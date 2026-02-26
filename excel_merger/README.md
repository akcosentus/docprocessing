# Excel Merger

A simple tool to combine multiple Excel files into one master file with header validation.

## Installation

Install required dependencies:

```bash
pip install pandas openpyxl
```

## Usage

```bash
python excel_merger/merge.py --input ~/Desktop/ExcelFiles/
```

Optionally specify a custom output path:

```bash
python excel_merger/merge.py --input ~/Desktop/ExcelFiles/ --output ~/Desktop/Master.xlsx
```

## Features

- **Header Validation**: Validates that each file has the expected headers (case-insensitive, whitespace-tolerant)
- **Automatic Merging**: Combines all valid files into a single master file
- **Source Tracking**: Adds a `source_file` column to track which file each row came from
- **Formatted Output**: 
  - Bold header row
  - Auto-sized column widths
  - Arial font throughout
  - Frozen top row for easy scrolling

## Expected Headers

The tool expects these exact columns (order doesn't matter):

```
patient number, sms, practicename, patientid, patientdob, patientfirstname, 
patientlastname, patientbalance, patientcreditpresent, 1ststatementdate, 
laststatementdate, lastoutreachdate, lastpaymentdate, balanceage, aginggroup, 
statementcount, smscount, emailcount, callcount, autopay, paymentplan, 
endofcadence, address, addressline2, city, state, zip, email, servicedate, 
physicianname, primaryinsurance
```

## Output

The tool prints a report showing:
- ✅ Files that were successfully merged (with row counts)
- ❌ Files that were skipped (with reasons: missing columns, extra columns, or read errors)
- Total rows merged
- Output file path

## Limitations

- Processes up to 16 files per run
- Does not deduplicate rows (keeps all rows as-is)
- Requires exact header match (after normalization)
