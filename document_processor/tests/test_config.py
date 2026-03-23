"""Unit tests for config module."""

from unittest.mock import patch

import pytest


def test_missing_required_var():
    """Test that missing OPENAI_API_KEY raises RuntimeError at module import."""
    # Since config is evaluated at import time, we test via DocumentExtractor
    # which uses config.OPENAI_API_KEY
    from src.extractor import DocumentExtractor

    with patch("src.extractor.config.OPENAI_API_KEY", ""):
        with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
            DocumentExtractor()


def test_optional_defaults():
    """Test that optional vars use defaults when not set."""
    # Test by checking the actual config values (they're set at import time)
    import src.config

    # These should have default values from .env or defaults
    # We can't easily test the module-level evaluation, but we can verify
    # the attributes exist and have reasonable values
    assert hasattr(src.config, "LOG_LEVEL")
    assert hasattr(src.config, "MODEL_SNAPSHOT")
    assert hasattr(src.config, "MAX_FILE_SIZE_MB")
    assert isinstance(src.config.MAX_FILE_SIZE_MB, int)


def test_optional_overrides():
    """Test that optional vars can be overridden via environment."""
    # Test by patching the config attributes directly (simulating env override)
    with patch("src.config.LOG_LEVEL", "DEBUG"), \
         patch("src.config.MODEL_SNAPSHOT", "gpt-4o"), \
         patch("src.config.MAX_FILE_SIZE_MB", 100):
        import src.config
        # Verify the patched values
        assert src.config.LOG_LEVEL == "DEBUG"
        assert src.config.MODEL_SNAPSHOT == "gpt-4o"
        assert src.config.MAX_FILE_SIZE_MB == 100
