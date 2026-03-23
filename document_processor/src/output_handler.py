"""Output handling for writing extraction results to JSON files."""

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

from src.logger import get_logger

logger = get_logger(__name__)


def write_result(
    result: Dict[str, Any], input_filename: str, output_dir: str
) -> Path:
    """
    Write extraction result to a timestamped JSON file.

    Args:
        result: The extraction result dictionary
        input_filename: Original input filename (without path)
        output_dir: Directory to write output files

    Returns:
        Path to the written output file
    """
    logger.debug(f"Writing result to output_dir: {output_dir}")
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # Generate output filename: {input_filename_without_ext}_{timestamp}.json
    input_stem = Path(input_filename).stem
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_filename = f"{input_stem}_{timestamp}.json"
    output_file = output_path / output_filename

    # Write pretty-printed JSON
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    logger.debug(f"Wrote result file: {output_file}")
    return output_file


def write_review_queue_entry(
    result: Dict[str, Any],
    input_filename: str,
    output_dir: str,
    extraction_file_path: Optional[Path] = None,
    reason: Optional[str] = None,
    detected_name: Optional[str] = None,
) -> Path:
    """
    Write an entry to the review queue JSONL file for results needing human review.

    Args:
        result: The extraction result dictionary
        input_filename: Original input filename
        output_dir: Directory to write review queue file
        extraction_file_path: Optional path to the extraction output file
        reason: Optional reason for review (e.g., "unknown_facility")
        detected_name: Optional detected facility name from classification

    Returns:
        Path to the review queue file
    """
    logger.debug(f"Writing review queue entry to: {output_dir}")
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    review_queue_file = output_path / "review_queue.jsonl"

    # Create review entry
    meta = result.get("_meta", {})
    review_entry = {
        "timestamp": datetime.now().isoformat(),
        "input_filename": input_filename,
        "extraction_file": str(extraction_file_path) if extraction_file_path else None,
        "confidence": meta.get("confidence"),
        "conflicts": meta.get("conflicts", []),
        "result": result,
    }

    # Add optional classification fields
    if reason:
        review_entry["reason"] = reason
    if detected_name:
        review_entry["detected_name"] = detected_name
        review_entry["suggested_action"] = "Add to facilities.json or re-run with --facility"

    # Append to JSONL file (one JSON object per line)
    with open(review_queue_file, "a", encoding="utf-8") as f:
        json_line = json.dumps(review_entry, ensure_ascii=False)
        f.write(json_line + "\n")

    logger.debug(f"Appended to review queue: {review_queue_file}")
    return review_queue_file


# gpt-4o-2024-11-20 pricing
_INPUT_COST_PER_M_TOKENS: float = 2.50
_OUTPUT_COST_PER_M_TOKENS: float = 10.00


def _estimate_cost(input_tokens: int, output_tokens: int) -> float:
    """Calculate estimated USD cost from token counts.

    Args:
        input_tokens: Number of input tokens.
        output_tokens: Number of output tokens.

    Returns:
        Estimated cost in USD.
    """
    input_cost = (input_tokens / 1_000_000) * _INPUT_COST_PER_M_TOKENS
    output_cost = (output_tokens / 1_000_000) * _OUTPUT_COST_PER_M_TOKENS
    return input_cost + output_cost


def write_run_report(report: Dict[str, Any], output_dir: str) -> Path:
    """
    Write a run report JSON file (no PHI — metadata only).

    Filename: run_report_{timestamp}.json

    Args:
        report: Dict with keys: run_id, timestamp, total_files, succeeded,
                failed, routed_to_review, files_skipped_duplicate,
                total_input_tokens, total_output_tokens, estimated_cost_usd,
                per_file_summary (list of dicts with filename, facility_id,
                confidence, flags, status).
        output_dir: Directory for output files.

    Returns:
        Path to the written report file.
    """
    logger.debug(f"Writing run report to: {output_dir}")
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_filename = f"run_report_{timestamp}.json"
    report_file = output_path / report_filename

    with open(report_file, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    logger.debug(f"Wrote run report: {report_file}")
    return report_file
