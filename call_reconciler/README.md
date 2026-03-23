# Call Reconciler

A simple tool that matches failed phone calls against a master Excel sheet and outputs the full patient records for all matched numbers.

## What It Does

1. **Reads your master Excel file** containing all patient records with phone numbers
2. **Reads your failed calls Excel file** with phone numbers that failed to connect
3. **Matches phone numbers** between the two files (handles the `+` prefix automatically)
4. **Outputs a new Excel file** with complete patient records for every matched failed call
5. **Formats the output** with bold headers, readable fonts, and frozen top row for easy scrolling

## Installation

First, install the required software packages:

```bash
pip install pandas openpyxl
```

Or if that doesn't work, try:

```bash
pip3 install pandas openpyxl
```

## Setup

Before running, organize your files in this structure:

```
~/Desktop/ARcallback/
    Master/        ← Put exactly 1 .xlsx file here
    Errored/       ← Put exactly 1 .xlsx file here
```

The tool will automatically find the files in these folders — no file paths needed.

## Usage

Just run the script with no arguments:

```bash
python3 call_reconciler/reconcile.py
```

This will:
- Automatically find the single .xlsx file in `~/Desktop/ARcallback/Master/`
- Automatically find the single .xlsx file in `~/Desktop/ARcallback/Errored/`
- Read the master file and look for a column named `phone number`
- Read the failed calls file and look for a column named `To`
- Match phone numbers (direct string comparison)
- Create a new file: `~/Desktop/ARcallback/Failed_Calls_Full_YYYY-MM-DD.xlsx` (with today's date)
- Print a report showing how many matches were found

## How It Works

### Phone Number Matching

Both files use the same phone number format:

- **Master file**: Column `phone number` (format: `19494360836`)
- **Failed calls file**: Column `To` (format: `19494360836`)

Phone numbers are compared as strings (not numbers) to preserve any leading zeros. No normalization is needed since both columns use the same format.

### Output

The output file contains:
- **Full rows from master** for every phone number that matched a failed call
- **All columns** from the master file (preserved exactly as they appear)
- **Professional formatting**:
  - Bold header row for easy identification
  - Auto-sized columns so everything is readable
  - Arial font throughout
  - Frozen top row so headers stay visible when scrolling

The output file is saved to `~/Desktop/ARcallback/` with today's date in the filename:
- Example: `~/Desktop/ARcallback/Failed_Calls_Full_2026-02-26.xlsx`

## Example Output

When you run the tool, you'll see a report like this:

```
Master file:        Master.xlsx (3,627 rows)
Errored file:       FailedCalls.xlsx (900 numbers)

Matched:            887 rows found in master
Unmatched:          13 numbers not found in master

Output written to: ~/Desktop/ARcallback/Failed_Calls_Full_2026-02-26.xlsx
```

This tells you:
- How many total rows are in your master sheet
- How many failed call numbers were in the input file
- How many matches were found (rows written to output)
- How many failed call numbers couldn't be found in the master
- Where the output file was saved

## Required Column Names

Your Excel files must have these specific column names:

- **Master file**: Must have a column named `phone number` (case-insensitive, extra spaces ignored)
- **Failed calls file**: Must have a column named `To` (exact match required)

The order of columns doesn't matter, and the master file can have any other columns you want (they'll all be included in the output).

## Important Notes

- **Fixed folder structure**: Files must be in `~/Desktop/ARcallback/Master/` and `~/Desktop/ARcallback/Errored/`
- **Exactly one file per folder**: Each folder must contain exactly 1 .xlsx file (0 or 2+ files will cause an error)
- **Phone number format**: Both columns use the same format (`19494360836`), so direct string comparison is used
- **String comparison**: Phone numbers are compared as strings, not numbers (preserves leading zeros)
- **No deduplication**: If a phone number appears multiple times in the master, all matching rows are included
- **Overwrites existing files**: If the output file already exists, it will be replaced with the new results
- **Unmatched numbers**: Numbers in the failed calls file that don't match the master are reported but not included in the output

## Troubleshooting

### "Master/ must contain exactly 1 .xlsx file, found 0"
- Make sure you have placed exactly one .xlsx file in `~/Desktop/ARcallback/Master/`
- Check that the file has the `.xlsx` extension (not `.xls` or `.csv`)

### "Errored/ must contain exactly 1 .xlsx file, found 0"
- Make sure you have placed exactly one .xlsx file in `~/Desktop/ARcallback/Errored/`
- Check that the file has the `.xlsx` extension (not `.xls` or `.csv`)

### "Master/ must contain exactly 1 .xlsx file, found 2"
- Remove extra files from `~/Desktop/ARcallback/Master/` so only one .xlsx file remains
- The tool requires exactly one file in each folder

### "Master file must have a 'phone number' column"
- Check that your master file has a column with the header "phone number" (case doesn't matter)
- Make sure there are no extra spaces or typos in the column name

### "Failed calls file must have a 'To' column"
- Check that your failed calls file has a column with the header exactly "To" (case-sensitive)
- Make sure the column name is spelled correctly

### "Error reading [filename]"
- The file might be corrupted or password-protected
- Try opening the file in Excel first to see if there are any issues
- Make sure the file is a `.xlsx` format (not `.xls`)

### "No matches found"
- Verify that the phone numbers actually exist in both files
- Make sure both columns use the same format (`19494360836` - no `+` prefix)
- Check for any extra spaces or formatting issues in the phone number columns
