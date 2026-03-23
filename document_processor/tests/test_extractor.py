"""Unit tests for extractor module."""

from unittest.mock import MagicMock, patch

import pytest

from src.extractor import DocumentExtractor, ExtractionError, ExtractionResponse
from src.schemas import ExtractionResult, Patient, Meta


@pytest.fixture
def mock_openai_client():
    """Create a mock OpenAI client."""
    with patch("src.extractor.OpenAI") as mock_client_class:
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        yield mock_client


@pytest.fixture
def extractor(mock_openai_client):
    """Create an extractor instance with mocked OpenAI client."""
    with patch("src.config.OPENAI_API_KEY", "test-key"), \
         patch("src.config.OPENAI_ORG_ID", ""):
        return DocumentExtractor()


def _make_parsed_result(**patient_kwargs) -> ExtractionResult:
    """Helper to build a valid ExtractionResult with minimal overrides."""
    return ExtractionResult(
        patient=Patient(**patient_kwargs),
        _meta=Meta(confidence="HIGH"),
    )


def test_extract_success(extractor, mock_openai_client):
    """Test successful extraction via Structured Outputs."""
    parsed_obj = _make_parsed_result(first_name="John", last_name="Doe")

    mock_message = MagicMock()
    mock_message.refusal = None
    mock_message.parsed = parsed_obj

    mock_response = MagicMock()
    mock_response.choices = [MagicMock(message=mock_message)]

    mock_usage = MagicMock()
    mock_usage.prompt_tokens = 100
    mock_usage.completion_tokens = 50
    mock_response.usage = mock_usage
    mock_openai_client.beta.chat.completions.parse.return_value = mock_response

    messages = [{"role": "user", "content": "test"}]
    response = extractor.extract(messages)

    assert isinstance(response, ExtractionResponse)
    assert response.input_tokens == 100
    assert response.output_tokens == 50
    result = response.result
    assert result["patient"]["first_name"] == "John"
    assert result["patient"]["last_name"] == "Doe"
    assert "_meta" in result
    assert result["_meta"]["confidence"] == "HIGH"

    mock_openai_client.beta.chat.completions.parse.assert_called_once()
    call_kwargs = mock_openai_client.beta.chat.completions.parse.call_args[1]
    assert call_kwargs["store"] is False, "store must be False for PHI safety"
    assert call_kwargs["temperature"] == 0
    assert call_kwargs["model"] == "gpt-4o-2024-11-20", "model must be gpt-4o-2024-11-20"
    assert call_kwargs["response_format"] is ExtractionResult


def test_extract_refusal(extractor, mock_openai_client):
    """Test that a model refusal raises ExtractionError."""
    mock_message = MagicMock()
    mock_message.refusal = "I cannot process this image."
    mock_message.parsed = None

    mock_response = MagicMock()
    mock_response.choices = [MagicMock(message=mock_message)]
    mock_response.usage = None

    mock_openai_client.beta.chat.completions.parse.return_value = mock_response

    messages = [{"role": "user", "content": "test"}]
    with pytest.raises(ExtractionError, match="Model refused the request"):
        extractor.extract(messages)


def test_extract_none_parsed(extractor, mock_openai_client):
    """Test error handling when parsed result is None."""
    mock_message = MagicMock()
    mock_message.refusal = None
    mock_message.parsed = None

    mock_response = MagicMock()
    mock_response.choices = [MagicMock(message=mock_message)]
    mock_response.usage = None

    mock_openai_client.beta.chat.completions.parse.return_value = mock_response

    messages = [{"role": "user", "content": "test"}]
    with pytest.raises(ExtractionError, match="Parsed response is None"):
        extractor.extract(messages)


def test_extract_api_exception(extractor, mock_openai_client):
    """Test that API exceptions are wrapped in ExtractionError."""
    mock_openai_client.beta.chat.completions.parse.side_effect = Exception(
        "API error"
    )

    messages = [{"role": "user", "content": "test"}]
    with pytest.raises(ExtractionError, match="Extraction failed"):
        extractor.extract(messages)


def test_extract_model_dump_uses_alias(extractor, mock_openai_client):
    """Verify the returned dict uses ``_meta`` (alias), not ``meta``."""
    parsed_obj = _make_parsed_result(first_name="Jane")

    mock_message = MagicMock()
    mock_message.refusal = None
    mock_message.parsed = parsed_obj

    mock_response = MagicMock()
    mock_response.choices = [MagicMock(message=mock_message)]

    mock_usage = MagicMock()
    mock_usage.prompt_tokens = 100
    mock_usage.completion_tokens = 50
    mock_response.usage = mock_usage
    mock_openai_client.beta.chat.completions.parse.return_value = mock_response

    response = extractor.extract([{"role": "user", "content": "test"}])
    result = response.result
    assert "_meta" in result
    assert "meta" not in result


def test_extract_missing_api_key():
    """Test error when OPENAI_API_KEY is not set."""
    with patch("src.extractor.config.OPENAI_API_KEY", ""):
        with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
            DocumentExtractor()


def test_extract_retry_on_rate_limit(extractor, mock_openai_client):
    """Test retry logic on RateLimitError."""
    # Create a mock RateLimitError class that will pass isinstance check
    class MockRateLimitError(Exception):
        pass

    # Patch the openai module's RateLimitError for the isinstance check
    with patch("src.extractor.openai.RateLimitError", MockRateLimitError):
        parsed_obj = _make_parsed_result(first_name="John")
        mock_message = MagicMock()
        mock_message.refusal = None
        mock_message.parsed = parsed_obj

        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=mock_message)]
        mock_usage = MagicMock()
        mock_usage.prompt_tokens = 100
        mock_usage.completion_tokens = 50
        mock_response.usage = mock_usage

        # First two calls raise RateLimitError, third succeeds
        mock_openai_client.beta.chat.completions.parse.side_effect = [
            MockRateLimitError("Rate limit"),
            MockRateLimitError("Rate limit"),
            mock_response,
        ]

        messages = [{"role": "user", "content": "test"}]
        response = extractor.extract(messages)

        assert isinstance(response, ExtractionResponse)
        assert response.result["patient"]["first_name"] == "John"
        # Should have tried 3 times (initial + 2 retries)
        assert mock_openai_client.beta.chat.completions.parse.call_count == 3


def test_extract_fail_fast_on_authentication_error(extractor, mock_openai_client):
    """Test that AuthenticationError fails fast without retry."""
    # Create a mock AuthenticationError that won't match _should_retry
    class MockAuthenticationError(Exception):
        pass

    # AuthenticationError is not in _should_retry, so it should fail fast
    mock_openai_client.beta.chat.completions.parse.side_effect = MockAuthenticationError(
        "Invalid API key"
    )

    messages = [{"role": "user", "content": "test"}]
    with pytest.raises(ExtractionError, match="Extraction failed"):
        extractor.extract(messages)

    # Should have tried exactly once (no retry for non-retryable errors)
    assert mock_openai_client.beta.chat.completions.parse.call_count == 1
