"""Unit tests for fingerprint module."""

import json
import tempfile
from pathlib import Path

import pytest

from src.fingerprint import compute_fingerprint, load_processed_log, save_processed_log


def test_compute_fingerprint_deterministic(tmp_path):
    """Test that same file content returns same hash."""
    test_file = tmp_path / "test.txt"
    test_file.write_text("test content")

    fp1 = compute_fingerprint(str(test_file))
    fp2 = compute_fingerprint(str(test_file))

    assert fp1 == fp2
    assert len(fp1) == 64  # SHA-256 hex is 64 chars


def test_compute_fingerprint_different(tmp_path):
    """Test that different content returns different hash."""
    file1 = tmp_path / "file1.txt"
    file1.write_text("content one")

    file2 = tmp_path / "file2.txt"
    file2.write_text("content two")

    fp1 = compute_fingerprint(str(file1))
    fp2 = compute_fingerprint(str(file2))

    assert fp1 != fp2


def test_load_processed_log_missing_file(tmp_path):
    """Test that missing log file returns empty set."""
    log_path = tmp_path / "nonexistent.json"
    result = load_processed_log(str(log_path))
    assert result == set()


def test_load_processed_log_round_trip(tmp_path):
    """Test save and load round-trip."""
    log_path = tmp_path / "processed_files.json"
    fingerprints = {"abc123", "def456", "ghi789"}

    save_processed_log(str(log_path), fingerprints)
    loaded = load_processed_log(str(log_path))

    assert loaded == fingerprints


def test_load_processed_log_invalid_json(tmp_path):
    """Test that invalid JSON returns empty set."""
    log_path = tmp_path / "invalid.json"
    log_path.write_text("not valid json {")

    result = load_processed_log(str(log_path))
    assert result == set()
