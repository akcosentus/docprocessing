#!/usr/bin/env python3
"""Call reconciler - matches failed calls against master Excel sheet by phone number."""

import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter


def to_string(phone) -> str:
    """Convert phone number to string, handling NaN and float formatting."""
    if pd.isna(phone):
        return ""
    # Convert to string and remove .0 suffix if present (from float conversion)
    phone_str = str(phone)
    if phone_str.endswith('.0'):
        phone_str = phone_str[:-2]
    return phone_str


def find_single_excel_file(directory: Path, folder_name: str) -> Path:
    """
    Find the single .xlsx file in a directory.
    
    Args:
        directory: Path to the directory to search
        folder_name: Name of the folder (for error messages)
        
    Returns:
        Path to the single .xlsx file
        
    Raises:
        SystemExit: If directory doesn't exist, has 0 files, or has more than 1 file
    """
    if not directory.exists():
        print(f"❌ Error: {folder_name}/ directory does not exist: {directory}", file=sys.stderr)
        sys.exit(1)
    
    if not directory.is_dir():
        print(f"❌ Error: {folder_name}/ is not a directory: {directory}", file=sys.stderr)
        sys.exit(1)
    
    # Find all .xlsx files
    xlsx_files = list(directory.glob("*.xlsx"))
    
    if len(xlsx_files) == 0:
        print(f"❌ Error: {folder_name}/ must contain exactly 1 .xlsx file, found 0", file=sys.stderr)
        sys.exit(1)
    
    if len(xlsx_files) > 1:
        file_list = ", ".join(f.name for f in xlsx_files)
        print(f"❌ Error: {folder_name}/ must contain exactly 1 .xlsx file, found {len(xlsx_files)}: {file_list}", file=sys.stderr)
        sys.exit(1)
    
    return xlsx_files[0]


def reconcile_calls(master_path: str, failed_path: str, output_path: str) -> None:
    """
    Reconcile failed calls against master sheet by matching phone numbers.
    
    Args:
        master_path: Path to master Excel file with 'phone number' column
        failed_path: Path to failed calls Excel file with 'To' column
        output_path: Path to write the output Excel file
    """
    # Validate input files exist
    master_file = Path(master_path)
    failed_file = Path(failed_path)
    
    if not master_file.exists():
        print(f"❌ Error: Master file does not exist: {master_path}", file=sys.stderr)
        sys.exit(1)
    
    if not failed_file.exists():
        print(f"❌ Error: Failed calls file does not exist: {failed_path}", file=sys.stderr)
        sys.exit(1)
    
    # Read master sheet
    try:
        master_df = pd.read_excel(master_path)
    except Exception as e:
        print(f"❌ Error reading master file: {e}", file=sys.stderr)
        sys.exit(1)
    
    # Check for 'phone number' column in master
    master_phone_col = None
    for col in master_df.columns:
        if str(col).strip().lower() == "phone number":
            master_phone_col = col
            break
    
    if master_phone_col is None:
        print("❌ Error: Master file must have a 'phone number' column", file=sys.stderr)
        sys.exit(1)
    
    # Read failed calls sheet
    try:
        failed_df = pd.read_excel(failed_path)
    except Exception as e:
        print(f"❌ Error reading failed calls file: {e}", file=sys.stderr)
        sys.exit(1)
    
    # Check for 'To' column in failed calls
    to_col = None
    for col in failed_df.columns:
        if str(col).strip() == "To":
            to_col = col
            break
    
    if to_col is None:
        print("❌ Error: Failed calls file must have a 'To' column", file=sys.stderr)
        sys.exit(1)
    
    # Get counts before processing
    master_row_count = len(master_df)
    failed_count = len(failed_df)
    
    # Convert phone numbers to strings for comparison
    failed_df["normalized_to"] = failed_df[to_col].apply(to_string)
    
    # Get set of failed call numbers (as strings)
    failed_numbers = set(failed_df["normalized_to"].dropna())
    failed_numbers.discard("")  # Remove empty strings
    
    # Convert master phone numbers to strings
    master_df["normalized_phone"] = master_df[master_phone_col].apply(to_string)
    
    # Filter master to only rows where phone number matches any failed call
    matched_df = master_df[master_df["normalized_phone"].isin(failed_numbers)].copy()
    
    # Remove temporary normalization columns
    matched_df = matched_df.drop(columns=["normalized_phone"], errors="ignore")
    
    matched_count = len(matched_df)
    unmatched_count = failed_count - matched_count
    
    # Create output directory if needed
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    # Write output with formatting
    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        matched_df.to_excel(writer, index=False, sheet_name="Sheet1")
        
        # Get the workbook and worksheet
        workbook = writer.book
        worksheet = writer.sheets["Sheet1"]
        
        # Format header row: bold, Arial font
        header_font = Font(bold=True, name="Arial")
        for cell in worksheet[1]:
            cell.font = header_font
        
        # Auto-size column widths
        for col in worksheet.columns:
            max_length = 0
            col_letter = get_column_letter(col[0].column)
            for cell in col:
                try:
                    if cell.value:
                        max_length = max(max_length, len(str(cell.value)))
                except:
                    pass
            adjusted_width = min(max_length + 2, 50)  # Cap at 50
            worksheet.column_dimensions[col_letter].width = adjusted_width
        
        # Freeze top row
        worksheet.freeze_panes = "A2"
        
        # Set Arial font for all cells
        arial_font = Font(name="Arial")
        for row in worksheet.iter_rows(min_row=2):
            for cell in row:
                cell.font = arial_font
    
    # Print report
    master_filename = Path(master_path).name
    failed_filename = Path(failed_path).name
    print(f"Master file:        {master_filename} ({master_row_count:,} rows)")
    print(f"Errored file:       {failed_filename} ({failed_count:,} numbers)")
    print()
    print(f"Matched:            {matched_count:,} rows found in master")
    print(f"Unmatched:          {unmatched_count:,} numbers not found in master")
    print()
    print(f"Output written to: {output_path}")


def main():
    """Main entry point."""
    # Fixed paths
    base_dir = Path.home() / "Desktop" / "ARcallback"
    master_dir = base_dir / "Master"
    errored_dir = base_dir / "Errored"
    
    # Find the single .xlsx file in each directory
    master_file = find_single_excel_file(master_dir, "Master")
    errored_file = find_single_excel_file(errored_dir, "Errored")
    
    # Generate output filename with today's date
    today = datetime.now().strftime("%Y-%m-%d")
    output_filename = f"Failed_Calls_Full_{today}.xlsx"
    output_path = str(base_dir / output_filename)
    
    reconcile_calls(str(master_file), str(errored_file), output_path)


if __name__ == "__main__":
    main()
