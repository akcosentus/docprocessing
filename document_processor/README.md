# Medical Document Processing Pipeline

Extracts patient demographic data from PDF and image facesheets using GPT-4o vision, local OCR, and self-consistency checks.

## Requirements

- Python 3.11+ (3.10 may work; CI targets 3.11+)
- OpenAI API key (BAA-covered deployment as required by your org)
- Tesseract OCR (required — OCR always runs)

## Installation

1. Dependencies:

   ```bash
   pip install -r requirements.txt
   ```

   If `pip install` is blocked (PEP 668 on macOS/Homebrew Python), use a venv:

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

2. Tesseract (required):

   - **macOS:** `brew install tesseract`
   - **Debian/Ubuntu:** `apt-get install tesseract-ocr`
   - **RHEL/CentOS:** `yum install tesseract`
   - **Windows:** [UB Mannheim installer](https://github.com/UB-Mannheim/tesseract/wiki)

3. Environment:

   ```bash
   cp .env.example .env
   # Set OPENAI_API_KEY (and optionally MODEL_SNAPSHOT, OUTPUT_EXCEL, etc.)
   ```

## Usage

Run from the **repository root** (or `cd document_processor` and use paths below relative to that folder).

You must pass **exactly one** of: `--input`, `--input-dir`, or `--batch-folder`.

### Single file

```bash
python document_processor/main.py --input /path/to/facesheet.pdf
```

### Batch folder (all supported files in that folder, non-recursive)

```bash
python document_processor/main.py --input-dir /path/to/facesheets/
```

### Dated batch layout (recommended)

Put PDFs/images in `<date>/start/`. Outputs go to `<date>/end/output/` (JSON, reports) and Excel defaults to `<date>/end/PatientDemographics.xlsx` unless overridden.

```bash
python document_processor/main.py --batch-folder ~/Desktop/facesheets/03-23 --validate --verbose
```

### Main options

| Flag | Description |
|------|-------------|
| `--input` | Single PDF or image file |
| `--input-dir` | Folder of PDFs/images (batch) |
| `--batch-folder` | Folder containing `start/` (inputs) and `end/` (outputs + default Excel path) |
| `--facility` | Facility ID from `config/facilities.json` (optional — omit for auto-classification) |
| `--no-classify` | Skip auto-detection; **requires** `--facility` |
| `--output-dir` | JSON + run reports directory (default `./output`, or `<batch-folder>/end/output` with `--batch-folder`) |
| `--output-excel` | Workbook to append (default: `OUTPUT_EXCEL` in `.env`, or `~/Desktop/PatientDemographics/PatientDemographics.xlsx`) |
| `--validate` | Force second-pass validation in addition to the automatic rules below |
| `--force` | Reprocess even if file fingerprint is already in `processed_files.json` |
| `--verbose` | DEBUG logging |

### Facility routing

- If **`--facility`** is set, that facility is used and classification is skipped.
- If **`--facility`** is omitted (default), the tool classifies the first page and matches `config/facilities.json` (including auto-stubs for new names when appropriate).
- **`--no-classify`** without **`--facility`** exits with an error.

### Validation passes

- **Local validation** (`validator.py`) always runs on the merged result (format checks).
- **Second-pass LLM validation** runs when you pass **`--validate`**, or when the merged result is MEDIUM/LOW confidence or has conflicts (`should_run_validation_pass`).

### Outputs

- Per-file JSON: `<stem>_<timestamp>.json` under `--output-dir`
- Run report: `run_report_<timestamp>.json` (metadata, no PHI in structured fields beyond filenames)
- Idempotency log: `processed_files.json` (content hashes)
- Excel: new row per file on sheet `Extractions` (color-coded confidence / flags) at `--output-excel`

### Supported input types

See `src/pdf_handler.py`: typically `.pdf`, `.jpg`, `.jpeg`, `.png`, `.tif`, `.tiff`.

## Features

- **OCR grounding** (always on): Tesseract text is sent with the image for cross-check.
- **Self-consistency** (always on): two extraction passes per page; disagreements are flagged/nulled per `consistency.py`.
- **Multi-page**: one row in Excel per document; JSON merges pages.

## HIPAA / data handling notes

- OpenAI calls use `store=False` in code (`extractor.py`).
- Avoid committing `.env`, `output/`, or logs with PHI. Use `.env.example` only for template keys.

## More help

- Tests: `pytest` from `document_processor/` with dependencies installed.
- Facility list: `config/facilities.json`.
