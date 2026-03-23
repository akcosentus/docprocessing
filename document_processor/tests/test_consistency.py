"""Unit tests for consistency module."""

from unittest.mock import MagicMock, patch
from dataclasses import dataclass

import pytest

from src.consistency import (
    ConsistencyResult,
    run_consistency_check,
    _extract_all_leaf_fields,
    _merge_results_with_consistency,
)
from src.extractor import DocumentExtractor, ExtractionResponse


@dataclass
class MockExtractionResponse:
    """Mock ExtractionResponse for testing."""
    result: dict
    input_tokens: int
    output_tokens: int


def test_extract_all_leaf_fields():
    """Test that _extract_all_leaf_fields extracts all leaf fields correctly."""
    result = {
        "patient": {
            "last_name": "Doe",
            "first_name": "John",
            "address": {
                "street": "123 Main St",
                "city": "Anytown",
            },
        },
        "insurance": {
            "primary": {
                "insurance_name": "Medicare",
                "policy_number": "123456",
            },
        },
        "clinical": {
            "diagnoses": ["E11.9", "I10"],
        },
        "_meta": {
            "confidence": "HIGH",
            "flags": [],
        },
    }

    fields = _extract_all_leaf_fields(result)

    assert "patient.last_name" in fields
    assert fields["patient.last_name"] == "Doe"
    assert "patient.first_name" in fields
    assert "patient.address.street" in fields
    assert "patient.address.city" in fields
    assert "insurance.primary.insurance_name" in fields
    assert "insurance.primary.policy_number" in fields
    assert "clinical.diagnoses" in fields
    assert fields["clinical.diagnoses"] == ["E11.9", "I10"]
    # _meta should be excluded
    assert "_meta.confidence" not in fields
    assert "_meta.flags" not in fields


def test_merge_results_with_consistency():
    """Test merging results with consistency logic."""
    pass1 = {
        "patient": {
            "last_name": "Doe",
            "first_name": "John",
            "phone": "555-1234",
            "ssn": None,
        },
        "_meta": {"flags": []},
    }
    pass2 = {
        "patient": {
            "last_name": "Doe",
            "first_name": "John",
            "phone": "555-5678",  # Different
            "ssn": None,
        },
        "_meta": {"flags": []},
    }

    agreed = ["patient.last_name", "patient.first_name"]
    inconsistent = [{"field": "patient.phone", "pass1_value": "555-1234", "pass2_value": "555-5678"}]
    one_sided = []

    merged = _merge_results_with_consistency(pass1, pass2, agreed, inconsistent, one_sided)

    assert merged["patient"]["last_name"] == "Doe"
    assert merged["patient"]["first_name"] == "John"
    assert merged["patient"]["phone"] is None  # Nulled out due to inconsistency
    assert "consistency_conflict_patient.phone" in merged["_meta"]["flags"]


def test_merge_results_with_one_sided_fields():
    """Test merging results with one-sided fields."""
    pass1 = {
        "patient": {
            "last_name": "Doe",
            "phone": None,
        },
        "_meta": {"flags": []},
    }
    pass2 = {
        "patient": {
            "last_name": "Doe",
            "phone": "555-1234",  # Only in pass2
        },
        "_meta": {"flags": []},
    }

    agreed = ["patient.last_name"]
    inconsistent = []
    one_sided = [{"field": "patient.phone", "value": "555-1234", "pass": 2}]

    merged = _merge_results_with_consistency(pass1, pass2, agreed, inconsistent, one_sided)

    assert merged["patient"]["last_name"] == "Doe"
    assert merged["patient"]["phone"] == "555-1234"  # Preserved from pass2
    assert "low_confidence_single_pass" in merged["_meta"]["flags"]


def test_run_consistency_check_perfect_consistency():
    """Test perfect consistency: both passes return identical results."""
    extractor = MagicMock(spec=DocumentExtractor)

    result = {
        "patient": {"last_name": "Doe", "first_name": "John"},
        "insurance": {"primary": {"insurance_name": "Medicare"}},
        "_meta": {"confidence": "HIGH", "flags": []},
    }

    response = ExtractionResponse(
        result=result,
        input_tokens=1000,
        output_tokens=500,
    )

    extractor.extract.return_value = response

    messages = [{"role": "system", "content": "test"}]

    consistency_result = run_consistency_check(extractor, messages, messages)

    assert consistency_result.consistency_score == 1.0
    assert len(consistency_result.inconsistent_fields) == 0
    assert len(consistency_result.one_sided_fields) == 0
    assert consistency_result.final_result["patient"]["last_name"] == "Doe"
    assert consistency_result.total_input_tokens == 2000  # Both passes
    assert consistency_result.total_output_tokens == 1000  # Both passes


def test_run_consistency_check_partial_inconsistency():
    """Test partial inconsistency: one field differs."""
    extractor = MagicMock(spec=DocumentExtractor)

    result1 = {
        "patient": {"last_name": "Doe", "phone": "555-1234"},
        "_meta": {"confidence": "HIGH", "flags": []},
    }
    result2 = {
        "patient": {"last_name": "Doe", "phone": "555-5678"},  # Different phone
        "_meta": {"confidence": "HIGH", "flags": []},
    }

    response1 = ExtractionResponse(result=result1, input_tokens=1000, output_tokens=500)
    response2 = ExtractionResponse(result=result2, input_tokens=1000, output_tokens=500)

    extractor.extract.side_effect = [response1, response2]

    messages = [{"role": "system", "content": "test"}]

    consistency_result = run_consistency_check(extractor, messages, messages)

    assert consistency_result.consistency_score < 1.0
    assert len(consistency_result.inconsistent_fields) == 1
    assert consistency_result.inconsistent_fields[0]["field"] == "patient.phone"
    assert consistency_result.final_result["patient"]["phone"] is None
    assert "consistency_conflict_patient.phone" in consistency_result.final_result["_meta"]["flags"]


def test_run_consistency_check_all_null():
    """Test all null (unresolved): both passes return null for a field."""
    extractor = MagicMock(spec=DocumentExtractor)

    result = {
        "patient": {"last_name": "Doe", "ssn": None},  # SSN null in both
        "_meta": {"confidence": "HIGH", "flags": []},
    }

    response = ExtractionResponse(result=result, input_tokens=1000, output_tokens=500)
    extractor.extract.return_value = response

    messages = [{"role": "system", "content": "test"}]

    consistency_result = run_consistency_check(extractor, messages, messages)

    assert "patient.ssn" in consistency_result.unresolved_fields
    assert consistency_result.final_result["patient"]["ssn"] is None
    # No flag should be added for unresolved fields
    assert "consistency_conflict_patient.ssn" not in consistency_result.final_result["_meta"]["flags"]


def test_run_consistency_check_one_sided_match():
    """Test one-sided match: one pass null, other has value."""
    extractor = MagicMock(spec=DocumentExtractor)

    result1 = {
        "patient": {"last_name": "Doe", "phone": None},
        "_meta": {"confidence": "HIGH", "flags": []},
    }
    result2 = {
        "patient": {"last_name": "Doe", "phone": "555-1234"},  # Only in pass2
        "_meta": {"confidence": "HIGH", "flags": []},
    }

    response1 = ExtractionResponse(result=result1, input_tokens=1000, output_tokens=500)
    response2 = ExtractionResponse(result=result2, input_tokens=1000, output_tokens=500)

    extractor.extract.side_effect = [response1, response2]

    messages = [{"role": "system", "content": "test"}]

    consistency_result = run_consistency_check(extractor, messages, messages)

    assert len(consistency_result.one_sided_fields) == 1
    assert consistency_result.one_sided_fields[0]["field"] == "patient.phone"
    assert consistency_result.one_sided_fields[0]["value"] == "555-1234"
    assert consistency_result.one_sided_fields[0]["pass"] == 2
    assert consistency_result.final_result["patient"]["phone"] == "555-1234"
    assert "low_confidence_single_pass" in consistency_result.final_result["_meta"]["flags"]


def test_run_consistency_check_one_sided_match_reverse():
    """Test one-sided match in reverse: pass1 has value, pass2 is null."""
    extractor = MagicMock(spec=DocumentExtractor)

    result1 = {
        "patient": {"last_name": "Doe", "phone": "555-1234"},  # Only in pass1
        "_meta": {"confidence": "HIGH", "flags": []},
    }
    result2 = {
        "patient": {"last_name": "Doe", "phone": None},
        "_meta": {"confidence": "HIGH", "flags": []},
    }

    response1 = ExtractionResponse(result=result1, input_tokens=1000, output_tokens=500)
    response2 = ExtractionResponse(result=result2, input_tokens=1000, output_tokens=500)

    extractor.extract.side_effect = [response1, response2]

    messages = [{"role": "system", "content": "test"}]

    consistency_result = run_consistency_check(extractor, messages, messages)

    assert len(consistency_result.one_sided_fields) == 1
    assert consistency_result.one_sided_fields[0]["pass"] == 1
    assert consistency_result.final_result["patient"]["phone"] == "555-1234"


def test_run_consistency_check_score_threshold(caplog):
    """Test that consistency score below threshold forces confidence to LOW."""
    import src.config as config

    extractor = MagicMock(spec=DocumentExtractor)

    # Create results that will produce a low consistency score
    result1 = {
        "patient": {"last_name": "Doe", "first_name": "John", "phone": "555-1111"},
        "insurance": {"primary": {"insurance_name": "Medicare"}},
        "_meta": {"confidence": "HIGH", "flags": []},
    }
    result2 = {
        "patient": {"last_name": "Doe", "first_name": "Jane", "phone": "555-2222"},  # Different
        "insurance": {"primary": {"insurance_name": "Medicaid"}},  # Different
        "_meta": {"confidence": "HIGH", "flags": []},
    }

    response1 = ExtractionResponse(result=result1, input_tokens=1000, output_tokens=500)
    response2 = ExtractionResponse(result=result2, input_tokens=1000, output_tokens=500)

    extractor.extract.side_effect = [response1, response2]

    messages = [{"role": "system", "content": "test"}]

    consistency_result = run_consistency_check(extractor, messages, messages)

    # Score should be low (only last_name agreed, others inconsistent)
    assert consistency_result.consistency_score < config.CONSISTENCY_THRESHOLD

    # When integrated into main.py, confidence would be forced to LOW
    # But here we just verify the score is below threshold


def test_run_consistency_check_token_accumulation():
    """Test that tokens from both passes are accumulated."""
    extractor = MagicMock(spec=DocumentExtractor)

    result = {"patient": {"last_name": "Doe"}, "_meta": {"confidence": "HIGH", "flags": []}}

    response1 = ExtractionResponse(result=result, input_tokens=1500, output_tokens=600)
    response2 = ExtractionResponse(result=result, input_tokens=1200, output_tokens=550)

    extractor.extract.side_effect = [response1, response2]

    messages = [{"role": "system", "content": "test"}]

    consistency_result = run_consistency_check(extractor, messages, messages)

    assert consistency_result.total_input_tokens == 2700  # 1500 + 1200
    assert consistency_result.total_output_tokens == 1150  # 600 + 550


def test_run_consistency_check_phi_not_in_logs(caplog):
    """Test that PHI never appears in log output."""
    extractor = MagicMock(spec=DocumentExtractor)

    result1 = {
        "patient": {
            "last_name": "Smith",
            "first_name": "John",
            "ssn": "123-45-6789",
            "date_of_birth": "1980-01-15",
            "phone": "555-1234",
        },
        "_meta": {"confidence": "HIGH", "flags": []},
    }
    result2 = {
        "patient": {
            "last_name": "Smith",
            "first_name": "John",
            "ssn": "123-45-6789",
            "date_of_birth": "1980-01-15",
            "phone": "555-5678",  # Different
        },
        "_meta": {"confidence": "HIGH", "flags": []},
    }

    response1 = ExtractionResponse(result=result1, input_tokens=1000, output_tokens=500)
    response2 = ExtractionResponse(result=result2, input_tokens=1000, output_tokens=500)

    extractor.extract.side_effect = [response1, response2]

    messages = [{"role": "system", "content": "test"}]

    consistency_result = run_consistency_check(extractor, messages, messages)

    # Check log output
    log_text = caplog.text

    # Field names should appear
    assert "patient.phone" in log_text

    # But PHI values should NOT appear
    phi_strings = ["123-45-6789", "1980-01-15", "Smith", "John", "555-1234", "555-5678"]
    for phi in phi_strings:
        assert phi not in log_text, f"PHI value '{phi}' found in log output"

    # Also check that base64 doesn't appear (though it shouldn't be in these logs anyway)
    assert "base64" not in log_text.lower()


def test_run_consistency_check_nested_fields():
    """Test that nested fields are compared separately."""
    extractor = MagicMock(spec=DocumentExtractor)

    result1 = {
        "insurance": {
            "primary": {
                "insurance_name": "Medicare",
                "policy_number": "123456",
            },
        },
        "_meta": {"confidence": "HIGH", "flags": []},
    }
    result2 = {
        "insurance": {
            "primary": {
                "insurance_name": "Medicare",  # Same
                "policy_number": "789012",  # Different
            },
        },
        "_meta": {"confidence": "HIGH", "flags": []},
    }

    response1 = ExtractionResponse(result=result1, input_tokens=1000, output_tokens=500)
    response2 = ExtractionResponse(result=result2, input_tokens=1000, output_tokens=500)

    extractor.extract.side_effect = [response1, response2]

    messages = [{"role": "system", "content": "test"}]

    consistency_result = run_consistency_check(extractor, messages, messages)

    # insurance_name should be agreed
    assert "insurance.primary.insurance_name" in consistency_result.agreed_fields
    # policy_number should be inconsistent
    assert len(consistency_result.inconsistent_fields) == 1
    assert consistency_result.inconsistent_fields[0]["field"] == "insurance.primary.policy_number"


def test_run_consistency_check_list_fields():
    """Test that list fields (like diagnoses) are compared correctly."""
    extractor = MagicMock(spec=DocumentExtractor)

    result1 = {
        "clinical": {"diagnoses": ["E11.9", "I10"]},
        "_meta": {"confidence": "HIGH", "flags": []},
    }
    result2 = {
        "clinical": {"diagnoses": ["E11.9", "I10"]},  # Same list
        "_meta": {"confidence": "HIGH", "flags": []},
    }

    response1 = ExtractionResponse(result=result1, input_tokens=1000, output_tokens=500)
    response2 = ExtractionResponse(result=result2, input_tokens=1000, output_tokens=500)

    extractor.extract.side_effect = [response1, response2]

    messages = [{"role": "system", "content": "test"}]

    consistency_result = run_consistency_check(extractor, messages, messages)

    assert "clinical.diagnoses" in consistency_result.agreed_fields


def test_run_consistency_check_list_fields_different():
    """Test that different list contents are detected as inconsistent."""
    extractor = MagicMock(spec=DocumentExtractor)

    result1 = {
        "clinical": {"diagnoses": ["E11.9", "I10"]},
        "_meta": {"confidence": "HIGH", "flags": []},
    }
    result2 = {
        "clinical": {"diagnoses": ["E11.9", "I20"]},  # Different
        "_meta": {"confidence": "HIGH", "flags": []},
    }

    response1 = ExtractionResponse(result=result1, input_tokens=1000, output_tokens=500)
    response2 = ExtractionResponse(result=result2, input_tokens=1000, output_tokens=500)

    extractor.extract.side_effect = [response1, response2]

    messages = [{"role": "system", "content": "test"}]

    consistency_result = run_consistency_check(extractor, messages, messages)

    assert "clinical.diagnoses" in [c["field"] for c in consistency_result.inconsistent_fields]
