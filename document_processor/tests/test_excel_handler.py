"""Unit tests for excel_handler module."""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.excel_handler import WorkbookLockedError, append_to_workbook


def test_file_lock_acquisition(tmp_path):
    """Test that file lock is acquired and workbook is written."""
    workbook_path = tmp_path / "test.xlsx"
    result = {
        "patient": {"first_name": "John", "last_name": "Doe"},
        "insurance": {"primary": {"insurance_name": "Medicare"}, "secondary": {}},
        "clinical": {"rendering_facility": "Test", "diagnoses": []},
        "_meta": {"confidence": "HIGH", "conflicts": [], "flags": []},
    }

    # Should succeed with lock
    output_path = append_to_workbook(result, "test.pdf", str(workbook_path))
    assert output_path == workbook_path
    assert workbook_path.exists()


def test_lock_timeout_raises_error(tmp_path):
    """Test that lock timeout raises WorkbookLockedError."""
    workbook_path = tmp_path / "test.xlsx"
    result = {
        "patient": {"first_name": "John"},
        "insurance": {"primary": {}, "secondary": {}},
        "clinical": {},
        "_meta": {"confidence": "HIGH", "conflicts": [], "flags": []},
    }

    from filelock import Timeout

    with patch("src.excel_handler.FileLock") as mock_lock_class:
        mock_lock = MagicMock()
        mock_lock_class.return_value = mock_lock
        mock_lock.__enter__.side_effect = Timeout("Lock timeout")

        with pytest.raises(WorkbookLockedError, match="Cannot acquire lock"):
            append_to_workbook(result, "test.pdf", str(workbook_path))
