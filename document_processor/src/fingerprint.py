"""File fingerprinting for idempotent processing."""

import hashlib
import json
from pathlib import Path
from typing import Set

from src.logger import get_logger

logger = get_logger(__name__)


def compute_fingerprint(file_path: str) -> str:
    """Return SHA-256 hex digest of file contents.

    Args:
        file_path: Path to the file.

    Returns:
        64-character lowercase hex string.
    """
    file_path_obj = Path(file_path)
    logger.debug(f"Computing fingerprint for: {file_path_obj}")

    sha256 = hashlib.sha256()
    with open(file_path_obj, "rb") as f:
        # Read in chunks to handle large files efficiently
        while chunk := f.read(8192):
            sha256.update(chunk)

    fingerprint = sha256.hexdigest()
    logger.debug(f"Fingerprint computed: {fingerprint[:16]}...")
    return fingerprint


def load_processed_log(log_path: str) -> Set[str]:
    """Read processed_files.json from disk, return set of fingerprint strings.

    Args:
        log_path: Path to the JSON file.

    Returns:
        Set of fingerprint hex strings. Empty set if file does not exist.
    """
    log_file = Path(log_path)
    if not log_file.exists():
        logger.debug(f"Processed log does not exist: {log_path}")
        return set()

    try:
        with open(log_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            fingerprints = set(data.get("fingerprints", []))
            logger.debug(f"Loaded {len(fingerprints)} fingerprints from log")
            return fingerprints
    except (json.JSONDecodeError, KeyError) as e:
        logger.warning(f"Error reading processed log {log_path}: {e}, returning empty set")
        return set()


def save_processed_log(log_path: str, fingerprints: Set[str]) -> None:
    """Write the set of fingerprints to processed_files.json.

    Args:
        log_path: Path to the JSON file.
        fingerprints: Set of fingerprint hex strings.
    """
    log_file = Path(log_path)
    log_file.parent.mkdir(parents=True, exist_ok=True)

    data = {"fingerprints": sorted(list(fingerprints))}
    with open(log_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    logger.debug(f"Saved {len(fingerprints)} fingerprints to: {log_path}")
