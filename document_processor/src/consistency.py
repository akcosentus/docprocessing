"""Self-consistency verification for extraction results.

Runs extraction twice independently and compares results field-by-field
to identify inconsistencies and improve accuracy.
"""

from dataclasses import dataclass
from typing import Dict, Any, List, Optional

import src.config as config
from src.extractor import DocumentExtractor, ExtractionError, ExtractionResponse
from src.logger import get_logger

logger = get_logger(__name__)


@dataclass
class ConsistencyResult:
    """Result of consistency check between two extraction passes."""

    agreed_fields: List[str]  # Field paths that matched (e.g., ["patient.last_name", "patient.ssn"])
    inconsistent_fields: List[Dict[str, Any]]  # [{"field": "patient.phone", "pass1_value": "...", "pass2_value": "..."}]
    unresolved_fields: List[str]  # Fields that were null in both passes
    one_sided_fields: List[Dict[str, Any]]  # [{"field": "patient.ssn", "value": "...", "pass": 1}] - one pass null, other has value
    final_result: Dict[str, Any]  # Merged result with nulls for inconsistent fields, non-null values for one_sided_fields
    consistency_score: float  # 0.0-1.0, (agreed_fields + one_sided_fields) / total_comparable_fields
    total_input_tokens: int  # Sum of tokens from both passes
    total_output_tokens: int  # Sum of tokens from both passes


def _extract_all_leaf_fields(result: Dict[str, Any], prefix: str = "") -> Dict[str, Any]:
    """
    Recursively extract all leaf fields from nested result dict.

    Returns dict mapping field paths (e.g., "patient.last_name") to values.
    Excludes _meta fields except for confidence/conflicts/flags (which are not compared).

    Args:
        result: The extraction result dictionary.
        prefix: Current field path prefix (for recursion).

    Returns:
        Dictionary mapping field paths to values.
    """
    fields = {}

    for key, value in result.items():
        # Skip _meta entirely - we don't compare metadata fields
        if key == "_meta":
            continue

        field_path = f"{prefix}.{key}" if prefix else key

        if isinstance(value, dict):
            # Recurse into nested dictionaries
            fields.update(_extract_all_leaf_fields(value, field_path))
        elif isinstance(value, list):
            # For lists, compare the entire list as a single value
            # (e.g., diagnoses array)
            fields[field_path] = value
        else:
            # Leaf field (string, int, None, etc.)
            fields[field_path] = value

    return fields


def _merge_results_with_consistency(
    pass1_result: Dict[str, Any],
    pass2_result: Dict[str, Any],
    agreed_fields: List[str],
    inconsistent_fields: List[Dict[str, Any]],
    one_sided_fields: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Merge two results, using agreed values, nulling inconsistent fields, and preserving one-sided matches.

    - Agreed fields: use the matching value
    - Inconsistent fields: set to null, add "consistency_conflict_{field}" flag
    - One-sided fields: use the non-null value, add "low_confidence_single_pass" flag
    - Unresolved fields: remain null (no flag)

    Args:
        pass1_result: Result from first extraction pass.
        pass2_result: Result from second extraction pass.
        agreed_fields: List of field paths that matched between passes.
        inconsistent_fields: List of dicts with field, pass1_value, pass2_value.
        one_sided_fields: List of dicts with field, value, pass number.

    Returns:
        Merged result dictionary with consistency flags added to _meta.flags.
    """
    # Start with pass1_result as base (structure is identical)
    final = pass1_result.copy()

    # Helper to set nested field value
    def set_nested_field(d: Dict[str, Any], path: str, value: Any):
        """Set a nested field value using dot notation path."""
        parts = path.split(".")
        current = d
        for part in parts[:-1]:
            if part not in current:
                current[part] = {}
            current = current[part]
        current[parts[-1]] = value

    # Apply agreed fields (use pass1 value, they're identical)
    for field_path in agreed_fields:
        # Value is already correct from pass1_result, no change needed
        pass

    # Null out inconsistent fields
    for conflict in inconsistent_fields:
        field_path = conflict["field"]
        set_nested_field(final, field_path, None)

    # Apply one-sided fields (use the non-null value)
    for one_sided in one_sided_fields:
        field_path = one_sided["field"]
        value = one_sided["value"]
        set_nested_field(final, field_path, value)

    # Ensure _meta exists
    if "_meta" not in final:
        final["_meta"] = {}

    # Add flags
    flags = final["_meta"].get("flags", [])
    if not isinstance(flags, list):
        flags = []

    # Add consistency conflict flags
    for conflict in inconsistent_fields:
        flag = f"consistency_conflict_{conflict['field']}"
        if flag not in flags:
            flags.append(flag)

    # Add low confidence flag for one-sided fields (only once, not per field)
    if one_sided_fields and "low_confidence_single_pass" not in flags:
        flags.append("low_confidence_single_pass")

    final["_meta"]["flags"] = flags

    return final


def run_consistency_check(
    extractor: DocumentExtractor,
    messages_pass1: List[Dict[str, Any]],
    messages_pass2: List[Dict[str, Any]],
    model: str = None,
) -> ConsistencyResult:
    """
    Run two independent extraction passes and compare results.

    Args:
        extractor: DocumentExtractor instance (must be same instance for both passes).
        messages_pass1: Messages for first pass (must be identical to pass2).
        messages_pass2: Messages for second pass (must be identical to pass1).
        model: Model name (default: from config.MODEL_SNAPSHOT).

    Returns:
        ConsistencyResult with comparison results.

    Raises:
        ExtractionError: If either pass fails (propagated from extractor.extract()).
    """
    if model is None:
        model = config.MODEL_SNAPSHOT

    logger.debug("Running consistency check: pass 1")
    response1: ExtractionResponse = extractor.extract(messages_pass1, model=model)
    pass1_result = response1.result

    logger.debug("Running consistency check: pass 2")
    response2: ExtractionResponse = extractor.extract(messages_pass2, model=model)
    pass2_result = response2.result

    # Extract all leaf fields from both results
    fields1 = _extract_all_leaf_fields(pass1_result)
    fields2 = _extract_all_leaf_fields(pass2_result)

    # Get all unique field paths
    all_fields = set(fields1.keys()) | set(fields2.keys())

    agreed_fields: List[str] = []
    inconsistent_fields: List[Dict[str, Any]] = []
    unresolved_fields: List[str] = []
    one_sided_fields: List[Dict[str, Any]] = []

    for field_path in all_fields:
        val1 = fields1.get(field_path)
        val2 = fields2.get(field_path)

        # Normalize None vs missing key
        if field_path not in fields1:
            val1 = None
        if field_path not in fields2:
            val2 = None

        # Compare values (handle lists specially)
        if isinstance(val1, list) and isinstance(val2, list):
            # Compare lists by converting to tuples for equality
            val1_normalized = tuple(val1) if val1 else None
            val2_normalized = tuple(val2) if val2 else None
        else:
            val1_normalized = val1
            val2_normalized = val2

        # Categorize field
        if val1_normalized is None and val2_normalized is None:
            # Both null - unresolved
            unresolved_fields.append(field_path)
        elif val1_normalized == val2_normalized:
            # Both non-null and equal - agreed
            agreed_fields.append(field_path)
        elif val1_normalized is None or val2_normalized is None:
            # One null, one has value - one-sided match
            non_null_value = val1_normalized if val1_normalized is not None else val2_normalized
            non_null_pass = 1 if val1_normalized is not None else 2
            one_sided_fields.append({
                "field": field_path,
                "value": non_null_value,
                "pass": non_null_pass,
            })
        else:
            # Both non-null but different - inconsistent
            inconsistent_fields.append({
                "field": field_path,
                "pass1_value": val1_normalized,
                "pass2_value": val2_normalized,
            })

    # Merge results
    final_result = _merge_results_with_consistency(
        pass1_result,
        pass2_result,
        agreed_fields,
        inconsistent_fields,
        one_sided_fields,
    )

    # Calculate consistency score
    # Total comparable fields = all fields except unresolved (both null)
    total_comparable = len(all_fields) - len(unresolved_fields)
    if total_comparable == 0:
        consistency_score = 0.0
    else:
        # Score = (agreed + one_sided) / total_comparable
        consistency_score = (len(agreed_fields) + len(one_sided_fields)) / total_comparable

    # Log summary (PHI-safe: only field names, not values)
    logger.info(
        f"Consistency check complete: score={consistency_score:.2f}, "
        f"agreed={len(agreed_fields)}, inconsistent={len(inconsistent_fields)}, "
        f"one_sided={len(one_sided_fields)}, unresolved={len(unresolved_fields)}"
    )
    if inconsistent_fields:
        inconsistent_field_names = [c["field"] for c in inconsistent_fields]
        logger.warning(f"Inconsistent fields detected: {', '.join(inconsistent_field_names)}")

    return ConsistencyResult(
        agreed_fields=agreed_fields,
        inconsistent_fields=inconsistent_fields,
        unresolved_fields=unresolved_fields,
        one_sided_fields=one_sided_fields,
        final_result=final_result,
        consistency_score=consistency_score,
        total_input_tokens=response1.input_tokens + response2.input_tokens,
        total_output_tokens=response1.output_tokens + response2.output_tokens,
    )
