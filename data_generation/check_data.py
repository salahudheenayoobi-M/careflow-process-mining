"""
CareFlow: quick sanity check of the generated CSV files.

Put this file in the  data_generation/  folder of your repo, then run:
    python data_generation/check_data.py
Run it AFTER generate_events.py.
"""

from pathlib import Path

import pandas as pd

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"

VALID_ACTIVITIES = {
    "Arrival", "Registration", "Triage", "X-Ray",
    "Lab Test", "Doctor Consult", "Discharge",
}

clean = pd.read_csv(RAW_DIR / "clean_events.csv")
dirty = pd.read_csv(RAW_DIR / "er_events.csv")

# ---------------------------------------------------------------- clean file
print("=" * 55)
print("CLEAN FILE  (expect ~9,000 rows, 1,500 patients)")
print("=" * 55)
print(f"Rows:      {len(clean):,}")
print(f"Patients:  {clean['case_id'].nunique():,}")

arrivals = clean.loc[clean["activity"] == "Arrival", "timestamp"]
# Timestamps are text in ISO format, so min/max sorts them correctly
print(f"First arrival: {arrivals.min()}")
print(f"Last arrival:  {arrivals.max()}   (expect 2025-10-21 after the NUM_DAYS fix)")

# ---------------------------------------------------------------- dirty file
print()
print("=" * 55)
print("DIRTY FILE  (planted errors)")
print("=" * 55)
print(f"Rows: {len(dirty):,}   (expect clean rows + 30 duplicates)")

print(f"Exact duplicate rows:  {dirty.duplicated().sum()}   (planted 30; a few fewer is normal)")
print(f"Missing case_id:       {dirty['case_id'].isna().sum()}   (planted 20)")
print(f"Missing timestamp:     {dirty['timestamp'].isna().sum()}   (planted 15)")

bad_names = ~dirty["activity"].isin(VALID_ACTIVITIES)
print(f"Non-standard activity names: {bad_names.sum()}   (planted 45)")
print()
print("The variant spellings found:")
print(dirty.loc[bad_names, "activity"].value_counts().to_string())
