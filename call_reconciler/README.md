# Call Reconciler

Matches a **subsheet** (subset of phone numbers) to a **master** Excel file and writes **full master rows** for every phone that appears in both.

## Setup

Put exactly **one** data file in each folder. Supported types: **`.csv`**, **`.xlsx`**, **`.xls`** (pandas).

```
~/Desktop/processing/
    master/      ← one .csv / .xlsx / .xls (column: phone number)
    subsheet/    ← one .csv / .xlsx / .xls (column: To OR phone number)
```

Output is written to the **processing** folder root:

`~/Desktop/processing/Matched_To_Master_YYYY-MM-DD.xlsx`

## Usage

```bash
python3 call_reconciler/reconcile.py
```

## Columns

| File | Required column |
|------|-----------------|
| **Master** | `phone number` (case-insensitive, extra spaces ignored) |
| **Subsheet** | `To` (exact header) **or** `phone number` (case-insensitive) |

Phones are matched after normalizing: whitespace trimmed and a leading **`+`** removed (so `+12532299884` matches `12532299884`). If the same phone appears on multiple master rows, **all** matching rows are included in the output.

## Output

- All columns from the master, for rows whose `phone number` is in the subsheet phone set.
- Bold header row, Arial font, frozen top row, auto-sized columns.

## Notes

- Each of `master/` and `subsheet/` must contain **exactly one** supported file (`.csv`, `.xlsx`, or `.xls`). Remove extra copies so only one remains per folder.
- Re-running on the same date **overwrites** `Matched_To_Master_<today>.xlsx`.
- **Unmatched** subsheet phones are reported in the terminal only (not listed in the Excel file).

## Installation

```bash
pip install pandas openpyxl
```

## Troubleshooting

- **master/ must contain exactly 1 data file** — remove extra `.csv`/`.xlsx` or add the missing file.
- **Master file must have a 'phone number' column** — check the header spelling.
- **Subsheet must have 'To' or 'phone number'** — add or rename the column.
