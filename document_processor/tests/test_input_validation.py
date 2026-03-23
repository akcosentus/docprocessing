"""Unit tests for input file validation."""

import os
import tempfile
from pathlib import Path

import pytest
from PIL import Image

from src.pdf_handler import (
    CorruptFileError,
    FileTooLargeError,
    UnsupportedFormatError,
    validate_input_file,
)


def test_validate_input_file_valid_pdf(tmp_path):
    """Test that a valid PDF passes validation."""
    # Create a minimal valid PDF using PyMuPDF
    import fitz

    pdf_path = tmp_path / "test.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 50), "Test PDF")
    doc.save(str(pdf_path))
    doc.close()

    result = validate_input_file(str(pdf_path), max_size_mb=50)
    assert result == pdf_path.resolve()


def test_validate_input_file_nonexistent():
    """Test that nonexistent file raises FileNotFoundError."""
    with pytest.raises(FileNotFoundError):
        validate_input_file("/nonexistent/file.pdf", max_size_mb=50)


def test_validate_input_file_directory(tmp_path):
    """Test that directory path raises FileNotFoundError."""
    dir_path = tmp_path / "adir"
    dir_path.mkdir()

    with pytest.raises(FileNotFoundError, match="not a file"):
        validate_input_file(str(dir_path), max_size_mb=50)


def test_validate_input_file_unsupported_extension(tmp_path):
    """Test that unsupported extension raises UnsupportedFormatError."""
    txt_file = tmp_path / "test.txt"
    txt_file.write_text("not an image or PDF")

    with pytest.raises(UnsupportedFormatError):
        validate_input_file(str(txt_file), max_size_mb=50)


def test_validate_input_file_too_large(tmp_path):
    """Test that oversized file raises FileTooLargeError."""
    # Create a file larger than 1 MB limit
    large_file = tmp_path / "large.pdf"
    # Write 2 MB of data
    with open(large_file, "wb") as f:
        f.write(b"x" * (2 * 1024 * 1024))

    with pytest.raises(FileTooLargeError, match="exceeds maximum"):
        validate_input_file(str(large_file), max_size_mb=1)


def test_validate_input_file_unreadable(tmp_path):
    """Test that unreadable file raises PermissionError (skip on Windows)."""
    import sys

    if sys.platform == "win32":
        pytest.skip("Permission test not reliable on Windows")

    test_file = tmp_path / "test.jpg"
    img = Image.new("RGB", (300, 300), color="red")
    img.save(test_file, "JPEG")

    # Remove read permission
    os.chmod(test_file, 0o000)
    try:
        with pytest.raises(PermissionError, match="not readable"):
            validate_input_file(str(test_file), max_size_mb=50)
    finally:
        # Restore permission for cleanup
        os.chmod(test_file, 0o644)


def test_validate_input_file_corrupt_pdf(tmp_path):
    """Test that corrupt PDF raises CorruptFileError."""
    corrupt_pdf = tmp_path / "corrupt.pdf"
    corrupt_pdf.write_bytes(b"Not a valid PDF file content")

    with pytest.raises(CorruptFileError):
        validate_input_file(str(corrupt_pdf), max_size_mb=50)
