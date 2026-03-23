"""OpenAI API integration for extracting patient data from document images.

Uses OpenAI Structured Outputs with Pydantic to guarantee schema-compliant
responses.  The JSON retry loop is no longer needed — the API enforces the
schema at decode time.
"""

from dataclasses import dataclass
from typing import Dict, Any, List, Optional

import openai
from openai import OpenAI
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential_jitter,
    before_sleep_log,
)

import src.config as config
from src.logger import get_logger
from src.schemas import ExtractionResult


logger = get_logger(__name__)


@dataclass
class ExtractionResponse:
    """Wraps the parsed result dict and API usage metadata."""

    result: Dict[str, Any]
    input_tokens: int
    output_tokens: int


class ExtractionError(Exception):
    """Raised when extraction fails unrecoverably."""

    def __init__(self, message: str, original_error: Optional[Exception] = None):
        self.original_error = original_error
        super().__init__(message)


def _should_retry(exc: BaseException) -> bool:
    """Return True for retryable OpenAI errors (rate limit, 5xx).

    Args:
        exc: The exception to check.

    Returns:
        True if the exception should trigger a retry.
    """
    if isinstance(exc, openai.RateLimitError):
        return True
    if isinstance(exc, openai.APIStatusError) and exc.status_code >= 500:
        return True
    return False


def _log_retry_attempt(retry_state):
    """Log retry attempt at WARNING level (no PHI)."""
    logger.warning(
        f"Retry attempt {retry_state.attempt_number}/3 after {retry_state.outcome_timestamp - retry_state.start_time:.2f}s"
    )


class DocumentExtractor:
    """Handles OpenAI API calls for document extraction using Structured Outputs."""

    def __init__(self):
        """
        Initialize the OpenAI client from environment variables.

        Raises:
            RuntimeError: If OPENAI_API_KEY is not set or empty.
        """
        if not config.OPENAI_API_KEY or config.OPENAI_API_KEY.strip() == "":
            raise RuntimeError(
                "Required environment variable 'OPENAI_API_KEY' is missing or empty. "
                "Please set it in your .env file."
            )
        self.client = OpenAI(
            api_key=config.OPENAI_API_KEY,
            organization=config.OPENAI_ORG_ID if config.OPENAI_ORG_ID else None
        )

    @retry(
        retry=retry_if_exception(_should_retry),
        stop=stop_after_attempt(3),
        wait=wait_exponential_jitter(initial=2, max=60),
        before_sleep=_log_retry_attempt,
        reraise=True,
    )
    def _call_api(
        self, messages: List[Dict[str, Any]], model: str
    ) -> openai.types.chat.chat_completion.ChatCompletion:
        """Make the actual API call. Tenacity wraps this with retry logic.

        Args:
            messages: List of message dicts for the chat completion API.
            model: Model name to use.

        Returns:
            The parsed chat completion response.

        Raises:
            openai.RateLimitError: On rate limit (will be retried).
            openai.APIStatusError: On 5xx errors (will be retried).
            openai.AuthenticationError: On auth errors (fail-fast, no retry).
            openai.PermissionDeniedError: On permission errors (fail-fast, no retry).
            openai.BadRequestError: On bad request (fail-fast, no retry).
        """
        return self.client.beta.chat.completions.parse(
            model=model,
            messages=messages,
            temperature=0,
            store=False,  # HIPAA/ZDR requirement — do not store PHI
            response_format=ExtractionResult,
        )

    def extract(
        self, messages: List[Dict[str, Any]], model: str = None
    ) -> Dict[str, Any]:
        """
        Extract patient data from document images using OpenAI Structured Outputs.

        Args:
            messages: List of message dicts for the chat completion API.
            model: Model name to use (default: from config.MODEL_SNAPSHOT).

        Returns:
            Parsed extraction result as a plain dict (keys match the
            canonical schema, including ``_meta``).

        Raises:
            ExtractionError: On API-level failures, refusals, or empty
                parsed responses.
        """
        if model is None:
            model = config.MODEL_SNAPSHOT
        try:
            response = self._call_api(messages, model)

            # Check for model refusal
            message = response.choices[0].message
            if message.refusal is not None:
                raise ExtractionError(
                    f"Model refused the request: {message.refusal}"
                )

            parsed: Optional[ExtractionResult] = message.parsed
            if parsed is None:
                raise ExtractionError("Parsed response is None — no data returned.")

            # Extract token usage from response
            usage = response.usage
            input_tokens = usage.prompt_tokens if usage else 0
            output_tokens = usage.completion_tokens if usage else 0

            return ExtractionResponse(
                result=parsed.model_dump(by_alias=True),
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )

        except ExtractionError:
            raise
        except Exception as e:
            raise ExtractionError(
                f"Extraction failed: {e}",
                original_error=e,
            ) from e
