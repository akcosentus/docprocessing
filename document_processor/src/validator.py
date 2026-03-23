"""Post-extraction validation of extracted patient data."""

import re
from dataclasses import dataclass
from typing import Dict, Any, List

from src.logger import get_logger

logger = get_logger(__name__)


@dataclass
class ValidationResult:
    """Result of validation check."""

    is_valid: bool
    errors: List[str]


def _get_nested_value(data: Dict[str, Any], path: str) -> Any:
    """
    Get a nested value from a dictionary using dot notation.

    Args:
        data: The dictionary to search
        path: Dot-notation path (e.g., "patient.first_name")

    Returns:
        The value at the path, or None if not found
    """
    keys = path.split(".")
    value = data
    for key in keys:
        if isinstance(value, dict) and key in value:
            value = value[key]
        else:
            return None
    return value


def validate_extraction(result: Dict[str, Any]) -> ValidationResult:
    """
    Validate extracted patient data against schema and format requirements.

    Args:
        result: The extracted data dictionary

    Returns:
        ValidationResult with is_valid flag and list of error messages
    """
    logger.debug("Starting extraction validation")
    errors: List[str] = []

    # Required top-level schema keys
    required_top_level_keys = ["patient", "insurance", "clinical", "_meta"]
    for key in required_top_level_keys:
        if key not in result:
            errors.append(f"Missing required top-level key: {key}")

    # Validate patient.date_of_birth format (YYYY-MM-DD) if present
    dob = _get_nested_value(result, "patient.date_of_birth")
    if dob is not None:
        if not isinstance(dob, str):
            errors.append("patient.date_of_birth must be a string")
        elif not re.match(r"^\d{4}-\d{2}-\d{2}$", dob):
            errors.append(
                f"patient.date_of_birth must match YYYY-MM-DD format, got: {dob}"
            )

    # Validate patient.ssn format (XXX-XX-XXXX) if present
    ssn = _get_nested_value(result, "patient.ssn")
    if ssn is not None:
        if not isinstance(ssn, str):
            errors.append("patient.ssn must be a string")
        elif not re.match(r"^\d{3}-\d{2}-\d{4}$", ssn):
            errors.append(f"patient.ssn must match XXX-XX-XXXX format, got: {ssn}")

    # Validate patient.address.state format (2-char uppercase) if present
    state = _get_nested_value(result, "patient.address.state")
    if state is not None:
        if not isinstance(state, str):
            errors.append("patient.address.state must be a string")
        elif not re.match(r"^[A-Z]{2}$", state):
            errors.append(
                f"patient.address.state must be 2-character uppercase code, got: {state}"
            )

    # Validate patient.middle_initial format (single char) if present
    middle_initial = _get_nested_value(result, "patient.middle_initial")
    if middle_initial is not None:
        if not isinstance(middle_initial, str):
            errors.append("patient.middle_initial must be a string")
        elif len(middle_initial) != 1:
            errors.append(
                f"patient.middle_initial must be a single character, got: {middle_initial}"
            )

    # Validate clinical.diagnoses is a list with max 4 items
    diagnoses = _get_nested_value(result, "clinical.diagnoses")
    if diagnoses is not None:
        if not isinstance(diagnoses, list):
            errors.append("clinical.diagnoses must be a list")
        elif len(diagnoses) > 4:
            errors.append(
                f"clinical.diagnoses list must contain at most 4 items, got: {len(diagnoses)}"
            )

    # Validate _meta.confidence enum
    confidence = _get_nested_value(result, "_meta.confidence")
    if confidence is not None:
        valid_confidences = ["HIGH", "MEDIUM", "LOW"]
        if confidence not in valid_confidences:
            errors.append(
                f"_meta.confidence must be one of {valid_confidences}, got: {confidence}"
            )

    is_valid = len(errors) == 0
    logger.debug(f"Validation complete: {'valid' if is_valid else f'{len(errors)} error(s)'}")
    return ValidationResult(is_valid=is_valid, errors=errors)


def should_run_validation_pass(result: Dict[str, Any]) -> bool:
    """
    Determine if a second-pass validation should be run.

    Args:
        result: The extracted data dictionary

    Returns:
        True if validation pass should be run (MEDIUM/LOW confidence or conflicts present)
    """
    confidence = _get_nested_value(result, "_meta.confidence")
    conflicts = _get_nested_value(result, "_meta.conflicts")

    # Run validation if confidence is MEDIUM or LOW
    if confidence in ["MEDIUM", "LOW"]:
        return True

    # Run validation if there are unresolved conflicts
    if conflicts and isinstance(conflicts, list) and len(conflicts) > 0:
        return True

    return False
