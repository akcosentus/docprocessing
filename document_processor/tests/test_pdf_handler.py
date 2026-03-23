"""Unit tests for pdf_handler module."""

import base64
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from PIL import Image, ImageDraw

from src.pdf_handler import (
    CorruptFileError,
    PasswordProtectedError,
    UnsupportedFormatError,
    process_document,
    extract_ocr_text,
)


def test_process_image_jpeg(tmp_path):
    """Test processing a JPEG image."""
    # Create a test JPEG image
    img = Image.new("RGB", (300, 300), color="red")
    img_path = tmp_path / "test.jpg"
    img.save(img_path, "JPEG")

    results = process_document(img_path)

    assert len(results) == 1
    assert results[0]["page_number"] == 1
    assert results[0]["total_pages"] == 1
    assert results[0]["media_type"] == "image"
    assert "base64_image" in results[0]
    # Verify it's valid base64
    base64.b64decode(results[0]["base64_image"])


def test_process_image_png(tmp_path):
    """Test processing a PNG image (should be converted to JPEG)."""
    img = Image.new("RGB", (300, 300), color="blue")
    img_path = tmp_path / "test.png"
    img.save(img_path, "PNG")

    results = process_document(img_path)

    assert len(results) == 1
    assert results[0]["media_type"] == "image"


def test_process_image_too_small(tmp_path):
    """Test that images below minimum resolution raise an error."""
    img = Image.new("RGB", (100, 100), color="red")  # Too small
    img_path = tmp_path / "test.jpg"
    img.save(img_path, "JPEG")

    with pytest.raises(ValueError, match="resolution too low"):
        process_document(img_path)


def test_process_document_file_not_found():
    """Test error handling for non-existent file."""
    with pytest.raises(FileNotFoundError):
        process_document("/nonexistent/file.pdf")


def test_process_document_unsupported_format(tmp_path):
    """Test error handling for unsupported file format."""
    unsupported_file = tmp_path / "test.txt"
    unsupported_file.write_text("Not an image or PDF")

    with pytest.raises(UnsupportedFormatError):
        process_document(unsupported_file)


def test_process_document_corrupt_image(tmp_path):
    """Test error handling for corrupt image file."""
    corrupt_file = tmp_path / "corrupt.jpg"
    corrupt_file.write_bytes(b"Not a valid image file")

    with pytest.raises(CorruptFileError):
        process_document(corrupt_file)


def test_process_document_includes_pil_image(tmp_path):
    """Test that process_document includes PIL Image in return dict."""
    img = Image.new("RGB", (300, 300), color="red")
    img_path = tmp_path / "test.jpg"
    img.save(img_path, "JPEG")

    results = process_document(img_path)

    assert len(results) == 1
    assert "pil_image" in results[0]
    assert isinstance(results[0]["pil_image"], Image.Image)


def test_extract_ocr_text_success(caplog):
    """Test successful OCR extraction."""
    # Create PIL Image with text
    img = Image.new("RGB", (300, 300), color="white")
    draw = ImageDraw.Draw(img)
    draw.text((10, 10), "Sample Text", fill="black")

    with patch("src.pdf_handler.pytesseract") as mock_tesseract:
        mock_tesseract.image_to_string.return_value = "Sample Text"
        result = extract_ocr_text(img)

    assert result == "Sample Text"
    assert "OCR" not in caplog.text or "WARNING" not in caplog.text


def test_extract_ocr_text_failure_tesseract_not_found(caplog):
    """Test OCR failure when Tesseract is not found."""
    img = Image.new("RGB", (300, 300), color="white")

    # Create a mock exception class for TesseractNotFoundError
    class MockTesseractNotFoundError(Exception):
        pass

    with patch("src.pdf_handler.pytesseract") as mock_tesseract, \
         patch("src.pdf_handler.TesseractNotFoundError", MockTesseractNotFoundError):
        mock_tesseract.image_to_string.side_effect = MockTesseractNotFoundError("Tesseract not found")
        result = extract_ocr_text(img)

    assert result == ""
    assert "WARNING" in caplog.text
    assert "Tesseract OCR not found" in caplog.text


def test_extract_ocr_text_failure_generic_exception(caplog):
    """Test OCR failure with generic exception."""
    img = Image.new("RGB", (300, 300), color="white")

    # Create separate exception classes
    class MockTesseractNotFoundError(Exception):
        pass

    class MockGenericError(Exception):
        pass

    with patch("src.pdf_handler.pytesseract") as mock_tesseract, \
         patch("src.pdf_handler.TesseractNotFoundError", MockTesseractNotFoundError):
        # Raise a generic exception that is NOT TesseractNotFoundError
        mock_tesseract.image_to_string.side_effect = MockGenericError("OCR error")
        result = extract_ocr_text(img)

    assert result == ""
    assert "WARNING" in caplog.text
    assert "OCR extraction failed" in caplog.text


def test_extract_ocr_text_empty_output(caplog):
    """Test OCR returns empty string when output is empty."""
    img = Image.new("RGB", (300, 300), color="white")

    with patch("src.pdf_handler.pytesseract") as mock_tesseract:
        mock_tesseract.image_to_string.return_value = ""
        result = extract_ocr_text(img)

    assert result == ""
    assert "WARNING" in caplog.text
    assert "OCR returned empty text" in caplog.text


def test_extract_ocr_text_pytesseract_not_installed(caplog):
    """Test OCR when pytesseract is not installed."""
    img = Image.new("RGB", (300, 300), color="white")

    with patch("src.pdf_handler.pytesseract", None):
        result = extract_ocr_text(img)

    assert result == ""
    assert "WARNING" in caplog.text
    assert "pytesseract not installed" in caplog.text
