"""Unit tests for prompts module."""

from src.prompts import build_messages_for_extraction


def test_build_messages_for_extraction_with_ocr_text():
    """Test that OCR text is included in message when provided."""
    base64_image = "fake_base64_string"
    facility_name = "Test Facility"
    ocr_text = "Sample OCR text from document"

    messages = build_messages_for_extraction(
        base64_image=base64_image,
        facility_name=facility_name,
        ocr_text=ocr_text,
    )

    assert len(messages) == 2
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"
    
    user_content = messages[1]["content"]
    assert len(user_content) == 2
    assert user_content[0]["type"] == "text"
    assert user_content[1]["type"] == "image_url"
    
    text_content = user_content[0]["text"]
    assert "RAW OCR TEXT FROM DOCUMENT" in text_content
    assert ocr_text in text_content
    assert facility_name in text_content
    # OCR text should appear before the user prompt
    assert text_content.index(ocr_text) < text_content.index(facility_name)


def test_build_messages_for_extraction_without_ocr_text():
    """Test that message structure is unchanged when OCR text is not provided."""
    base64_image = "fake_base64_string"
    facility_name = "Test Facility"

    messages = build_messages_for_extraction(
        base64_image=base64_image,
        facility_name=facility_name,
        ocr_text=None,
    )

    assert len(messages) == 2
    user_content = messages[1]["content"]
    text_content = user_content[0]["text"]
    
    assert "RAW OCR TEXT FROM DOCUMENT" not in text_content
    assert facility_name in text_content


def test_build_messages_for_extraction_with_empty_ocr_text():
    """Test that empty OCR text is treated same as None."""
    base64_image = "fake_base64_string"
    facility_name = "Test Facility"

    messages = build_messages_for_extraction(
        base64_image=base64_image,
        facility_name=facility_name,
        ocr_text="",
    )

    assert len(messages) == 2
    user_content = messages[1]["content"]
    text_content = user_content[0]["text"]
    
    assert "RAW OCR TEXT FROM DOCUMENT" not in text_content
    assert facility_name in text_content


def test_build_messages_for_extraction_with_whitespace_only_ocr_text():
    """Test that whitespace-only OCR text is treated same as empty."""
    base64_image = "fake_base64_string"
    facility_name = "Test Facility"

    messages = build_messages_for_extraction(
        base64_image=base64_image,
        facility_name=facility_name,
        ocr_text="   \n\t  ",
    )

    assert len(messages) == 2
    user_content = messages[1]["content"]
    text_content = user_content[0]["text"]
    
    assert "RAW OCR TEXT FROM DOCUMENT" not in text_content
    assert facility_name in text_content
