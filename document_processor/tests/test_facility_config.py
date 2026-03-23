"""Unit tests for facility_config module."""

import json
import tempfile
from pathlib import Path

import pytest

from src.facility_config import FacilityConfig, FacilityNotFoundError


def test_get_facility_success():
    """Test successful facility retrieval."""
    # Create temporary config file
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        config_data = {
            "test_facility": {
                "display_name": "Test Facility",
                "overrides": ["rule1", "rule2"],
            }
        }
        json.dump(config_data, f)
        config_path = Path(f.name)

    try:
        config = FacilityConfig(config_path=config_path)
        facility = config.get_facility("test_facility")

        assert facility["display_name"] == "Test Facility"
        assert facility["overrides"] == ["rule1", "rule2"]
    finally:
        config_path.unlink()


def test_get_facility_not_found():
    """Test FacilityNotFoundError when facility ID doesn't exist."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        config_data = {"other_facility": {"display_name": "Other", "overrides": []}}
        json.dump(config_data, f)
        config_path = Path(f.name)

    try:
        config = FacilityConfig(config_path=config_path)
        with pytest.raises(FacilityNotFoundError) as exc_info:
            config.get_facility("nonexistent")
        assert "nonexistent" in str(exc_info.value)
    finally:
        config_path.unlink()


def test_load_config_invalid_json():
    """Test error handling for invalid JSON."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        f.write("invalid json content {")
        config_path = Path(f.name)

    try:
        with pytest.raises(ValueError, match="Invalid JSON"):
            FacilityConfig(config_path=config_path)
    finally:
        config_path.unlink()


def test_load_config_file_not_found():
    """Test error handling for missing config file."""
    nonexistent_path = Path("/nonexistent/path/facilities.json")
    with pytest.raises(FileNotFoundError):
        FacilityConfig(config_path=nonexistent_path)
