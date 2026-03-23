# Document Processing & Excel Automation Tools

This repository contains three standalone automation tools for medical document processing and Excel file management.

## Tools Overview

1. **[Document Processor](document_processor/)** - AI-powered extraction of patient data from PDF/image facesheets
2. **[Excel Merger](excel_merger/)** - Combines multiple Excel files into one master file
3. **[Call Reconciler](call_reconciler/)** - Matches failed phone calls against master Excel sheet

---

## 1. Document Processor

**What it does:** Extracts patient demographic data from medical document facesheets (PDFs/images) using GPT-4o vision, OCR, and self-consistency verification.

### Quick Start

```bash
# Process a single file
python document_processor/main.py \
  --input ~/Downloads/patient_facesheet.pdf \
  --validate \
  --verbose

# Process all files in a folder
python document_processor/main.py \
  --input ~/Downloads/facesheets/ \
  --validate \
  --verbose
```

### Key Features

- **OCR Grounding** - Always enabled, uses Tesseract to extract raw text
- **Self-Consistency Check** - Always enabled, runs extraction twice and compares results
- **Facility Auto-Detection** - Automatically identifies which facility sent the document
- **Validation** - Checks DOB format, SSN shape, state codes
- **Excel Output** - Writes to `PatientDemographics.xlsx` with color-coded confidence levels

### Output

- JSON files in `document_processor/output/`
- Excel file: `PatientDemographics.xlsx` (appends new rows)
- Terminal report with token counts and costs

### Full Documentation

See [document_processor/README.md](document_processor/README.md) for complete details.

---

## 2. Excel Merger

**What it does:** Combines multiple Excel files from a folder into one master file with header validation.

### Quick Start

```bash
# Basic usage (uses default OneDrive output location)
python3 excel_merger/merge.py --input ~/Desktop/ExcelFiles/

# Custom output location
python3 excel_merger/merge.py \
  --input ~/Desktop/ExcelFiles/ \
  --output ~/Desktop/Master.xlsx
```

### Key Features

- **Header Validation** - Ensures all files have the correct 31 required columns
- **Source Tracking** - Adds `source_file` column to track origin
- **Professional Formatting** - Bold headers, Arial font, frozen top row, auto-sized columns
- **Default Output** - Saves to OneDrive: `~/Library/CloudStorage/OneDrive-Cosentus,LLC/Cindy 2026/Cindy Batch Final/Master.xlsx`

### Output

- Master Excel file with all rows from valid input files
- Terminal report showing merged files and skipped files

### Full Documentation

See [excel_merger/README.md](excel_merger/README.md) for complete details.

---

## 3. Call Reconciler

**What it does:** Matches failed phone calls against a master Excel sheet and outputs full patient records for matched numbers.

### Quick Start

```bash
# Just run it - no arguments needed!
python3 call_reconciler/reconcile.py
```

### Setup Required

Before running, organize your files:

```
~/Desktop/ARcallback/
    Master/        ← Put exactly 1 .xlsx file here
    Errored/       ← Put exactly 1 .xlsx file here
```

### Key Features

- **Auto-Detection** - Automatically finds files in fixed locations
- **Phone Number Matching** - Direct string comparison (both use format `19494360836`)
- **Full Row Output** - Returns complete patient records from master for all matched calls
- **Professional Formatting** - Bold headers, Arial font, frozen top row, auto-sized columns

### Output

- Excel file: `~/Desktop/ARcallback/Failed_Calls_Full_{date}.xlsx`
- Terminal report showing match counts and unmatched numbers

### Full Documentation

See [call_reconciler/README.md](call_reconciler/README.md) for complete details.

---

## Installation

### Common Dependencies

All tools require:
```bash
pip install pandas openpyxl
```

### Document Processor Additional Requirements

```bash
# Install document processor dependencies
pip install -r document_processor/requirements.txt

# Install Tesseract OCR (required)
# macOS:
brew install tesseract

# Linux (Debian/Ubuntu):
apt-get install tesseract-ocr

# Configure OpenAI API key
cp document_processor/.env.example document_processor/.env
# Edit document_processor/.env with your OPENAI_API_KEY
```

---

## Quick Reference

### Document Processor
```bash
# Single file
python document_processor/main.py --input file.pdf --validate --verbose

# Batch folder
python document_processor/main.py --input folder/ --validate --verbose
```

### Excel Merger
```bash
python3 excel_merger/merge.py --input ~/Desktop/ExcelFiles/
```

### Call Reconciler
```bash
# Setup: Put files in ~/Desktop/ARcallback/Master/ and Errored/
python3 call_reconciler/reconcile.py
```

---

## Workflow Examples

### Complete Workflow: Document Processing → Excel Merge → Call Reconciliation

1. **Process medical documents:**
   ```bash
   python document_processor/main.py --input ~/Downloads/facesheets/ --validate --verbose
   ```
   Output: `PatientDemographics.xlsx` with extracted data

2. **Merge multiple Excel files:**
   ```bash
   python3 excel_merger/merge.py --input ~/Desktop/ExcelFiles/
   ```
   Output: `Master.xlsx` with all merged data

3. **Reconcile failed calls:**
   - Place master file in `~/Desktop/ARcallback/Master/`
   - Place failed calls file in `~/Desktop/ARcallback/Errored/`
   ```bash
   python3 call_reconciler/reconcile.py
   ```
   Output: `Failed_Calls_Full_{date}.xlsx` with matched records

---

## Troubleshooting

### Document Processor Issues
- **Missing Tesseract**: Install with `brew install tesseract` (macOS) or package manager (Linux)
- **API Errors**: Check `.env` file has valid `OPENAI_API_KEY`
- **No matches found**: See [document_processor/README.md](document_processor/README.md) troubleshooting section

### Excel Merger Issues
- **Missing columns**: Check that all files have the required 31 columns (see README)
- **Permission errors**: Ensure write access to output directory

### Call Reconciler Issues
- **"Must contain exactly 1 .xlsx file"**: Each folder needs exactly one `.xlsx` file
- **No matches**: Verify phone numbers exist in both files and use same format

---

## Project Structure

```
docprocessing/
├── README.md                    ← You are here
├── document_processor/          ← AI document extraction tool
│   ├── main.py
│   ├── README.md
│   ├── requirements.txt
│   ├── config/
│   ├── src/
│   └── tests/
├── excel_merger/                ← Excel file merger tool
│   ├── merge.py
│   └── README.md
└── call_reconciler/             ← Call reconciliation tool
    ├── reconcile.py
    └── README.md
```

---

## Need Help?

Each tool has its own detailed README:
- [Document Processor README](document_processor/README.md)
- [Excel Merger README](excel_merger/README.md)
- [Call Reconciler README](call_reconciler/README.md)
