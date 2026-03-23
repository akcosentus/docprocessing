"""Unit tests for merger module."""

import pytest

from src.merger import merge_pages


def test_single_page_passthrough():
    """Test that single page returns identical dict."""
    page_result = {
        "patient": {"first_name": "John", "last_name": "Doe"},
        "insurance": {"primary": {"insurance_name": "Medicare"}},
        "clinical": {"rendering_facility": "Test Facility"},
        "_meta": {"confidence": "HIGH", "conflicts": [], "flags": []},
    }
    merged = merge_pages([page_result])
    assert merged == page_result


def test_multi_page_scalar_merge():
    """Test that first non-null value wins across pages."""
    page1 = {
        "patient": {"first_name": None, "last_name": "Doe"},
        "insurance": {"primary": {}, "secondary": {}},
        "clinical": {},
        "_meta": {"confidence": "HIGH", "conflicts": [], "flags": []},
    }
    page2 = {
        "patient": {"first_name": "John", "last_name": None},
        "insurance": {"primary": {}, "secondary": {}},
        "clinical": {},
        "_meta": {"confidence": "MEDIUM", "conflicts": [], "flags": []},
    }
    merged = merge_pages([page1, page2])
    assert merged["patient"]["first_name"] == "John"
    assert merged["patient"]["last_name"] == "Doe"


def test_rendering_facility_from_page1_only():
    """Test that rendering_facility always comes from page 1."""
    page1 = {
        "patient": {},
        "insurance": {"primary": {}, "secondary": {}},
        "clinical": {"rendering_facility": "Facility A"},
        "_meta": {"confidence": "HIGH", "conflicts": [], "flags": []},
    }
    page2 = {
        "patient": {},
        "insurance": {"primary": {}, "secondary": {}},
        "clinical": {"rendering_facility": "Facility B"},
        "_meta": {"confidence": "HIGH", "conflicts": [], "flags": []},
    }
    merged = merge_pages([page1, page2])
    assert merged["clinical"]["rendering_facility"] == "Facility A"


def test_diagnoses_dedup_and_cap():
    """Test that diagnoses are combined, deduplicated, and capped at 4."""
    page1 = {
        "patient": {},
        "insurance": {"primary": {}, "secondary": {}},
        "clinical": {"diagnoses": ["E11.9", "I10", "M79.3"]},
        "_meta": {"confidence": "HIGH", "conflicts": [], "flags": []},
    }
    page2 = {
        "patient": {},
        "insurance": {"primary": {}, "secondary": {}},
        "clinical": {"diagnoses": ["I10", "F41.1", "Z00.00", "J18.9"]},  # I10 is duplicate
        "_meta": {"confidence": "HIGH", "conflicts": [], "flags": []},
    }
    merged = merge_pages([page1, page2])
    diagnoses = merged["clinical"]["diagnoses"]
    assert len(diagnoses) == 4  # Capped at 4
    assert "I10" in diagnoses  # Present once (deduplicated)
    assert diagnoses.count("I10") == 1


def test_confidence_takes_lowest():
    """Test that confidence takes the lowest value."""
    page1 = {
        "patient": {},
        "insurance": {"primary": {}, "secondary": {}},
        "clinical": {},
        "_meta": {"confidence": "HIGH", "conflicts": [], "flags": []},
    }
    page2 = {
        "patient": {},
        "insurance": {"primary": {}, "secondary": {}},
        "clinical": {},
        "_meta": {"confidence": "MEDIUM", "conflicts": [], "flags": []},
    }
    merged = merge_pages([page1, page2])
    assert merged["_meta"]["confidence"] == "MEDIUM"


def test_missing_required_recalculation():
    """Test that missing_required is recalculated after merge."""
    page1 = {
        "patient": {"first_name": None, "last_name": "Doe"},
        "insurance": {"primary": {}, "secondary": {}},
        "clinical": {},
        "_meta": {"confidence": "HIGH", "conflicts": [], "flags": [], "missing_required": ["patient.first_name"]},
    }
    page2 = {
        "patient": {"first_name": "John", "last_name": None},
        "insurance": {"primary": {}, "secondary": {}},
        "clinical": {},
        "_meta": {"confidence": "HIGH", "conflicts": [], "flags": [], "missing_required": ["patient.last_name"]},
    }
    merged = merge_pages([page1, page2])
    # After merge, both first_name and last_name are present, so neither should be in missing_required
    assert "patient.first_name" not in merged["_meta"]["missing_required"]
    assert "patient.last_name" not in merged["_meta"]["missing_required"]


def test_flags_deduplication():
    """Test that duplicate flags appear only once."""
    page1 = {
        "patient": {},
        "insurance": {"primary": {}, "secondary": {}},
        "clinical": {},
        "_meta": {"confidence": "HIGH", "conflicts": [], "flags": ["flag1", "flag2"]},
    }
    page2 = {
        "patient": {},
        "insurance": {"primary": {}, "secondary": {}},
        "clinical": {},
        "_meta": {"confidence": "HIGH", "conflicts": [], "flags": ["flag2", "flag3"]},
    }
    merged = merge_pages([page1, page2])
    flags = merged["_meta"]["flags"]
    assert "flag1" in flags
    assert "flag2" in flags
    assert "flag3" in flags
    assert flags.count("flag2") == 1  # Deduplicated
