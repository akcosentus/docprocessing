# Excel Merger

A simple tool that combines multiple Excel files from a folder into one master file. Perfect for merging patient data files that all have the same structure.

## What It Does

1. **Reads all Excel files** from a folder you specify
2. **Checks each file** to make sure it has the correct column headers
3. **Combines all valid files** into one master Excel file
4. **Adds a "source_file" column** so you can see which original file each row came from
5. **Formats the output** with bold headers, readable fonts, and frozen top row for easy scrolling

## Installation

Install dependencies:

```bash
pip install pandas openpyxl
```

If your system Python blocks `pip install` (PEP 668), use a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install pandas openpyxl
```

Or try:

```bash
pip3 install pandas openpyxl
```

## Usage

### Basic Usage (Uses Default Output Location)

```bash
python3 excel_merger/merge.py --input ~/Desktop/ExcelFiles/
```

This will:
- Read all `.xlsx` files from the `ExcelFiles` folder
- Create a master file at: `~/Library/CloudStorage/OneDrive-Cosentus,LLC/Cindy 2026/Cindy Batch Final/Master.xlsx`

### Custom Output Location

If you want to save the master file somewhere else:

```bash
python3 excel_merger/merge.py --input ~/Desktop/ExcelFiles/ --output ~/Desktop/Master.xlsx
```

## How It Works

### Step 1: Header Validation

Before merging, the tool checks that each Excel file has **all 31 required columns**. The column names must match exactly (after removing extra spaces and ignoring capitalization). The order of columns doesn't matter.

**Example:** If your file has "Patient Number" or "PATIENT NUMBER" or "  patient number  ", it will be recognized as correct.

### Step 2: File Processing

- ✅ **Valid files** are merged into the master file
- ❌ **Invalid files** are skipped and reported with the reason (missing columns, extra columns, or read errors)

### Step 3: Output Creation

The master file is created with:
- All rows from all valid files stacked together
- A `source_file` column added as the first column showing the original filename
- Professional formatting:
  - **Bold header row** for easy identification
  - **Auto-sized columns** so everything is readable
  - **Arial font** throughout
  - **Frozen top row** so headers stay visible when scrolling

## Required Column Headers

Your Excel files must have these **exact 31 columns** (column order doesn't matter):

```
patient number
sms
practicename
patientid
patientdob
patientfirstname
patientlastname
patientbalance
patientcreditpresent
1ststatementdate
laststatementdate
lastoutreachdate
lastpaymentdate
balanceage
aginggroup
statementcount
smscount
emailcount
callcount
autopay
paymentplan
endofcadence
address
addressline2
city
state
zip
email
servicedate
physicianname
primaryinsurance
```

**Note:** Column names are case-insensitive and extra spaces are ignored. So "Patient Number", "PATIENT NUMBER", and "  patient number  " are all acceptable.

## Example Output

When you run the tool, you'll see a report like this:

```
Confirmed output path: /Users/.../Master.xlsx

✅ Merged:   file1.xlsx (243 rows)
✅ Merged:   file2.xlsx (187 rows)
❌ Skipped:  file3.xlsx — missing columns: ['patientdob', 'zip']
❌ Skipped:  file4.xlsx — extra columns: ['unknownfield']

Total rows merged: 430
Output written to: /Users/.../Master.xlsx
```

This tells you:
- Which files were successfully merged and how many rows each had
- Which files were skipped and why
- The total number of rows in your master file
- Where the master file was saved

## Important Notes

- **No file limit**: The tool processes all `.xlsx` files found in the input folder
- **No deduplication**: All rows are kept exactly as they appear in the original files
- **Overwrites existing files**: If `Master.xlsx` already exists, it will be replaced with the new merge
- **Only processes `.xlsx` files**: Other file types (`.xls`, `.csv`, etc.) are ignored

## Troubleshooting

### "No .xlsx files found"
- Make sure the folder path is correct
- Check that your files have the `.xlsx` extension (not `.xls`)

### "No valid files to merge"
- All files failed header validation
- Check the error messages to see which columns are missing or extra
- Make sure all 31 required columns are present in your files

### "Error reading [filename]"
- The file might be corrupted or password-protected
- Try opening the file in Excel first to see if there are any issues

### Permission errors
- Make sure you have write access to the output folder
- If using the default OneDrive path, make sure OneDrive is synced and accessible
