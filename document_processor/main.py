#!/usr/bin/env python3
"""CLI entrypoint for medical document processing."""

import argparse
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

import src.config as config
from src.logger import get_logger, new_correlation_id, setup_logging

from src.extractor import DocumentExtractor, ExtractionError, ExtractionResponse
from src.facility_config import FacilityConfig, FacilityNotFoundError
from src.excel_handler import append_to_workbook, WorkbookLockedError
from src.consistency import run_consistency_check
from src.classifier import classify_document, resolve_facility, ClassificationResult
from src.output_handler import (
    write_result,
    write_review_queue_entry,
    write_run_report,
    _estimate_cost,
)
from src.pdf_handler import (
    SUPPORTED_EXTENSIONS,
    process_document,
    validate_input_file,
    extract_ocr_text,
    CorruptFileError,
    FileTooLargeError,
    PasswordProtectedError,
    UnsupportedFormatError,
)
from src.prompts import (
    build_messages_for_extraction,
    build_messages_for_validation,
)
from src.fingerprint import compute_fingerprint, load_processed_log, save_processed_log
from src.merger import merge_pages
from src.validator import should_run_validation_pass, validate_extraction


@dataclass
class BatchSummary:
    """Tracks results across a batch run."""

    total: int = 0
    succeeded: int = 0
    failed: int = 0
    review_queue: int = 0
    skipped_duplicate: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    failures: List[str] = field(default_factory=list)
    per_file_summary: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class FacilityResolution:
    """Result of facility resolution for a document."""

    facility_id: Optional[str]
    facility_data: Dict[str, Any]
    needs_review: bool
    classification: Optional[ClassificationResult]




def _needs_review(result: Dict[str, Any]) -> bool:
    """Return True if the result should be routed to the review queue.

    A result needs review when confidence is LOW or when conflicts exist.
    """
    meta = result.get("_meta", {})
    confidence = meta.get("confidence", result.get("confidence"))
    conflicts = meta.get("conflicts", result.get("conflicts", []))
    return confidence == "LOW" or (isinstance(conflicts, list) and len(conflicts) > 0)


def _sanitize_facility_id(name: str) -> str:
    """Generate a valid facility_id from a detected facility name.

    Args:
        name: Detected facility name

    Returns:
        Sanitized facility_id (lowercase, underscores, no special chars)
    """
    import re
    facility_id = name.lower()
    facility_id = facility_id.replace(" ", "_").replace("-", "_")
    facility_id = re.sub(r'[^a-z0-9_]', '', facility_id)  # Remove special characters
    facility_id = re.sub(r'_+', '_', facility_id)  # Collapse multiple underscores
    facility_id = facility_id.strip('_')  # Strip leading/trailing underscores
    return facility_id


def resolve_facility_for_file(
    file_path: str,
    explicit_facility: Optional[str],
    facilities: Dict[str, Any],
    skip_classify: bool,
    output_dir: str,
    facility_config: FacilityConfig,
) -> FacilityResolution:
    """
    Determine which facility config to use for a file.

    Args:
        file_path: Path to document file
        explicit_facility: Facility ID from --facility flag (if provided)
        facilities: Raw facilities config dict
        skip_classify: Whether --no-classify flag was set
        output_dir: Output directory for auto-stub creation
        facility_config: FacilityConfig instance for reloading after stub creation

    Returns:
        FacilityResolution with facility_id, facility_data, needs_review, and classification
        needs_review=True if classification was low confidence or no match
        classification is None if classification was skipped
    """
    logger = get_logger(__name__)

    # Decision tree:
    # 1. --facility provided AND --no-classify → use provided facility, skip classification
    # 2. --facility provided (no --no-classify) → use provided facility, skip classification
    # 3. --facility not provided AND --no-classify → raise ValueError
    # 4. --facility not provided → run classification

    if explicit_facility:
        # Cases 1 & 2: Use explicit facility
        try:
            facility_data = facility_config.get_facility(explicit_facility)
            logger.info(f"Using explicit facility: {facility_data['display_name']}")
            return FacilityResolution(
                facility_id=explicit_facility,
                facility_data=facility_data,
                needs_review=False,
                classification=None,
            )
        except FacilityNotFoundError as e:
            logger.error(f"Facility error: {e}")
            raise

    if skip_classify:
        # Case 3: Error - facility required when --no-classify set
        raise ValueError("facility required when --no-classify set")

    # Case 4: Run classification
    logger.info("Running facility classification...")
    
    # Process first page only for classification
    validated_path = validate_input_file(file_path, config.MAX_FILE_SIZE_MB)
    images = process_document(validated_path)
    if not images:
        raise ValueError(f"No images extracted from {file_path}")
    
    first_image = images[0]
    classification = classify_document(
        base64_image=first_image["base64_image"],
        image_media_type="image/jpeg",
    )

    # Resolve facility match
    facility_id, match_type = resolve_facility(classification, facilities)
    classification.matched_facility_id = facility_id
    classification.match_type = match_type

    # Decision logic based on classification result
    if facility_id:
        # Matched facility found
        facility_data = facility_config.get_facility(facility_id)
        
        if classification.confidence == "HIGH" and match_type in ("exact", "fuzzy"):
            # HIGH confidence + match → no review needed
            logger.info(f"Matched facility: {facility_data['display_name']} (match_type={match_type})")
            return FacilityResolution(
                facility_id=facility_id,
                facility_data=facility_data,
                needs_review=False,
                classification=classification,
            )
        elif classification.confidence == "MEDIUM" and match_type in ("exact", "fuzzy"):
            # MEDIUM confidence + match → needs review
            logger.info(f"Matched facility: {facility_data['display_name']} (match_type={match_type}, MEDIUM confidence)")
            return FacilityResolution(
                facility_id=facility_id,
                facility_data=facility_data,
                needs_review=True,
                classification=classification,
            )
        else:
            # Match but low confidence or no match type
            logger.warning(f"Matched facility but low confidence: {facility_data['display_name']}")
            return FacilityResolution(
                facility_id=facility_id,
                facility_data=facility_data,
                needs_review=True,
                classification=classification,
            )
    else:
        # No match found
        if classification.detected_name and classification.confidence == "HIGH":
            # HIGH confidence but no match → create auto-stub
            logger.info(f"Auto-detecting new facility: {classification.detected_name}")
            
            # Generate facility_id
            new_facility_id = _sanitize_facility_id(classification.detected_name)
            
            # Check if already exists (shouldn't happen, but be safe)
            if new_facility_id in facilities:
                logger.warning(f"Auto-generated facility_id '{new_facility_id}' already exists, using existing")
                facility_data = facility_config.get_facility(new_facility_id)
                return FacilityResolution(
                    facility_id=new_facility_id,
                    facility_data=facility_data,
                    needs_review=True,
                    classification=classification,
                )
            
            # Create auto-stub
            # Note: Auto-stub creation assumes sequential execution. In a batch run,
            # if multiple unknown docs from the same facility are processed concurrently
            # (if parallelized in the future), duplicate stubs could be created.
            # This is safe for the current CLI tool which processes files sequentially.
            config_path = facility_config.config_path
            with open(config_path, "r", encoding="utf-8") as f:
                config_data = json.load(f)
            
            config_data[new_facility_id] = {
                "display_name": classification.detected_name,
                "display_names": [classification.detected_name],
                "auto_detected": True,
                "overrides": [],
                "notes": f"Auto-detected on {datetime.now().strftime('%Y-%m-%d')}. Add overrides manually."
            }
            
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(config_data, f, indent=2, ensure_ascii=False)
            
            # Reload config
            facility_config._load_config()
            facility_data = facility_config.get_facility(new_facility_id)
            
            logger.info(f"Created auto-stub facility: {new_facility_id}")
            return FacilityResolution(
                facility_id=new_facility_id,
                facility_data=facility_data,
                needs_review=True,
                classification=classification,
            )
        else:
            # LOW confidence OR no detected_name → use empty overrides
            logger.warning(
                f"No facility match found. Detected: {classification.detected_name}, "
                f"Confidence: {classification.confidence}"
            )
            return FacilityResolution(
                facility_id=None,
                facility_data={"display_name": "Unknown", "overrides": []},
                needs_review=True,
                classification=classification,
            )


def process_single_file(
    file_path: str,
    facility_id: str,
    facility_data: Dict[str, Any],
    output_dir: str,
    validate: bool,
    output_excel: str,
    resolution: Optional[FacilityResolution] = None,
) -> tuple[Dict[str, Any], int, int]:
    """Run the full extraction pipeline on a single file.

    Args:
        file_path: Path to the PDF or image file.
        facility_id: The facility identifier string.
        facility_data: Facility config dict (display_name, overrides).
        output_dir: Directory for JSON output files.
        validate: Whether to run second-pass validation.
        output_excel: Path to Excel workbook for appending (required, set by main()).
        resolution: Optional FacilityResolution for flag handling.

    Returns:
        Tuple of (extraction result dict, total input tokens, total output tokens).

    Raises:
        Any pipeline exception (FileNotFoundError, CorruptFileError,
        PasswordProtectedError, UnsupportedFormatError, ExtractionError,
        WorkbookLockedError) is allowed to propagate.
    """
    # Generate new correlation ID for this file processing
    corr_id = new_correlation_id()
    logger = get_logger(__name__)

    # Validate input file before processing
    validated_path = validate_input_file(file_path, config.MAX_FILE_SIZE_MB)

    # Process document (PDF or image)
    logger.info(f"Processing document: {validated_path}")
    images = process_document(validated_path)
    logger.info(f"Converted {len(images)} page(s) to base64 images")

    # Extract OCR text for each page (always enabled)
    logger.info("Extracting OCR text from document pages...")
    for img_data in images:
        pil_image = img_data.get("pil_image")
        if pil_image:
            ocr_text = extract_ocr_text(pil_image)
            img_data["ocr_text"] = ocr_text
            if ocr_text:
                logger.debug(f"OCR extracted {len(ocr_text)} characters for page {img_data['page_number']}")
            else:
                logger.debug(f"OCR returned empty text for page {img_data['page_number']}")
        else:
            logger.warning(f"PIL Image not available for page {img_data['page_number']} - OCR skipped")
            img_data["ocr_text"] = ""

    # Extract data using OpenAI for all pages
    logger.info("Sending extraction requests to OpenAI API...")
    extractor = DocumentExtractor()

    page_results = []
    total_input_tokens = 0
    total_output_tokens = 0

    for img_data in images:
        messages = build_messages_for_extraction(
            base64_image=img_data["base64_image"],
            facility_name=facility_data["display_name"],
            facility_overrides=facility_data["overrides"],
            page_count=len(images),
            page_number=img_data["page_number"],
            image_media_type="image/jpeg",
            ocr_text=img_data.get("ocr_text"),
        )

        # Run two-pass consistency check (always enabled)
        logger.debug(f"Running consistency check for page {img_data['page_number']}")
        consistency_result = run_consistency_check(
            extractor=extractor,
            messages_pass1=messages,
            messages_pass2=messages,  # Same messages for both passes
        )
        page_result = consistency_result.final_result
        total_input_tokens += consistency_result.total_input_tokens
        total_output_tokens += consistency_result.total_output_tokens

        # Override confidence if consistency score is below threshold
        if consistency_result.consistency_score < config.CONSISTENCY_THRESHOLD:
            if "_meta" not in page_result:
                page_result["_meta"] = {}
            page_result["_meta"]["confidence"] = "LOW"
            logger.warning(
                f"Consistency score {consistency_result.consistency_score:.2f} "
                f"below threshold {config.CONSISTENCY_THRESHOLD} - forcing confidence to LOW"
            )

        # Set facility_id in _meta for each page
        if "_meta" not in page_result:
            page_result["_meta"] = {}
        page_result["_meta"]["facility_id"] = facility_id

        page_results.append(page_result)

    # Merge all page results
    result = merge_pages(page_results)

    # Add multi_page_document flag if applicable
    if len(images) > 1:
        if "_meta" not in result:
            result["_meta"] = {}
        flags = result["_meta"].get("flags", [])
        if "multi_page_document" not in flags:
            flags.append("multi_page_document")
            result["_meta"]["flags"] = flags

    logger.info("Extraction completed")

    # Validate extraction
    validation_result = validate_extraction(result)
    if not validation_result.is_valid:
        logger.warning(f"Validation errors: {validation_result.errors}")
    else:
        logger.info("Initial validation passed")

    # Run second-pass validation if requested or if needed
    if validate or should_run_validation_pass(result):
        logger.info("Running second-pass validation...")

        prior_result_json = json.dumps(result, ensure_ascii=False)

        # Use first page image for validation
        first_image = images[0]
        validation_messages = build_messages_for_validation(
            base64_image=first_image["base64_image"],
            prior_result_json=prior_result_json,
            image_media_type="image/jpeg",
        )

        try:
            validation_response = extractor.extract(validation_messages)
            validation_result_data = validation_response.result
            total_input_tokens += validation_response.input_tokens
            total_output_tokens += validation_response.output_tokens
            if isinstance(validation_result_data, dict):
                result.update(validation_result_data)
                if "_meta" not in result:
                    result["_meta"] = {}
                result["_meta"]["facility_id"] = facility_id
            logger.info("Second-pass validation completed")
        except ExtractionError as e:
            logger.warning(f"Second-pass validation failed: {e}")

    # Write JSON output
    input_filename = Path(file_path).name
    output_file = write_result(result, input_filename, output_dir)
    logger.info(f"Results written to: {output_file}")

    # Note: Fingerprint is saved to log in main() after successful processing

    # Add classification-related flags if resolution provided
    if resolution and resolution.classification:
        if "_meta" not in result:
            result["_meta"] = {}
        flags = result["_meta"].get("flags", [])
        if not isinstance(flags, list):
            flags = []
        
        # Add flags based on classification result
        if resolution.needs_review:
            if not resolution.facility_id:
                flags.extend(["unknown_facility", "no_overrides_applied", "requires_facility_review"])
            elif resolution.classification.match_type == "none" and resolution.classification.detected_name:
                flags.append("new_facility_review")
            elif resolution.classification.confidence == "MEDIUM":
                flags.append("new_facility_review")
        
        if resolution.facility_id and resolution.classification.match_type == "fuzzy":
            # Check if this was an auto-detected facility
            facility_config_check = FacilityConfig()
            try:
                facility_check = facility_config_check.get_facility(resolution.facility_id)
                # Check if auto_detected flag exists in config (would need to check raw config)
                # For now, we'll add a flag if match was fuzzy and needs review
                if "auto_detected_facility" not in flags and resolution.needs_review:
                    # This might be auto-detected, but we can't easily check here
                    pass
            except FacilityNotFoundError:
                pass
        
        result["_meta"]["flags"] = flags

    # Write to review queue if needed
    review_reason = None
    detected_name = None
    if resolution and resolution.needs_review and resolution.classification:
        if not resolution.facility_id:
            review_reason = "unknown_facility"
            detected_name = resolution.classification.detected_name
    
    # Review queue routing removed - Excel sheet is now the single source of truth
    # if _needs_review(result) or (resolution and resolution.needs_review):
    #     review_file = write_review_queue_entry(
    #         result, input_filename, output_dir, output_file,
    #         reason=review_reason,
    #         detected_name=detected_name,
    #     )
    #     logger.info(f"Added to review queue: {review_file}")

    # Append to Excel workbook (always done, default path set in main())
    logger.info(f"Appending results to Excel workbook: {output_excel}")
    excel_path = append_to_workbook(result, input_filename, output_excel)
    logger.info(f"Excel workbook updated: {excel_path}")

    return result, total_input_tokens, total_output_tokens


def _collect_supported_files(input_dir: str) -> List[Path]:
    """Return a sorted list of supported files in a directory (non-recursive).

    Args:
        input_dir: Path to the directory to scan.

    Returns:
        Sorted list of Path objects for supported files.

    Raises:
        FileNotFoundError: If the directory does not exist.
        ValueError: If no supported files are found.
    """
    dir_path = Path(input_dir)
    if not dir_path.is_dir():
        raise FileNotFoundError(f"Input directory not found: {input_dir}")

    files = sorted(
        f for f in dir_path.iterdir()
        if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS
    )

    if not files:
        raise ValueError(
            f"No supported files found in '{input_dir}'. "
            f"Supported types: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
        )

    return files


def main() -> int:
    """Main CLI entrypoint."""
    parser = argparse.ArgumentParser(
        description="Extract patient demographic data from PDF and image facesheets"
    )

    # --input, --input-dir, and --batch-folder are mutually exclusive
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument(
        "--input",
        type=str,
        help="Path to a single PDF or image file",
    )
    input_group.add_argument(
        "--input-dir",
        type=str,
        help="Path to a folder of PDF/image files for batch processing",
    )
    input_group.add_argument(
        "--batch-folder",
        type=str,
        help=(
            "Path to a dated batch folder containing 'start/' and 'end/' subfolders. "
            "Uses start/ as input-dir, writes JSON reports to end/output/, and writes "
            "Excel to end/PatientDemographics.xlsx unless output flags are provided."
        ),
    )

    parser.add_argument(
        "--facility",
        type=str,
        default=None,
        help="Facility ID from config (e.g., baywood_court). If omitted, auto-detected from document.",
    )
    parser.add_argument(
        "--no-classify",
        action="store_true",
        help="Skip auto-detection and require --facility to be specified explicitly.",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="Output directory for JSON files (default: ./output, or <batch-folder>/end/output when --batch-folder is used)",
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Run second-pass validation for MEDIUM/LOW confidence results",
    )
    parser.add_argument(
        "--output-excel",
        type=str,
        default=None,
        help="Path to Excel workbook (.xlsx) for appending results (default: from OUTPUT_EXCEL env var or ~/Desktop/PatientDemographics/PatientDemographics.xlsx)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force processing even if file has been processed before",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )

    args = parser.parse_args()

    # Setup logging with level from config or verbose override
    log_level = "DEBUG" if args.verbose else config.LOG_LEVEL
    setup_logging(level=log_level)
    logger = get_logger(__name__)

    # Resolve folder-based run mode paths first
    if args.batch_folder:
        batch_root = Path(args.batch_folder).expanduser().resolve()
        start_dir = batch_root / "start"
        end_dir = batch_root / "end"

        if not batch_root.is_dir():
            logger.error(f"Batch folder not found: {batch_root}")
            return 1
        if not start_dir.is_dir():
            logger.error(f"Batch folder is missing required start/ directory: {start_dir}")
            return 1
        if not end_dir.is_dir():
            logger.error(f"Batch folder is missing required end/ directory: {end_dir}")
            return 1

        # In batch-folder mode, input is always start/
        args.input_dir = str(start_dir)
        args.input = None

        # Default JSON/report output path for batch-folder mode
        if args.output_dir is None:
            args.output_dir = str(end_dir / "output")

        # Default Excel output path for batch-folder mode
        if args.output_excel is None:
            args.output_excel = str(end_dir / "PatientDemographics.xlsx")

        logger.info(f"Batch folder mode enabled: {batch_root}")
        logger.info(f"Resolved input directory: {args.input_dir}")
        logger.info(f"Resolved JSON output directory: {args.output_dir}")
        logger.info(f"Resolved Excel output path: {args.output_excel}")

    # Standard defaults when not using --batch-folder
    if args.output_dir is None:
        args.output_dir = "./output"
    if args.output_excel is None:
        args.output_excel = config.OUTPUT_EXCEL

    # ── Load facility config (shared by single-file and batch modes) ──
    facility_config = FacilityConfig()
    facilities = facility_config.load_facilities()

    # ── Single-file mode ──
    if args.input:
        run_id = new_correlation_id()

        # Resolve facility for this file
        try:
            resolution = resolve_facility_for_file(
                file_path=args.input,
                explicit_facility=args.facility,
                facilities=facilities,
                skip_classify=args.no_classify,
                output_dir=args.output_dir,
                facility_config=facility_config,
            )
        except ValueError as e:
            logger.error(f"Facility resolution error: {e}")
            return 2
        except Exception as e:
            logger.error(f"Facility resolution failed: {e}")
            return 2

        # Check fingerprint for idempotency
        processed_log_path = Path(args.output_dir) / "processed_files.json"
        processed_fingerprints = load_processed_log(str(processed_log_path))
        file_fingerprint = compute_fingerprint(args.input)

        if file_fingerprint in processed_fingerprints and not args.force:
            logger.info(
                f"File already processed (fingerprint: {file_fingerprint[:16]}...). "
                "Skipping. Use --force to reprocess."
            )
            # Build minimal report for skipped file
            report = {
                "run_id": run_id,
                "timestamp": datetime.now().isoformat(),
                "total_files": 1,
                "succeeded": 0,
                "failed": 0,
                "routed_to_review": 0,
                "files_skipped_duplicate": 1,
                "total_input_tokens": 0,
                "total_output_tokens": 0,
                "estimated_cost_usd": 0.0,
                "per_file_summary": [
                    {
                        "filename": Path(args.input).name,
                        "facility_id": resolution.facility_id,
                        "confidence": None,
                        "flags": [],
                        "status": "skipped_duplicate",
                    }
                ],
            }
            write_run_report(report, args.output_dir)
            return 0

        try:
            result, input_tokens, output_tokens = process_single_file(
                file_path=args.input,
                facility_id=resolution.facility_id or "unknown",
                facility_data=resolution.facility_data,
                output_dir=args.output_dir,
                validate=args.validate,
                output_excel=args.output_excel,
                resolution=resolution,  # Pass resolution for flag handling
            )

            # Add fingerprint to processed log after successful processing
            processed_fingerprints.add(file_fingerprint)
            save_processed_log(str(processed_log_path), processed_fingerprints)

            # Build and write run report
            meta = result.get("_meta", {})
            report = {
                "run_id": run_id,
                "timestamp": datetime.now().isoformat(),
                "total_files": 1,
                "succeeded": 1,
                "failed": 0,
                "routed_to_review": 1 if _needs_review(result) else 0,
                "files_skipped_duplicate": 0,
                "total_input_tokens": input_tokens,
                "total_output_tokens": output_tokens,
                "estimated_cost_usd": _estimate_cost(input_tokens, output_tokens),
                "per_file_summary": [
                    {
                        "filename": Path(args.input).name,
                        "facility_id": resolution.facility_id,
                        "confidence": meta.get("confidence"),
                        "flags": meta.get("flags", []),
                        "status": "succeeded",
                    }
                ],
            }
            write_run_report(report, args.output_dir)
            logger.info("Processing completed successfully")
            return 0

        except FileNotFoundError as e:
            logger.error(f"File not found: {e}")
            return 1
        except (
            CorruptFileError,
            FileTooLargeError,
            PasswordProtectedError,
            UnsupportedFormatError,
        ) as e:
            logger.error(f"File processing error: {e}")
            return 3
        except ExtractionError as e:
            logger.error(f"Extraction error: {e}")
            return 4
        except WorkbookLockedError as e:
            logger.error(f"Excel file error: {e}")
            return 6
        except Exception as e:
            logger.exception(f"Unexpected error: {e}")
            return 5

    # ── Batch / folder mode ──
    try:
        files = _collect_supported_files(args.input_dir)
    except (FileNotFoundError, ValueError) as e:
        logger.error(str(e))
        return 1

    run_id = new_correlation_id()
    summary = BatchSummary(total=len(files))
    logger.info(f"Found {summary.total} supported file(s) in {args.input_dir}")

    # Load processed fingerprints for batch mode
    processed_log_path = Path(args.output_dir) / "processed_files.json"
    processed_fingerprints = load_processed_log(str(processed_log_path))

    for idx, file_path in enumerate(files, start=1):
        logger.info(f"Processing file {idx} of {summary.total}: {file_path.name}")

        # Resolve facility for this file
        try:
            resolution = resolve_facility_for_file(
                file_path=str(file_path),
                explicit_facility=args.facility,
                facilities=facilities,
                skip_classify=args.no_classify,
                output_dir=args.output_dir,
                facility_config=facility_config,
            )
            # Reload facilities in case auto-stub was created
            facilities = facility_config.load_facilities()
        except ValueError as e:
            logger.error(f"Facility resolution error for {file_path.name}: {e}")
            summary.failed += 1
            summary.failures.append(f"{file_path.name}: {e}")
            summary.per_file_summary.append({
                "filename": file_path.name,
                "facility_id": None,
                "confidence": None,
                "flags": [],
                "status": "failed",
            })
            continue
        except Exception as e:
            logger.error(f"Facility resolution failed for {file_path.name}: {e}")
            summary.failed += 1
            summary.failures.append(f"{file_path.name}: facility resolution failed")
            summary.per_file_summary.append({
                "filename": file_path.name,
                "facility_id": None,
                "confidence": None,
                "flags": [],
                "status": "failed",
            })
            continue

        # Check fingerprint
        file_fingerprint = compute_fingerprint(str(file_path))
        if file_fingerprint in processed_fingerprints and not args.force:
            logger.info(
                f"File already processed (fingerprint: {file_fingerprint[:16]}...). "
                "Skipping. Use --force to reprocess."
            )
            summary.skipped_duplicate += 1
            summary.per_file_summary.append({
                "filename": file_path.name,
                "facility_id": resolution.facility_id,
                "confidence": None,
                "flags": [],
                "status": "skipped_duplicate",
            })
            continue

        try:
            result, input_tokens, output_tokens = process_single_file(
                file_path=str(file_path),
                facility_id=resolution.facility_id or "unknown",
                facility_data=resolution.facility_data,
                output_dir=args.output_dir,
                validate=args.validate,
                output_excel=args.output_excel,
                resolution=resolution,  # Pass resolution for flag handling
            )
            summary.succeeded += 1
            summary.total_input_tokens += input_tokens
            summary.total_output_tokens += output_tokens

            # Add fingerprint to log after successful processing
            processed_fingerprints.add(file_fingerprint)

            meta = result.get("_meta", {})
            summary.per_file_summary.append({
                "filename": file_path.name,
                "facility_id": resolution.facility_id,
                "confidence": meta.get("confidence"),
                "flags": meta.get("flags", []),
                "status": "succeeded",
            })

            if _needs_review(result):
                summary.review_queue += 1

        except (
            FileNotFoundError,
            CorruptFileError,
            FileTooLargeError,
            PasswordProtectedError,
            UnsupportedFormatError,
            ExtractionError,
            WorkbookLockedError,
        ) as e:
            summary.failed += 1
            summary.failures.append(f"{file_path.name}: {e}")
            summary.per_file_summary.append({
                "filename": file_path.name,
                "facility_id": args.facility,
                "confidence": None,
                "flags": [],
                "status": "failed",
            })
            logger.error(f"Failed to process {file_path.name}: {e}")
        except Exception as e:
            summary.failed += 1
            summary.failures.append(f"{file_path.name}: {e}")
            summary.per_file_summary.append({
                "filename": file_path.name,
                "facility_id": args.facility,
                "confidence": None,
                "flags": [],
                "status": "failed",
            })
            logger.exception(f"Unexpected error processing {file_path.name}: {e}")

    # Save updated processed log after batch processing
    save_processed_log(str(processed_log_path), processed_fingerprints)

    # ── Print batch summary ──
    logger.info("\n" + "=" * 50)
    logger.info("BATCH PROCESSING SUMMARY")
    logger.info("=" * 50)
    logger.info(f"  Total files:       {summary.total}")
    logger.info(f"  Succeeded:         {summary.succeeded}")
    logger.info(f"  Failed:            {summary.failed}")
    logger.info(f"  Skipped (duplicate): {summary.skipped_duplicate}")
    logger.info(f"  Routed to review:  {summary.review_queue}")

    if summary.failures:
        logger.info("\nFailed files:")
        for failure in summary.failures:
            logger.info(f"  ✗ {failure}")

    logger.info("=" * 50)

    # Build and write run report
    report = {
        "run_id": run_id,
        "timestamp": datetime.now().isoformat(),
        "total_files": summary.total,
        "succeeded": summary.succeeded,
        "failed": summary.failed,
        "routed_to_review": summary.review_queue,
        "files_skipped_duplicate": summary.skipped_duplicate,
        "total_input_tokens": summary.total_input_tokens,
        "total_output_tokens": summary.total_output_tokens,
        "estimated_cost_usd": _estimate_cost(
            summary.total_input_tokens, summary.total_output_tokens
        ),
        "per_file_summary": summary.per_file_summary,
    }
    write_run_report(report, args.output_dir)

    return 1 if summary.failed == summary.total else 0


if __name__ == "__main__":
    sys.exit(main())
