"""Unit tests for validator module."""

import pytest

from src.validator import ValidationResult, should_run_validation_pass, validate_extraction


def test_validate_extraction_all_valid():
    """Test validation with all valid fields."""
    result = {
        "patient": {
            "first_name": "John",
            "last_name": "Doe",
            "middle_initial": "A",
            "date_of_birth": "1990-01-15",
            "ssn": "123-45-6789",
            "sex": "M",
            "address": {
                "street": "123 Main St",
                "city": "Springfield",
                "state": "CA",
                "zip": "12345",
            },
            "phone": "555-1234",
        },
        "insurance": {
            "primary": {"insurance_name": "Medicare", "policy_number": "123456"},
            "secondary": {"insurance_name": None, "policy_number": None},
        },
        "clinical": {
            "rendering_facility": "Test Facility",
            "diagnoses": ["E11.9", "I10"],
        },
        "_meta": {
            "facility_id": None,
            "confidence": "HIGH",
            "conflicts": [],
            "missing_required": [],
            "flags": [],
            "raw_payer_note": None,
        },
    }

    validation = validate_extraction(result)
    assert validation.is_valid is True
    assert len(validation.errors) == 0


def test_validate_extraction_missing_required_top_level():
    """Test validation with missing required top-level keys."""
    result = {
        "patient": {
            "first_name": "John",
        },
        # Missing insurance, clinical, _meta
    }

    validation = validate_extraction(result)
    assert validation.is_valid is False
    assert len(validation.errors) > 0
    assert any("insurance" in error or "clinical" in error or "_meta" in error for error in validation.errors)


def test_validate_extraction_invalid_date_format():
    """Test validation with invalid date format."""
    result = {
        "patient": {
            "first_name": "John",
            "last_name": "Doe",
            "date_of_birth": "01/15/1990",  # Wrong format
            "ssn": "123-45-6789",
            "address": {"state": "CA"},
        },
        "insurance": {"primary": {}, "secondary": {}},
        "clinical": {"diagnoses": []},
        "_meta": {"confidence": "HIGH", "conflicts": [], "missing_required": [], "flags": []},
    }

    validation = validate_extraction(result)
    assert validation.is_valid is False
    assert any("patient.date_of_birth" in error and "YYYY-MM-DD" in error for error in validation.errors)


def test_validate_extraction_invalid_ssn_format():
    """Test validation with invalid SSN format."""
    result = {
        "patient": {
            "first_name": "John",
            "last_name": "Doe",
            "date_of_birth": "1990-01-15",
            "ssn": "123456789",  # Missing dashes
            "address": {"state": "CA"},
        },
        "insurance": {"primary": {}, "secondary": {}},
        "clinical": {"diagnoses": []},
        "_meta": {"confidence": "HIGH", "conflicts": [], "missing_required": [], "flags": []},
    }

    validation = validate_extraction(result)
    assert validation.is_valid is False
    assert any("patient.ssn" in error and "XXX-XX-XXXX" in error for error in validation.errors)


def test_validate_extraction_invalid_state_format():
    """Test validation with invalid state format."""
    result = {
        "patient": {
            "first_name": "John",
            "last_name": "Doe",
            "date_of_birth": "1990-01-15",
            "ssn": "123-45-6789",
            "address": {
                "state": "california",  # Not uppercase, too long
            },
        },
        "insurance": {"primary": {}, "secondary": {}},
        "clinical": {"diagnoses": []},
        "_meta": {"confidence": "HIGH", "conflicts": [], "missing_required": [], "flags": []},
    }

    validation = validate_extraction(result)
    assert validation.is_valid is False
    assert any("patient.address.state" in error and "2-character uppercase" in error for error in validation.errors)


def test_validate_extraction_invalid_middle_initial():
    """Test validation with invalid middle initial."""
    result = {
        "patient": {
            "first_name": "John",
            "last_name": "Doe",
            "date_of_birth": "1990-01-15",
            "ssn": "123-45-6789",
            "middle_initial": "AB",  # Too long
            "address": {"state": "CA"},
        },
        "insurance": {"primary": {}, "secondary": {}},
        "clinical": {"diagnoses": []},
        "_meta": {"confidence": "HIGH", "conflicts": [], "missing_required": [], "flags": []},
    }

    validation = validate_extraction(result)
    assert validation.is_valid is False
    assert any("patient.middle_initial" in error and "single character" in error for error in validation.errors)


def test_validate_extraction_too_many_diagnoses():
    """Test validation with too many diagnoses."""
    result = {
        "patient": {
            "first_name": "John",
            "last_name": "Doe",
            "date_of_birth": "1990-01-15",
            "ssn": "123-45-6789",
            "address": {"state": "CA"},
        },
        "insurance": {"primary": {}, "secondary": {}},
        "clinical": {
            "diagnoses": ["E11.9", "I10", "M79.3", "F41.1", "Z00.00"],  # 5 items
        },
        "_meta": {"confidence": "HIGH", "conflicts": [], "missing_required": [], "flags": []},
    }

    validation = validate_extraction(result)
    assert validation.is_valid is False
    assert any("clinical.diagnoses" in error and "at most 4 items" in error for error in validation.errors)


def test_validate_extraction_invalid_confidence():
    """Test validation with invalid confidence value."""
    result = {
        "patient": {
            "first_name": "John",
            "last_name": "Doe",
            "date_of_birth": "1990-01-15",
            "ssn": "123-45-6789",
            "address": {"state": "CA"},
        },
        "insurance": {"primary": {}, "secondary": {}},
        "clinical": {"diagnoses": []},
        "_meta": {
            "confidence": "VERY_HIGH",  # Invalid
            "conflicts": [],
            "missing_required": [],
            "flags": [],
        },
    }

    validation = validate_extraction(result)
    assert validation.is_valid is False
    assert any("_meta.confidence" in error and ("HIGH" in error or "MEDIUM" in error or "LOW" in error) for error in validation.errors)


def test_validate_extraction_null_values_allowed():
    """Test that None values are allowed for optional fields."""
    result = {
        "patient": {
            "first_name": "John",
            "last_name": "Doe",
            "date_of_birth": None,  # None is allowed
            "ssn": None,  # None is allowed
            "address": {
                "state": None,  # None is allowed
            },
            "middle_initial": None,  # None is allowed
        },
        "insurance": {"primary": {}, "secondary": {}},
        "clinical": {"diagnoses": []},
        "_meta": {"confidence": "HIGH", "conflicts": [], "missing_required": [], "flags": []},
    }

    validation = validate_extraction(result)
    assert validation.is_valid is True


def test_should_run_validation_pass_medium_confidence():
    """Test that validation pass should run for MEDIUM confidence."""
    result = {
        "_meta": {"confidence": "MEDIUM", "conflicts": []},
    }
    assert should_run_validation_pass(result) is True


def test_should_run_validation_pass_low_confidence():
    """Test that validation pass should run for LOW confidence."""
    result = {
        "_meta": {"confidence": "LOW", "conflicts": []},
    }
    assert should_run_validation_pass(result) is True


def test_should_run_validation_pass_with_conflicts():
    """Test that validation pass should run when conflicts exist."""
    result = {
        "_meta": {
            "confidence": "HIGH",
            "conflicts": [{"field": "insurance.primary.insurance_name"}],
        },
    }
    assert should_run_validation_pass(result) is True


def test_should_run_validation_pass_high_no_conflicts():
    """Test that validation pass should not run for HIGH confidence with no conflicts."""
    result = {
        "_meta": {"confidence": "HIGH", "conflicts": []},
    }
    assert should_run_validation_pass(result) is False
