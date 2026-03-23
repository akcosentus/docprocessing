"""
prompts.py
----------
Prompt definitions for patient demographic document extraction via GPT-4o vision.
All prompts are designed for BAA-covered, ZDR-enabled OpenAI API usage.

Extraction flow:
  1. SYSTEM_PROMPT        — establishes model role, schema, and universal rules
  2. build_user_prompt()  — constructs the per-request user message with
                            facility-specific overrides injected at runtime
  3. VALIDATION_PROMPT    — secondary pass to resolve flagged conflicts
"""

from __future__ import annotations
from typing import Optional


# ---------------------------------------------------------------------------
# OUTPUT SCHEMA (canonical field names used throughout the system)
# ---------------------------------------------------------------------------
# Any change here must be reflected in your downstream validation and
# database mapping layers. Do not rename fields without a migration plan.

EXTRACTION_SCHEMA: dict = {
    "patient": {
        "last_name":        None,   # str | null
        "first_name":       None,   # str | null
        "middle_initial":   None,   # str (single char) | null
        "date_of_birth":    None,   # str "YYYY-MM-DD" | null
        "ssn":              None,   # str "XXX-XX-XXXX" | null — handle with care
        "sex":              None,   # str "M" | "F" | "Other" | null
        "address": {
            "street":       None,   # str | null
            "city":         None,   # str | null
            "state":        None,   # str (2-char abbreviation) | null
            "zip":          None,   # str | null
        },
        "phone":            None,   # str | null — preserve formatting from source
    },
    "insurance": {
        "primary": {
            "insurance_name":   None,   # str | null
            "policy_number":    None,   # str | null
        },
        "secondary": {
            "insurance_name":   None,   # str | null
            "policy_number":    None,   # str | null
        },
    },
    "clinical": {
        "rendering_facility":   None,   # str — top-of-document facility/location name
        "diagnoses":            [],     # list[str] — ICD codes or text, max 4 entries
    },
    "_meta": {
        "facility_id":          None,   # str — populated by caller, not the model
        "confidence":           None,   # "HIGH" | "MEDIUM" | "LOW"
        "conflicts":            [],     # list[dict] — populated when conflicts detected
        "missing_required":     [],     # list[str] — field names absent from document
        "flags":                [],     # list[str] — freeform extractor warnings
        "raw_payer_note":       None,   # str — verbatim payer text when ambiguous
    }
}


# ---------------------------------------------------------------------------
# SYSTEM PROMPT
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """
You are a medical document data extraction specialist. Your sole function is to \
extract structured patient demographic and insurance information from images of \
healthcare facility facesheets, intake forms, and registration documents.

You output exclusively valid JSON. No preamble, no explanation, no markdown fencing. \
Raw JSON only.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EXTRACTION RULES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

CARDINAL RULE: Extract only what is explicitly present on the document.
Never infer, guess, hallucinate, or complete partial information.

MISSING DATA
  • Any field not present on the document must be null (scalars) or [] (arrays).
  • Do not return empty strings "". Use null.
  • For missing_required, include the JSON path of any field that is null and
    would typically be expected (name, DOB, primary insurance). Use dot notation:
    e.g. "patient.last_name", "insurance.primary.insurance_name".

PATIENT NAME
  • Extract exactly as printed. Do not reformat capitalization.
  • middle_initial: single character only. If a full middle name is given,
    extract only the first character. Omit periods.

DATE OF BIRTH
  • Normalize all date formats to "YYYY-MM-DD".
  • Acceptable inputs: "01/15/1980", "Jan 15 1980", "1-15-80", etc.
  • Two-digit years: assume 1900s if year > current year's last two digits,
    otherwise assume 2000s. When ambiguous, add a flag.

SOCIAL SECURITY NUMBER
  • Extract only if explicitly labeled as SSN, Social Security, or Social.
  • Normalize to "XXX-XX-XXXX" format.
  • Do not extract partial SSNs (fewer than 9 digits). Mark as null and flag.
  • If the SSN is masked (e.g. "XXX-XX-1234"), extract the visible portion as-is.

SEX
  • Normalize to "M", "F", or "Other".
  • Acceptable source values: Male/Female, M/F, Boy/Girl, checkboxes, etc.
  • If the field is ambiguous or illegible, use null and flag.

ADDRESS
  • state: always return a 2-character uppercase abbreviation.
    Convert full state names (e.g. "California" → "CA").
  • zip: preserve as string. Include ZIP+4 if present (e.g. "92614-3201").
  • street: include unit/apt/suite if present on the same line or the next.

PHONE
  • Preserve the formatting as it appears on the document.
  • If multiple phone numbers exist, prefer the primary/home number.
    Flag if multiple numbers are present with no indication of which is primary.

RENDERING FACILITY
  • This is the name of the facility or location printed at the top of the document,
    often in a header or logo area.
  • Extract the location name exactly as printed. Do not extract addresses here.

DIAGNOSES
  • Capture up to 4. If more than 4 are present, take the first 4 as listed.
  • Include ICD-10 codes if present alongside text (e.g. "J18.9 Pneumonia").
  • If only codes are listed without descriptions, extract the codes.
  • Return [] if no diagnoses are found.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
INSURANCE EXTRACTION RULES (CRITICAL)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Insurance fields vary significantly across facilities. The following labels are
known to map to primary or secondary insurance — treat all of these equivalently:

  PRIMARY equivalents:
    "Primary Insurance", "Primary Payer", "Payer", "Insurance", "Insurance Name",
    "Carrier", "Plan", "Coverage", "Primary Coverage", "Ins 1", "Payer 1"

  SECONDARY equivalents:
    "Secondary Insurance", "Secondary Payer", "Supplemental", "Secondary Coverage",
    "Second Insurance", "Ins 2", "Payer 2", "Medicare Supplement",
    "Secondary Carrier", "Additional Insurance"

  POLICY NUMBER equivalents:
    "Policy #", "Policy Number", "Member ID", "Member #", "Subscriber ID",
    "ID #", "Group #", "Group Number", "Insurance ID", "Claim #", "Certificate #"

PRIVATE PAY / SELF PAY RULE
  If the primary insurance field contains any of the following values:
  "Private Pay", "Self Pay", "Self-Pay", "Private", "None", "N/A", "Cash"
  — do NOT populate insurance.primary with this value.
  — Instead, scan the entire document for any section containing actual
    insurance carrier information (e.g. Medicare, Medicaid, Blue Cross, Humana,
    Aetna, UnitedHealth, Cigna, etc.) or a policy/member ID number.
  — If found, use that as the primary insurance.
  — Set raw_payer_note to the verbatim text of the original primary field
    (e.g. "Private Pay") so downstream systems are aware of the substitution.
  — If no insurance information is found anywhere on the document, set
    insurance.primary to null and add "private_pay_no_insurance_found" to flags.

CONFLICT DETECTION
  If two or more locations on the document contain different insurance information
  for the same coverage tier, do NOT silently pick one. Instead:
  — Populate insurance.primary (or .secondary) with the most complete/specific value.
  — Add an entry to conflicts describing both values found.
  — Set raw_payer_note to preserve the verbatim alternative text.

  Conflict object format:
  {
    "field":    "insurance.primary.insurance_name",
    "value_a":  { "location": "header section", "value": "Private Pay" },
    "value_b":  { "location": "Insurance Information section", "value": "Medicare" },
    "resolved": "value_b — Medicare selected per Private Pay substitution rule"
  }

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CONFIDENCE SCORING
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Set _meta.confidence based on the following:

  HIGH   — All core fields (name, DOB, primary insurance) present and unambiguous.
            No conflicts. Document is legible.

  MEDIUM — One or more core fields are missing OR at least one conflict was
            detected and resolved OR document has partial illegibility.

  LOW    — Multiple core fields missing, OR a conflict could not be resolved,
            OR significant portions of the document are illegible or cut off.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FLAGS REFERENCE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Add the appropriate string to _meta.flags when applicable:

  "multiple_phone_numbers"          — more than one phone found, primary unclear
  "partial_ssn"                     — SSN present but incomplete
  "ambiguous_dob_century"           — two-digit year, century assumed
  "ambiguous_sex"                   — sex field present but unreadable
  "private_pay_substitution"       — private pay replaced with found insurance
  "private_pay_no_insurance_found"  — private pay with no alternative insurance
  "diagnoses_truncated"             — more than 4 diagnoses found, first 4 taken
  "illegible_section"               — one or more sections are unreadable
  "multi_page_document"             — document appears to be multi-page;
                                       extraction based on provided pages only
  "insurance_conflict"              — conflicting insurance data found and resolved
  "unresolved_conflict"             — conflicting data found, could not resolve
  "no_policy_number"                — insurance name found but no policy number
  "policy_number_only"              — policy number found but no insurance name

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
GENERAL CONSTRAINTS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  • _meta.facility_id must always be null. It is set by the calling system.
  • Do not include any PHI or document content in _meta.flags or _meta.conflicts
    beyond what is structurally necessary (field values in conflict objects are
    acceptable; do not add narrative summaries of patient information).
  • If the image is blank, corrupted, or clearly not a medical document, return
    a result with all fields null, confidence "LOW", and add the flag
    "invalid_document" to _meta.flags.
  • Do not output partial JSON. If extraction cannot be completed, return the
    full schema with null/[] values and appropriate flags.
""".strip()


# ---------------------------------------------------------------------------
# USER PROMPT BUILDER
# ---------------------------------------------------------------------------

def build_user_prompt(
    facility_name: str,
    facility_overrides: Optional[list[str]] = None,
    page_count: int = 1,
    page_number: int = 1,
) -> str:
    """
    Constructs the per-request user message sent alongside the document image.

    Args:
        facility_name:      Human-readable name of the sending facility.
                            Used for context only — not injected into output.
        facility_overrides: Optional list of facility-specific extraction rules
                            loaded from the facility config. Each entry is a
                            plain-English instruction string.
        page_count:         Total number of pages in this document.
        page_number:        The page number of the currently attached image.

    Returns:
        Formatted user prompt string.
    """
    lines: list[str] = []

    lines.append(
        f"Extract patient demographic information from the attached document image."
    )

    if page_count > 1:
        lines.append(
            f"This is page {page_number} of {page_count}. "
            f"Extract all available fields from this page. "
            f"Fields not present on this page should be null."
        )
        if page_number > 1:
            lines.append(
                "Note: rendering_facility should only be extracted from page 1 "
                "where the facility header is typically present."
            )

    lines.append(f"\nSource facility: {facility_name}")

    if facility_overrides:
        lines.append(
            "\nFACILITY-SPECIFIC RULES — These override general rules where they conflict:"
        )
        for i, rule in enumerate(facility_overrides, 1):
            lines.append(f"  {i}. {rule}")

    lines.append(
        "\nReturn raw JSON only. No explanation. No markdown. No commentary."
    )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CONFLICT RESOLUTION / VALIDATION PROMPT
# ---------------------------------------------------------------------------
# Used as a second-pass prompt when the first extraction returns confidence
# MEDIUM or LOW, or when _meta.conflicts is non-empty. Pass the original
# image(s) plus the first-pass JSON result back through this prompt.

VALIDATION_PROMPT = """
You are reviewing a prior extraction attempt from a medical document image.
The extraction result is provided below. Your task is to validate and correct it.

Do not re-extract the entire document. Focus only on:

  1. CONFLICTS: Each entry in _meta.conflicts represents a field where two
     different values were found on the document. Review the document image and
     determine the correct value. Update the field and set the "resolved" string
     in the conflict object to explain which value was chosen and why.

  2. LOW CONFIDENCE FIELDS: If _meta.confidence is "LOW" or "MEDIUM", re-examine
     the document for any fields that are null but may actually be present.
     Legibility issues from the first pass may be resolved with closer inspection.

  3. INSURANCE VERIFICATION: Re-verify that the Private Pay substitution rule
     was applied correctly if "private_pay_substitution" appears in _meta.flags.
     Confirm the substituted insurance name and policy number are accurate.

  4. FORMAT VALIDATION: Verify that:
       • date_of_birth is in "YYYY-MM-DD" format
       • ssn is in "XXX-XX-XXXX" format or null
       • state is a 2-character uppercase abbreviation
       • middle_initial is a single character with no period
       • diagnoses array has no more than 4 entries

  5. SCHEMA COMPLIANCE: Confirm no extra keys were added, no required keys
     are missing from the output structure, and all null fields use null
     (not empty string, not "N/A", not "Unknown").

Update _meta.confidence after your review:
  • Upgrade to HIGH only if all conflicts are resolved and core fields are present.
  • Downgrade to LOW if new issues are found that cannot be resolved.
  • Add any new flags discovered during validation.

Return the corrected JSON only. Same schema. No explanation. No markdown.

PRIOR EXTRACTION RESULT:
""".strip()


# ---------------------------------------------------------------------------
# PROMPT ASSEMBLY HELPERS
# ---------------------------------------------------------------------------

def build_messages_for_extraction(
    base64_image: str,
    facility_name: str,
    facility_overrides: Optional[list[str]] = None,
    page_count: int = 1,
    page_number: int = 1,
    image_media_type: str = "image/jpeg",
    ocr_text: Optional[str] = None,
) -> list[dict]:
    """
    Assembles the full messages array for the /v1/chat/completions API call.

    Args:
        base64_image:       Base64-encoded string of the document image.
        facility_name:      Name of the source facility.
        facility_overrides: Facility-specific rule overrides.
        page_count:         Total pages in document.
        page_number:        Current page number.
        image_media_type:   MIME type of the image (image/jpeg or image/png).
        ocr_text:           Optional raw OCR text. If provided and non-empty, adds OCR block
                           before image in user message. If None or empty, message structure
                           unchanged from current behavior.

    Returns:
        messages list ready for the OpenAI API call.
    """
    user_prompt = build_user_prompt(
        facility_name=facility_name,
        facility_overrides=facility_overrides,
        page_count=page_count,
        page_number=page_number,
    )

    # Build text content - include OCR if provided
    text_content = user_prompt
    if ocr_text and ocr_text.strip():
        text_content = (
            "RAW OCR TEXT FROM DOCUMENT (use to cross-reference with the image — "
            "the image is authoritative if they conflict):\n\n"
            f"{ocr_text}\n\n"
            f"{user_prompt}"
        )

    return [
        {
            "role": "system",
            "content": SYSTEM_PROMPT,
        },
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": text_content,
                },
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{image_media_type};base64,{base64_image}",
                        "detail": "high",
                    },
                },
            ],
        },
    ]


def build_messages_for_validation(
    base64_image: str,
    prior_result_json: str,
    image_media_type: str = "image/jpeg",
) -> list[dict]:
    """
    Assembles the messages array for the validation/second-pass API call.

    Args:
        base64_image:       Base64-encoded string of the original document image.
        prior_result_json:  The JSON string output from the first extraction pass.
        image_media_type:   MIME type of the image.

    Returns:
        messages list for the validation API call.
    """
    return [
        {
            "role": "system",
            "content": SYSTEM_PROMPT,
        },
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": f"{VALIDATION_PROMPT}\n\n{prior_result_json}",
                },
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{image_media_type};base64,{base64_image}",
                        "detail": "high",
                    },
                },
            ],
        },
    ]


# ---------------------------------------------------------------------------
# FACILITY CONFIG EXAMPLES
# ---------------------------------------------------------------------------
# In production, load these from a database or config file (YAML/JSON).
# The facility_overrides list items are plain-English rules injected into
# the user prompt at runtime. Keep each rule atomic and unambiguous.

FACILITY_CONFIG_EXAMPLES: dict[str, dict] = {
    "baywood_court": {
        "display_name": "Baywood Court",
        "overrides": [
            "The header section of this form lists 'Private Pay' as the primary payer. "
            "This is always incorrect for this facility. Ignore it.",
            "The true primary insurance is located under the section labeled "
            "'Insurance Information' further down the document. Use that section "
            "for insurance.primary.",
            "Set raw_payer_note to 'Private Pay (header — ignored per facility rule)'.",
        ],
    },
    "bellaken": {
        "display_name": "Bellaken",
        "overrides": [
            "Primary insurance is labeled 'Primary Payer' and will typically be Medicare.",
            "Secondary insurance carrier name is found in the 'Insurance Name' box, "
            "NOT the 'Payer Information' section. Prefer the 'Insurance Name' box value "
            "for insurance.secondary.insurance_name.",
            "If the 'Payer Information' section conflicts with 'Insurance Name' box, "
            "flag it as insurance_conflict and resolve in favor of 'Insurance Name' box.",
        ],
    },
}
