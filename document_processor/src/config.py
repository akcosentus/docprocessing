"""Centralized environment configuration. Imported before any other src module."""

from pathlib import Path

from dotenv import load_dotenv, dotenv_values


# Load .env once at module import time
load_dotenv()
_env = dotenv_values()


def _require(key: str) -> str:
    """Return env var value or raise RuntimeError if missing/empty.

    Args:
        key: Environment variable name.

    Returns:
        The environment variable value (non-empty string).

    Raises:
        RuntimeError: If the variable is missing or empty.
    """
    value = _env.get(key)
    if not value or value.strip() == "":
        raise RuntimeError(
            f"Required environment variable '{key}' is missing or empty. "
            "Please set it in your .env file."
        )
    return value


def _optional(key: str, default: str) -> str:
    """Return env var value or default if missing/empty.

    Args:
        key: Environment variable name.
        default: Default value to use if variable is missing or empty.

    Returns:
        The environment variable value or the default.
    """
    value = _env.get(key)
    if not value or value.strip() == "":
        return default
    return value


# Required
OPENAI_API_KEY: str = _require("OPENAI_API_KEY")

# Optional with defaults
OPENAI_ORG_ID: str = _optional("OPENAI_ORG_ID", "")
LOG_LEVEL: str = _optional("LOG_LEVEL", "INFO")
MODEL_SNAPSHOT: str = _optional("MODEL_SNAPSHOT", "gpt-4o-2024-11-20")
MAX_FILE_SIZE_MB: int = int(_optional("MAX_FILE_SIZE_MB", "50"))
OUTPUT_EXCEL: str = _optional("OUTPUT_EXCEL", str(Path.home() / "Desktop" / "PatientDemographics" / "PatientDemographics.xlsx"))
# Empirically, scores below 0.85 correlate with documents where OCR quality is poor
# or form layout is ambiguous, indicating low extraction reliability
CONSISTENCY_THRESHOLD: float = float(_optional("CONSISTENCY_THRESHOLD", "0.85"))
