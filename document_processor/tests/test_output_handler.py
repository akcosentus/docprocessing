"""Unit tests for output_handler module."""

import json
import tempfile
from pathlib import Path

import pytest

from src.output_handler import _estimate_cost, write_run_report


def test_write_run_report_creates_file(tmp_path):
    """Test that write_run_report creates a file with correct keys."""
    report = {
        "run_id": "test-run-id",
        "timestamp": "2024-01-01T00:00:00",
        "total_files": 5,
        "succeeded": 4,
        "failed": 1,
        "routed_to_review": 2,
        "files_skipped_duplicate": 0,
        "total_input_tokens": 1000,
        "total_output_tokens": 500,
        "estimated_cost_usd": 0.005,
        "per_file_summary": [
            {
                "filename": "test.pdf",
                "facility_id": "test_facility",
                "confidence": "HIGH",
                "flags": [],
                "status": "succeeded",
            }
        ],
    }

    output_path = write_run_report(report, str(tmp_path))
    assert output_path.exists()
    assert output_path.name.startswith("run_report_")

    # Verify contents
    with open(output_path, "r", encoding="utf-8") as f:
        loaded = json.load(f)

    assert loaded["run_id"] == "test-run-id"
    assert loaded["total_files"] == 5
    assert "per_file_summary" in loaded


def test_cost_calculation():
    """Test that cost calculation produces expected USD value."""
    # 1M input tokens at $2.50/M = $2.50
    # 500K output tokens at $10.00/M = $5.00
    # Total = $7.50
    cost = _estimate_cost(1_000_000, 500_000)
    assert abs(cost - 7.50) < 0.01

    # Small amounts
    cost_small = _estimate_cost(1000, 500)
    expected = (1000 / 1_000_000) * 2.50 + (500 / 1_000_000) * 10.00
    assert abs(cost_small - expected) < 0.0001
