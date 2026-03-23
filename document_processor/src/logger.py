"""Structured logging with PHI-safe output and correlation ID tracking."""

import contextvars
import json
import logging
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional


# Context variable for correlation ID
correlation_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "correlation_id", default=""
)


def new_correlation_id() -> str:
    """Generate and set a new uuid4 correlation_id in the current context.

    Returns:
        The generated correlation ID string.
    """
    corr_id = str(uuid.uuid4())
    correlation_id_var.set(corr_id)
    return corr_id


class CorrelationFilter(logging.Filter):
    """Injects correlation_id from contextvars into every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        """Add correlation_id to the log record."""
        record.correlation_id = correlation_id_var.get("")
        return True


class JsonLineFormatter(logging.Formatter):
    """Formats log records as single-line JSON objects."""

    def format(self, record: logging.LogRecord) -> str:
        """Format a log record as a JSON line."""
        log_data = {
            "timestamp": datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "correlation_id": getattr(record, "correlation_id", ""),
            "module": record.name,
            "message": record.getMessage(),
        }
        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_data, ensure_ascii=False)


class HumanReadableFormatter(logging.Formatter):
    """Human-readable format with timestamp, level, correlation_id, and message."""

    def __init__(self):
        super().__init__(
            fmt="%(asctime)s - %(name)s - %(levelname)s - [%(correlation_id)s] - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

    def format(self, record: logging.LogRecord) -> str:
        """Format a log record with correlation_id."""
        # Ensure correlation_id attribute exists
        if not hasattr(record, "correlation_id"):
            record.correlation_id = ""
        return super().format(record)


def setup_logging(level: str = "INFO", log_dir: str = "logs") -> None:
    """
    Configure root logger with two handlers:
    - StreamHandler (stdout) with HumanReadableFormatter
    - FileHandler (logs/app.log) with JsonLineFormatter
    Both get the CorrelationFilter attached.

    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        log_dir: Directory for log files.
    """
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    # Get root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Remove existing handlers to avoid duplicates
    root_logger.handlers.clear()

    # Create correlation filter
    correlation_filter = CorrelationFilter()

    # Stream handler (stdout) with human-readable format
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setLevel(getattr(logging, level.upper(), logging.INFO))
    stream_handler.setFormatter(HumanReadableFormatter())
    stream_handler.addFilter(correlation_filter)
    root_logger.addHandler(stream_handler)

    # File handler (JSON lines)
    log_file = log_path / "app.log"
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(getattr(logging, level.upper(), logging.INFO))
    file_handler.setFormatter(JsonLineFormatter())
    file_handler.addFilter(correlation_filter)
    root_logger.addHandler(file_handler)


def get_logger(name: str) -> logging.Logger:
    """
    Return a named logger. All modules use this instead of logging.getLogger().

    Args:
        name: Logger name (typically __name__).

    Returns:
        A Logger instance.
    """
    return logging.getLogger(name)
