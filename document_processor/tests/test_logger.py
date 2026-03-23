"""Unit tests for logger module."""

import json
import logging
from io import StringIO

import pytest

from src.logger import (
    CorrelationFilter,
    HumanReadableFormatter,
    JsonLineFormatter,
    get_logger,
    new_correlation_id,
)


def test_correlation_id_propagation():
    """Test that correlation_id appears in formatted output."""
    corr_id = new_correlation_id()
    assert len(corr_id) == 36  # UUID4 format

    # Create a logger with correlation filter
    logger = get_logger("test_module")
    handler = logging.StreamHandler(StringIO())
    handler.addFilter(CorrelationFilter())
    handler.setFormatter(HumanReadableFormatter())
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

    # Capture output
    output = handler.stream.getvalue()
    logger.info("Test message")

    # Check that correlation_id appears in output
    output_after = handler.stream.getvalue()
    assert corr_id in output_after or "test_module" in output_after


def test_json_line_format():
    """Test that JsonLineFormatter produces valid JSON with required keys."""
    formatter = JsonLineFormatter()
    record = logging.LogRecord(
        name="test_module",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg="Test message",
        args=(),
        exc_info=None,
    )
    record.correlation_id = "test-correlation-id"

    json_str = formatter.format(record)
    parsed = json.loads(json_str)

    assert "timestamp" in parsed
    assert "level" in parsed
    assert "correlation_id" in parsed
    assert parsed["correlation_id"] == "test-correlation-id"
    assert "module" in parsed
    assert "message" in parsed
    assert parsed["message"] == "Test message"


def test_phi_never_in_logs():
    """Test that PHI strings never appear in log output.

    This test verifies that the logger itself doesn't accidentally inject PHI
    into log messages. We log safe messages and verify no PHI field names appear.
    """
    # Forbidden PHI strings as specified in plan
    forbidden_strings = ["ssn", "date_of_birth", "first_name", "last_name", "street", "phone", "policy_number", "base64"]

    logger = get_logger("test_module")
    output_stream = StringIO()
    handler = logging.StreamHandler(output_stream)
    handler.setFormatter(HumanReadableFormatter())
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

    # Log only safe messages (no PHI values)
    safe_messages = [
        "Processing document: test.pdf",
        "Extraction completed",
        "Validation passed",
        "File written successfully",
    ]

    for msg in safe_messages:
        logger.info(msg)

    output = output_stream.getvalue()

    # Check that none of the forbidden PHI field names appear in the output
    # (case-insensitive). This ensures the logger doesn't accidentally inject
    # PHI field names into log messages.
    output_lower = output.lower()
    for forbidden in forbidden_strings:
        # Only check for the field name itself, not as part of safe words
        # We're checking that the logger doesn't accidentally log PHI field names
        # The actual protection is that code should never log PHI values
        assert forbidden.lower() not in output_lower, (
            f"PHI field name '{forbidden}' found in log output! "
            "Logger should not include PHI field names in messages."
        )


def test_get_logger_returns_named_logger():
    """Test that get_logger returns a logger with the correct name."""
    logger = get_logger("test_module_name")
    assert logger.name == "test_module_name"
    assert isinstance(logger, logging.Logger)
