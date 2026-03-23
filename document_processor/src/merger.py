"""Merge per-page extraction results into a single consolidated result."""

from typing import Any, Dict, List

from src.logger import get_logger

logger = get_logger(__name__)


def _first_non_null(values: List[Any]) -> Any:
    """Return the first non-null value from a list, or None if all are null.

    Args:
        values: List of values to search.

    Returns:
        First non-null value, or None.
    """
    for value in values:
        if value is not None:
            return value
    return None


def _lowest_confidence(confidences: List[str]) -> str:
    """Return the lowest confidence level from a list.

    Order: LOW < MEDIUM < HIGH.

    Args:
        confidences: List of confidence strings.

    Returns:
        Lowest confidence level.
    """
    if not confidences:
        return "LOW"
    if "LOW" in confidences:
        return "LOW"
    if "MEDIUM" in confidences:
        return "MEDIUM"
    return "HIGH"


def _recalculate_missing_required(merged: Dict[str, Any]) -> List[str]:
    """Recalculate missing_required after merge.

    A field is missing if it's null in the merged result and would typically
    be expected (name, DOB, primary insurance).

    Args:
        merged: The merged extraction result dict.

    Returns:
        List of missing field paths in dot notation.
    """
    missing = []
    patient = merged.get("patient", {})
    insurance = merged.get("insurance", {})
    clinical = merged.get("clinical", {})

    if not patient.get("first_name"):
        missing.append("patient.first_name")
    if not patient.get("last_name"):
        missing.append("patient.last_name")
    if not patient.get("date_of_birth"):
        missing.append("patient.date_of_birth")
    if not insurance.get("primary", {}).get("insurance_name"):
        missing.append("insurance.primary.insurance_name")
    if not clinical.get("rendering_facility"):
        missing.append("clinical.rendering_facility")

    return missing


def merge_pages(page_results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Merge per-page extraction dicts into a single ExtractionResult dict.

    Rules:
    - Single page: return as-is, no processing.
    - Scalar fields: first non-null value wins (page order).
    - rendering_facility: always taken from page 1 only.
    - diagnoses: combined across pages, deduplicated, capped at 4.
    - conflicts: concatenated from all pages.
    - flags: concatenated, deduplicated.
    - missing_required: recalculated after merge (field present on any page = not missing).
    - confidence: lowest value across all pages (LOW < MEDIUM < HIGH).

    Args:
        page_results: List of extraction dicts, one per page, in page order.

    Returns:
        Single merged extraction dict.
    """
    if len(page_results) == 1:
        logger.debug("Single page document, returning as-is")
        return page_results[0]

    logger.debug(f"Merging {len(page_results)} page results")
    merged: Dict[str, Any] = {
        "patient": {},
        "insurance": {"primary": {}, "secondary": {}},
        "clinical": {},
        "_meta": {},
    }

    # Merge patient fields (first non-null wins)
    patient_fields = [
        "last_name",
        "first_name",
        "middle_initial",
        "date_of_birth",
        "ssn",
        "sex",
        "phone",
    ]
    for field in patient_fields:
        values = [page.get("patient", {}).get(field) for page in page_results]
        merged["patient"][field] = _first_non_null(values)

    # Merge address (first non-null for each subfield)
    address_fields = ["street", "city", "state", "zip"]
    merged["patient"]["address"] = {}
    for field in address_fields:
        values = [
            page.get("patient", {}).get("address", {}).get(field)
            for page in page_results
        ]
        merged["patient"]["address"][field] = _first_non_null(values)

    # Merge insurance (first non-null wins)
    for tier in ["primary", "secondary"]:
        for field in ["insurance_name", "policy_number"]:
            values = [
                page.get("insurance", {}).get(tier, {}).get(field)
                for page in page_results
            ]
            merged["insurance"][tier][field] = _first_non_null(values)

    # rendering_facility: always from page 1
    merged["clinical"]["rendering_facility"] = (
        page_results[0].get("clinical", {}).get("rendering_facility")
    )

    # diagnoses: combine, deduplicate, cap at 4
    all_diagnoses = []
    for page in page_results:
        page_diagnoses = page.get("clinical", {}).get("diagnoses", [])
        if isinstance(page_diagnoses, list):
            all_diagnoses.extend(page_diagnoses)
    # Deduplicate while preserving order
    seen = set()
    unique_diagnoses = []
    for diag in all_diagnoses:
        if diag not in seen:
            seen.add(diag)
            unique_diagnoses.append(diag)
    merged["clinical"]["diagnoses"] = unique_diagnoses[:4]

    # conflicts: concatenate from all pages
    all_conflicts = []
    for page in page_results:
        page_conflicts = page.get("_meta", {}).get("conflicts", [])
        if isinstance(page_conflicts, list):
            all_conflicts.extend(page_conflicts)
    merged["_meta"]["conflicts"] = all_conflicts

    # flags: concatenate, deduplicate
    all_flags = []
    for page in page_results:
        page_flags = page.get("_meta", {}).get("flags", [])
        if isinstance(page_flags, list):
            all_flags.extend(page_flags)
    # Deduplicate while preserving order
    seen_flags = set()
    unique_flags = []
    for flag in all_flags:
        if flag not in seen_flags:
            seen_flags.add(flag)
            unique_flags.append(flag)
    merged["_meta"]["flags"] = unique_flags

    # confidence: lowest across all pages
    confidences = [
        page.get("_meta", {}).get("confidence")
        for page in page_results
        if page.get("_meta", {}).get("confidence")
    ]
    merged["_meta"]["confidence"] = _lowest_confidence(confidences)

    # missing_required: recalculate after merge
    merged["_meta"]["missing_required"] = _recalculate_missing_required(merged)

    # facility_id: take from first page (should be same across all)
    merged["_meta"]["facility_id"] = (
        page_results[0].get("_meta", {}).get("facility_id")
    )

    # raw_payer_note: first non-null
    raw_notes = [
        page.get("_meta", {}).get("raw_payer_note") for page in page_results
    ]
    merged["_meta"]["raw_payer_note"] = _first_non_null(raw_notes)

    logger.debug("Page merge completed")
    return merged
