# Medical Document Processing Pipeline

A Python-based medical document processing platform for extracting patient demographic data from PDF and image facesheets using GPT-4o vision.

## Requirements

- Python 3.11+
- OpenAI API key with BAA coverage
- Tesseract OCR (required - OCR always runs)

## Installation

1. Install Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Install Tesseract OCR (required - OCR always runs):
   - **macOS**: `brew install tesseract`
   - **Linux (Debian/Ubuntu)**: `apt-get install tesseract-ocr`
   - **Linux (RHEL/CentOS)**: `yum install tesseract`
   - **Windows**: Download installer from [GitHub](https://github.com/UB-Mannheim/tesseract/wiki)

3. Copy `.env.example` to `.env` and configure:
   ```bash
   cp .env.example .env
   # Edit .env with your OPENAI_API_KEY
   ```

## Usage

```bash
python main.py --input <file.pdf> --facility <facility_id> [options]
```

### Options

- `--input`: Path to a single PDF or image file
- `--input-dir`: Path to a folder of PDF/image files for batch processing
- `--facility`: Facility ID (required)
- `--output-dir`: Output directory for JSON files (default: ./output)
- `--validate`: Run second-pass validation for MEDIUM/LOW confidence results
- `--output-excel`: Path to Excel workbook for appending results
- `--force`: Force processing even if file has been processed before
- `--verbose`: Enable verbose logging

## Features

- **OCR Grounding** (always enabled): Extracts raw text using local Tesseract OCR before sending to GPT-4o, providing a second representation for cross-reference
- **Self-Consistency Verification** (always enabled): Runs extraction twice independently and compares results field-by-field for improved accuracy

## HIPAA Compliance

- All OpenAI API calls use `store=False` (ZDR requirement)
- No PHI is logged or written to disk except final output JSON and Excel files
- All processing is local - no cloud services or external APIs that touch PHI
