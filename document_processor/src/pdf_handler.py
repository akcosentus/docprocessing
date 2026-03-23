"""PDF and image file handling, conversion to base64-encoded JPEG images."""

import base64
import os
from io import BytesIO
from pathlib import Path
from typing import List, Dict, Any, Union, Optional

import fitz  # PyMuPDF
from PIL import Image

try:
    import pytesseract
    from pytesseract import TesseractNotFoundError
except ImportError:
    pytesseract = None
    TesseractNotFoundError = Exception

from src.logger import get_logger

logger = get_logger(__name__)

# Supported file extensions for batch processing (lowercase, with dot)
SUPPORTED_EXTENSIONS = {".pdf", ".jpeg", ".jpg", ".png", ".tiff", ".tif"}


class CorruptFileError(Exception):
    """Raised when a file is corrupted and cannot be read."""

    pass


class PasswordProtectedError(Exception):
    """Raised when a PDF is password-protected."""

    pass


class UnsupportedFormatError(Exception):
    """Raised when a file format is not supported."""

    pass


class FileTooLargeError(Exception):
    """Raised when a file exceeds the maximum allowed size."""

    pass


def validate_input_file(path: Union[str, Path], max_size_mb: int) -> Path:
    """
    Validate an input file before processing.

    Checks:
    - Path exists and is a file (not directory) -> FileNotFoundError
    - Extension in allowed set (case-insensitive) -> UnsupportedFormatError
    - File size under max_size_mb -> FileTooLargeError
    - File is readable (os.access R_OK check) -> PermissionError
    - For PDFs: attempt fitz.open() to verify valid PDF -> CorruptFileError

    Args:
        path: File path to validate.
        max_size_mb: Maximum file size in megabytes (from config).

    Returns:
        Resolved Path object.

    Raises:
        FileNotFoundError, UnsupportedFormatError, FileTooLargeError,
        PermissionError, CorruptFileError
    """
    file_path = Path(path).resolve()
    logger.debug(f"Validating input file: {file_path}")

    # Check if path exists
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    # Check if it's a file (not a directory)
    if not file_path.is_file():
        raise FileNotFoundError(f"Path is not a file: {file_path}")

    # Check extension
    suffix = file_path.suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise UnsupportedFormatError(
            f"Unsupported file format: {suffix}. "
            f"Supported types: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
        )

    # Check file size
    file_size_bytes = file_path.stat().st_size
    file_size_mb = file_size_bytes / (1024 * 1024)
    if file_size_mb > max_size_mb:
        raise FileTooLargeError(
            f"File size {file_size_mb:.2f} MB exceeds maximum allowed size "
            f"of {max_size_mb} MB: {file_path}"
        )

    # Check if file is readable
    if not os.access(file_path, os.R_OK):
        raise PermissionError(f"File is not readable: {file_path}")

    # For PDFs, attempt to open with fitz to verify it's a valid PDF
    if suffix == ".pdf":
        try:
            doc = fitz.open(file_path)
            doc.close()
        except Exception as e:
            if "password" in str(e).lower() or "encrypted" in str(e).lower():
                # Password-protected PDFs will be caught later in process_document
                # but we can validate the file structure is valid
                pass
            else:
                raise CorruptFileError(
                    f"PDF file is corrupted or cannot be opened: {file_path}"
                ) from e

    logger.debug(f"File validation passed: {file_path}")
    return file_path


def process_document(file_path: Union[str, Path]) -> List[Dict[str, Any]]:
    """
    Process a PDF or image file, converting it to base64-encoded JPEG images.

    Args:
        file_path: Path to the PDF or image file (JPEG, PNG, TIFF)

    Returns:
        List of dictionaries, each containing:
        - "base64_image": base64-encoded JPEG string
        - "page_number": 1-indexed page number
        - "total_pages": total number of pages
        - "media_type": "pdf" or "image"
        - "pil_image": PIL Image object (optional, for OCR use)

    Raises:
        FileNotFoundError: If the file does not exist
        CorruptFileError: If the file is corrupted
        PasswordProtectedError: If the PDF is password-protected
        UnsupportedFormatError: If the file format is not supported
    """
    logger.debug(f"Starting document processing: {file_path}")
    file_path = Path(file_path)

    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    # Detect file type
    suffix = file_path.suffix.lower()

    if suffix == ".pdf":
        result = _process_pdf(file_path)
        logger.debug(f"Processed PDF: {len(result)} page(s)")
        return result
    elif suffix in [".jpg", ".jpeg", ".png", ".tiff", ".tif"]:
        result = _process_image(file_path)
        logger.debug(f"Processed image: {suffix}")
        return result
    else:
        logger.error(f"Unsupported file format: {suffix}")
        raise UnsupportedFormatError(
            f"Unsupported file format: {suffix}. Supported formats: PDF, JPEG, PNG, TIFF"
        )


def _process_pdf(file_path: Path) -> List[Dict[str, Any]]:
    """
    Convert PDF pages to base64-encoded JPEG images at 300 DPI.

    Args:
        file_path: Path to the PDF file

    Returns:
        List of dictionaries with base64 images and metadata

    Raises:
        CorruptFileError: If the PDF is corrupted
        PasswordProtectedError: If the PDF is password-protected
    """
    try:
        doc = fitz.open(file_path)
    except Exception as e:
        if "password" in str(e).lower() or "encrypted" in str(e).lower():
            raise PasswordProtectedError(f"PDF is password-protected: {file_path}") from e
        raise CorruptFileError(f"PDF file is corrupted or cannot be opened: {file_path}") from e

    # Check if password-protected (needs authentication)
    if doc.is_encrypted:
        doc.close()
        raise PasswordProtectedError(f"PDF is password-protected: {file_path}")

    total_pages = len(doc)
    results = []

    # Matrix for 300 DPI: 300/72 = 4.1667
    zoom = 300 / 72
    matrix = fitz.Matrix(zoom, zoom)

    try:
        for page_num in range(total_pages):
            page = doc[page_num]

            # Render page to pixmap at 300 DPI
            pix = page.get_pixmap(matrix=matrix)
            img_data = pix.tobytes("jpeg")

            # Convert to base64
            base64_image = base64.b64encode(img_data).decode("utf-8")

            # Store PIL Image for OCR (avoids base64 roundtrip)
            pil_image = Image.open(BytesIO(img_data))

            results.append({
                "base64_image": base64_image,
                "page_number": page_num + 1,
                "total_pages": total_pages,
                "media_type": "pdf",
                "pil_image": pil_image,
            })
    finally:
        doc.close()

    return results


def _process_image(file_path: Path) -> List[Dict[str, Any]]:
    """
    Normalize image to JPEG format and convert to base64.

    Args:
        file_path: Path to the image file

    Returns:
        List containing a single dictionary with base64 image and metadata

    Raises:
        CorruptFileError: If the image is corrupted
    """
    try:
        img = Image.open(file_path)
    except Exception as e:
        raise CorruptFileError(f"Image file is corrupted or cannot be opened: {file_path}") from e

    # Verify minimum resolution for OCR-quality (at least 200x200 pixels)
    width, height = img.size
    if width < 200 or height < 200:
        raise ValueError(
            f"Image resolution too low for OCR-quality extraction: {width}x{height}. "
            "Minimum required: 200x200 pixels"
        )

    # Convert to RGB if necessary (handles RGBA, P, etc.)
    if img.mode != "RGB":
        img = img.convert("RGB")

    # Save to JPEG in memory for base64 encoding
    buffer = BytesIO()
    img.save(buffer, format="JPEG", quality=95)
    img_data = buffer.getvalue()

    # Convert to base64
    base64_image = base64.b64encode(img_data).decode("utf-8")

    # Store PIL Image for OCR (avoids base64 roundtrip)
    # Note: img is already in RGB mode, ready for OCR - use it directly
    pil_image = img.copy()  # Use the already-converted RGB image

    return [{
        "base64_image": base64_image,
        "page_number": 1,
        "total_pages": 1,
        "media_type": "image",
        "pil_image": pil_image,
    }]


def extract_ocr_text(image: Image.Image) -> str:
    """
    Extract raw text from a PIL Image using Tesseract OCR.

    Runs fully locally - no data leaves the machine during OCR.
    If OCR fails or produces empty output, returns empty string and logs WARNING.
    OCR failure is non-fatal - extraction continues with image only.

    Args:
        image: PIL Image object (RGB mode, already validated for resolution)

    Returns:
        Raw OCR text as string, or empty string if OCR fails

    Note:
        Requires Tesseract to be installed locally (brew install tesseract on Mac).
        If pytesseract cannot find Tesseract, returns empty string and logs WARNING.
    """
    if pytesseract is None:
        logger.warning("pytesseract not installed - OCR disabled. Install with: pip install pytesseract")
        return ""

    try:
        ocr_text = pytesseract.image_to_string(image)
        if not ocr_text or not ocr_text.strip():
            logger.warning("OCR returned empty text - continuing with image-only extraction")
            return ""
        return ocr_text.strip()
    except TesseractNotFoundError:
        logger.warning(
            "Tesseract OCR not found on system - OCR disabled. "
            "Install Tesseract: brew install tesseract (Mac) or apt-get install tesseract-ocr (Linux)"
        )
        return ""
    except Exception as e:
        logger.warning(f"OCR extraction failed: {e} - continuing with image-only extraction")
        return ""
