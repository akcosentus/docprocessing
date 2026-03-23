"""Facility classification pre-pass for automatic facility detection.

Runs a separate API call before extraction to identify the source facility
from document headers, footers, or letterhead. This enables automatic
routing to the correct facility config without requiring --facility flag.
"""

import re
from dataclasses import dataclass
from typing import Dict, Any, List, Optional, Tuple

from rapidfuzz import fuzz

import src.config as config
from src.extractor import DocumentExtractor, ExtractionError
from src.logger import get_logger
from src.schemas import ClassificationOutput

logger = get_logger(__name__)

# Classification API parameters
CLASSIFIER_MODEL = "gpt-4o-2024-11-20"  # Same pinned model as extractor
CLASSIFIER_DETAIL = "low"  # 85 tokens — only need to read header/logo
CLASSIFIER_TEMPERATURE = 0

# System prompt for classification
CLASSIFIER_SYSTEM_PROMPT = """You are a document routing assistant for a medical billing company. Your only job is to identify which healthcare facility sent this document.

Look for:
- Facility name in the document header or letterhead
- Facility name in a footer
- A logo with text
- A "Facility:" or "From:" label anywhere on the document

Return ONLY the facility name exactly as it appears on the document. If you see multiple names (e.g., a parent company and a location name), return the most specific location name.

If no facility name is visible, return null for facility_name and set confidence to LOW.

Do not extract any patient information. Do not read any fields other than the facility name."""

CLASSIFIER_USER_MESSAGE = "Identify the facility name on this document. Return only the structured output."


@dataclass
class ClassificationResult:
    """Result of facility classification pre-pass."""

    detected_name: Optional[str]  # Raw name found on document
    matched_facility_id: Optional[str]  # Config key if matched, else None
    match_type: str  # "exact" | "fuzzy" | "none"
    match_score: float  # 0.0-1.0 fuzzy similarity score (1.0 for exact)
    confidence: str  # "HIGH" | "MEDIUM" | "LOW"
    raw_response: Dict[str, Any]  # Full structured output from classifier call
    input_tokens: int
    output_tokens: int


def classify_document(
    base64_image: str,
    image_media_type: str = "image/jpeg",
    model: str = CLASSIFIER_MODEL,
) -> ClassificationResult:
    """
    Run classification pre-pass to identify source facility.

    Sends first page at low detail. Returns detected name and confidence.
    Never extracts patient data. Safe to call before facility config is known.

    Args:
        base64_image: Base64-encoded first page image
        image_media_type: MIME type (default: image/jpeg)
        model: OpenAI model string (default: pinned snapshot)

    Returns:
        ClassificationResult with detected name, tokens, confidence

    Raises:
        ExtractionError: If API call fails after retries
    """
    extractor = DocumentExtractor()

    # Build messages for classification
    messages = [
        {
            "role": "system",
            "content": CLASSIFIER_SYSTEM_PROMPT,
        },
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": CLASSIFIER_USER_MESSAGE,
                },
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{image_media_type};base64,{base64_image}",
                        "detail": CLASSIFIER_DETAIL,  # Low detail for header/logo
                    },
                },
            ],
        },
    ]

    try:
        # Use Structured Outputs with ClassificationOutput schema
        # Call the API directly (same pattern as extractor but with ClassificationOutput)
        response = extractor.client.beta.chat.completions.parse(
            model=model,
            messages=messages,
            temperature=CLASSIFIER_TEMPERATURE,
            store=False,  # HIPAA/ZDR requirement — do not store PHI
            response_format=ClassificationOutput,
        )

        # Check for model refusal
        message = response.choices[0].message
        if message.refusal is not None:
            raise ExtractionError(
                f"Model refused the classification request: {message.refusal}"
            )

        parsed: Optional[ClassificationOutput] = message.parsed
        if parsed is None:
            raise ExtractionError("Parsed classification response is None — no data returned.")

        # Extract token usage
        usage = response.usage
        input_tokens = usage.prompt_tokens if usage else 0
        output_tokens = usage.completion_tokens if usage else 0

        # Build ClassificationResult (matching happens in resolve_facility)
        result = ClassificationResult(
            detected_name=parsed.facility_name,
            matched_facility_id=None,  # Set by resolve_facility()
            match_type="none",  # Set by resolve_facility()
            match_score=0.0,  # Set by resolve_facility()
            confidence=parsed.confidence,
            raw_response=parsed.model_dump(by_alias=True),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )

        logger.debug(
            f"Classification complete: detected_name={result.detected_name}, "
            f"confidence={result.confidence}, tokens={input_tokens + output_tokens}"
        )

        return result

    except ExtractionError:
        raise
    except Exception as e:
        raise ExtractionError(
            f"Classification failed: {e}",
            original_error=e,
        ) from e


def resolve_facility(
    classification: ClassificationResult,
    facilities: Dict[str, Any],
    fuzzy_threshold: float = 0.80,
) -> Tuple[Optional[str], str]:
    """
    Match detected facility name against known facilities config.

    Runs locally — no API call. Uses rapidfuzz for similarity scoring.

    Args:
        classification: Result from classify_document()
        facilities: Full facilities config dict (from load_facilities())
        fuzzy_threshold: Minimum score to accept a fuzzy match (default: 0.80)

    Returns:
        Tuple of (facility_id or None, match_type)
        match_type: "exact" | "fuzzy" | "none"
    """
    if not classification.detected_name:
        classification.match_type = "none"
        classification.match_score = 0.0
        return None, "none"

    detected_name = classification.detected_name.strip()

    # Step 1: Check for exact match (case-insensitive)
    for facility_id, facility_data in facilities.items():
        display_names = facility_data.get("display_names", [])
        # Also check display_name as fallback
        if not display_names:
            display_names = [facility_data.get("display_name", "")]
        
        for display_name in display_names:
            if display_name and display_name.strip().lower() == detected_name.lower():
                classification.matched_facility_id = facility_id
                classification.match_type = "exact"
                classification.match_score = 1.0
                logger.debug(f"Exact match: '{detected_name}' → '{facility_id}'")
                return facility_id, "exact"

    # Step 2: Fuzzy match against all display_names
    best_match: Optional[Tuple[str, float]] = None  # (facility_id, score)
    all_matches: List[Tuple[str, str, float]] = []  # (facility_id, display_name, score)

    for facility_id, facility_data in facilities.items():
        display_names = facility_data.get("display_names", [])
        # Also check display_name as fallback
        if not display_names:
            display_names = [facility_data.get("display_name", "")]
        
        for display_name in display_names:
            if not display_name:
                continue
            
            # Use token_sort_ratio (handles word order differences)
            score = fuzz.token_sort_ratio(detected_name, display_name) / 100.0
            
            if score >= fuzzy_threshold:
                all_matches.append((facility_id, display_name, score))
                if best_match is None or score > best_match[1]:
                    best_match = (facility_id, score)

    # Step 3: Tiebreaker logic
    if best_match is None:
        classification.match_type = "none"
        classification.match_score = 0.0
        return None, "none"

    # Check for exact tie (multiple facilities with same highest score)
    if len(all_matches) > 1:
        highest_score = best_match[1]
        ties = [m for m in all_matches if m[2] == highest_score]
        if len(ties) > 1:
            # Exact tie — flag for review
            logger.warning(
                f"Fuzzy match tie: '{detected_name}' matches {len(ties)} facilities "
                f"with score {highest_score:.2f}: {[t[0] for t in ties]}"
            )
            classification.match_type = "none"
            classification.match_score = highest_score
            return None, "none"

    # Single best match
    facility_id, score = best_match
    classification.matched_facility_id = facility_id
    classification.match_type = "fuzzy"
    classification.match_score = score
    logger.debug(f"Fuzzy match: '{detected_name}' → '{facility_id}' (score={score:.2f})")
    return facility_id, "fuzzy"
