"""
CareFlow ER Event Log Generator
================================
Generates a synthetic event log for emergency room process mining.
Based on the data design in docs/data_design.md.

Outputs:
    data/raw/clean_events.csv  — perfect data (ground truth)
    data/raw/er_events.csv     — same data with planted errors (dirty copy)
"""

import random
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path

# ──────────────────────────────────────────────────────────────────────
# STAGE 1: Configuration
# ──────────────────────────────────────────────────────────────────────

SEED = 42
random.seed(SEED)

NUM_PATIENTS = 1_500
START_DATE = datetime(2025, 10, 1)
END_DATE = datetime(2025, 10, 21)
NUM_DAYS = (END_DATE - START_DATE).days + 1  # 21 days  

# Path definitions: name → (sequence of activities, probability)
PATHS = {
    "A": (["Arrival", "Registration", "Triage", "Doctor Consult", "Discharge"], 0.20),
    "B": (["Arrival", "Registration", "Triage", "X-Ray", "Doctor Consult", "Discharge"], 0.30),
    "C": (["Arrival", "Registration", "Triage", "X-Ray", "Triage_2", "Doctor Consult", "Discharge"], 0.20),
    "D": (["Arrival", "Registration", "Triage", "Lab Test", "Doctor Consult", "Discharge"], 0.30),
}

# Wait-time ranges in minutes: (from_activity, to_activity) → (min, max)
# "Triage_2" is used internally for the second Triage visit in Path C
WAIT_RANGES = {
    ("Arrival", "Registration"):       (2, 8),
    ("Registration", "Triage"):        (5, 15),
    ("Triage", "X-Ray"):               (15, 35),
    ("Triage", "Lab Test"):            (10, 30),
    ("Triage", "Doctor Consult"):      (30, 90),
    ("X-Ray", "Doctor Consult"):       (20, 60),
    ("X-Ray", "Triage_2"):             (25, 55),     # rework return
    ("Triage_2", "Doctor Consult"):    (40, 120),    # rework → doctor (slow!)
    ("Lab Test", "Doctor Consult"):    (30, 70),
    ("Doctor Consult", "Discharge"):   (10, 30),
}

# Department mapping
DEPARTMENT_MAP = {
    "Arrival":        "Reception",
    "Registration":   "Reception",
    "Triage":         "Triage",
    "Triage_2":       "Triage",       # same department, second visit
    "X-Ray":          "Radiology",
    "Lab Test":       "Laboratory",
    "Doctor Consult": "Emergency",
    "Discharge":      "Discharge",
}

# Acuity level (ESI) distribution: level → weight
ACUITY_LEVELS = [1, 2, 3, 4, 5]
ACUITY_WEIGHTS = [2, 13, 45, 30, 10]  # must sum to 100

# Arrival hour weights (0–23), heavier during 8 AM – 10 PM
HOUR_WEIGHTS = [
    1, 1, 1, 1, 1, 1, 1, 2,   # 00:00–07:59  (quiet overnight)
    5, 7, 8, 8, 7, 6, 6, 7,   # 08:00–15:59  (busy daytime)
    8, 7, 6, 5, 4, 3, 2, 1,   # 16:00–23:59  (tapering evening)
]

# Intentional error counts
NUM_DUPLICATES = 30
NUM_MISSING_CASE_IDS = 20
NUM_INCONSISTENT_NAMES = 45
NUM_NULL_TIMESTAMPS = 15

# Inconsistent name variants
NAME_VARIANTS = {
    "X-Ray":    ["xray", "x-ray", "Xray", "X ray"],
    "Lab Test": ["lab_test", "lab test", "LabTest", "Lab_Test"],
}


# ──────────────────────────────────────────────────────────────────────
# STAGE 2: Generate ONE patient
# ──────────────────────────────────────────────────────────────────────

def pick_path() -> tuple[str, list[str]]:
    """Pick a random path based on configured probabilities."""
    path_names = list(PATHS.keys())
    path_weights = [PATHS[p][1] for p in path_names]
    chosen = random.choices(path_names, weights=path_weights, k=1)[0]
    return chosen, list(PATHS[chosen][0])  # return a copy of the sequence


def pick_arrival_time() -> datetime:
    """Pick a random arrival datetime within the date range, weighted by hour."""
    day_offset = random.randint(0, NUM_DAYS - 1)
    hour = random.choices(range(24), weights=HOUR_WEIGHTS, k=1)[0]
    minute = random.randint(0, 59)
    second = random.randint(0, 59)
    return START_DATE + timedelta(days=day_offset, hours=hour, minutes=minute, seconds=second)


def generate_patient(case_id: int) -> list[dict]:
    """Generate all events for a single patient."""
    path_name, activities = pick_path()
    arrival_time = pick_arrival_time()

    # Assign acuity (once per patient)
    acuity = random.choices(ACUITY_LEVELS, weights=ACUITY_WEIGHTS, k=1)[0]

    # Assign missing_form_flag (probabilistic, not deterministic)
    if path_name == "C":
        missing_form = random.random() < 0.90  # ~90% for Path C
    else:
        missing_form = random.random() < 0.05  # ~5% for others

    events = []
    current_time = arrival_time

    for i, activity in enumerate(activities):
        # Add wait time (skip for the first activity — Arrival is instant)
        if i > 0:
            prev_activity = activities[i - 1]
            wait_key = (prev_activity, activity)
            min_wait, max_wait = WAIT_RANGES[wait_key]
            wait_minutes = random.randint(min_wait, max_wait)
            current_time = current_time + timedelta(minutes=wait_minutes)

        # The CSV activity name: "Triage_2" becomes "Triage" in output
        display_activity = "Triage" if activity == "Triage_2" else activity

        events.append({
            "case_id": f"P-{case_id:04d}",
            "activity": display_activity,
            "timestamp": current_time,
            "department": DEPARTMENT_MAP[activity],
            "acuity_level": acuity,
            "missing_form_flag": missing_form,
            "path": path_name,  # kept for verification, can drop later
        })

    return events


# ──────────────────────────────────────────────────────────────────────
# STAGE 3: Loop for all patients
# ──────────────────────────────────────────────────────────────────────

def generate_all_patients() -> pd.DataFrame:
    """Generate events for all patients and return a DataFrame."""
    all_events = []
    for i in range(1, NUM_PATIENTS + 1):
        all_events.extend(generate_patient(i))

    df = pd.DataFrame(all_events)
    # Sort by timestamp for a realistic event log
    df = df.sort_values("timestamp").reset_index(drop=True)
    return df


# ──────────────────────────────────────────────────────────────────────
# STAGE 4: Verify and save
# ──────────────────────────────────────────────────────────────────────

def verify_clean_data(df: pd.DataFrame) -> None:
    """Run sanity checks on the clean data."""
    print("=" * 60)
    print("VERIFICATION — Clean Data")
    print("=" * 60)

    # Total rows
    total_rows = len(df)
    print(f"\nTotal events: {total_rows:,}  (expected ~9,000)")

    # Unique patients
    n_patients = df["case_id"].nunique()
    print(f"Unique patients: {n_patients:,}  (expected {NUM_PATIENTS:,})")

    # Path distribution
    path_counts = df.groupby("path")["case_id"].nunique()
    print(f"\nPath distribution (patients):")
    for path_name in sorted(path_counts.index):
        count = path_counts[path_name]
        pct = count / n_patients * 100
        print(f"  Path {path_name}: {count:,} ({pct:.1f}%)  — expected {PATHS[path_name][1]*100:.0f}%")

    # X-Ray rework rate
    xray_patients = path_counts.get("B", 0) + path_counts.get("C", 0)
    rework_patients = path_counts.get("C", 0)
    rework_rate = rework_patients / xray_patients * 100 if xray_patients > 0 else 0
    print(f"\nX-Ray rework rate: {rework_rate:.1f}%  (expected 40%)")

    # Average total wait per path
    print(f"\nAverage total wait per path (minutes):")
    for path_name in sorted(PATHS.keys()):
        path_df = df[df["path"] == path_name]
        patient_durations = []
        for cid, group in path_df.groupby("case_id"):
            duration = (group["timestamp"].max() - group["timestamp"].min()).total_seconds() / 60
            patient_durations.append(duration)
        avg_duration = sum(patient_durations) / len(patient_durations) if patient_durations else 0
        print(f"  Path {path_name}: {avg_duration:.0f} min")

    expected_avgs = {"A": 95, "B": 100, "C": 180, "D": 105}
    print(f"  Expected:  A≈95, B≈100, C≈180, D≈105")
    print()


def plant_errors(df: pd.DataFrame) -> pd.DataFrame:
    """Plant intentional data quality errors on a copy of the DataFrame."""
    dirty = df.copy()
    n = len(dirty)

    # --- 1. Duplicate rows (~30) ---
    dup_indices = random.sample(range(n), NUM_DUPLICATES)
    duplicates = dirty.iloc[dup_indices].copy()
    dirty = pd.concat([dirty, duplicates], ignore_index=True)
    print(f"Planted {NUM_DUPLICATES} duplicate rows")

    # --- 2. Missing case IDs (~20) ---
    missing_id_indices = random.sample(range(n), NUM_MISSING_CASE_IDS)
    dirty.loc[missing_id_indices, "case_id"] = None
    print(f"Planted {NUM_MISSING_CASE_IDS} missing case IDs")

    # --- 3. Inconsistent activity names (~45) ---
    # Find rows with X-Ray or Lab Test
    xray_mask = dirty["activity"] == "X-Ray"
    lab_mask = dirty["activity"] == "Lab Test"
    xray_indices = dirty.index[xray_mask].tolist()
    lab_indices = dirty.index[lab_mask].tolist()

    # Split ~45 roughly proportionally
    n_xray_corrupt = min(30, len(xray_indices))
    n_lab_corrupt = min(15, len(lab_indices))

    chosen_xray = random.sample(xray_indices, n_xray_corrupt)
    chosen_lab = random.sample(lab_indices, n_lab_corrupt)

    for idx in chosen_xray:
        dirty.at[idx, "activity"] = random.choice(NAME_VARIANTS["X-Ray"])
    for idx in chosen_lab:
        dirty.at[idx, "activity"] = random.choice(NAME_VARIANTS["Lab Test"])

    total_name_errors = n_xray_corrupt + n_lab_corrupt
    print(f"Planted {total_name_errors} inconsistent activity names ({n_xray_corrupt} X-Ray, {n_lab_corrupt} Lab Test)")

    # --- 4. Null timestamps (~15) ---
    null_ts_indices = random.sample(range(len(dirty)), NUM_NULL_TIMESTAMPS)
    dirty.loc[null_ts_indices, "timestamp"] = pd.NaT
    print(f"Planted {NUM_NULL_TIMESTAMPS} null timestamps")

    # Shuffle so duplicates aren't all at the bottom
    dirty = dirty.sample(frac=1, random_state=SEED).reset_index(drop=True)

    total_errors = NUM_DUPLICATES + NUM_MISSING_CASE_IDS + total_name_errors + NUM_NULL_TIMESTAMPS
    print(f"\nTotal planted errors: {total_errors}")
    return dirty


def main():
    # Resolve output paths relative to the project root
    script_dir = Path(__file__).resolve().parent
    project_root = script_dir.parent
    raw_dir = project_root / "data" / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    clean_path = raw_dir / "clean_events.csv"
    dirty_path = raw_dir / "er_events.csv"

    # Generate clean data
    print("Generating 1,500 patients...")
    clean_df = generate_all_patients()

    # Verify
    verify_clean_data(clean_df)

    # Save clean copy (drop the 'path' column — it's for verification only)
    clean_export = clean_df.drop(columns=["path"])
    clean_export.to_csv(clean_path, index=False)
    print(f"Saved clean data: {clean_path} ({len(clean_export):,} rows)")

    # Plant errors and save dirty copy
    print("\nPlanting errors...")
    dirty_df = plant_errors(clean_df)
    dirty_export = dirty_df.drop(columns=["path"])
    dirty_export.to_csv(dirty_path, index=False)
    print(f"\nSaved dirty data:  {dirty_path} ({len(dirty_export):,} rows)")

    print("\n✓ Done!")


if __name__ == "__main__":
    main()
