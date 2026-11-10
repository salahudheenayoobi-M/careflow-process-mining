"""
CareFlow: process mining analysis with PM4Py.

Put this file in the  process_mining/  folder of your repo, then run it from
the project root:
    python process_mining/analyze_careflow.py

What it does:
  1. Reads the cleaned event table (dbt model fct_events) from BigQuery
  2. Draws the process diagrams (the "spaghetti diagram") with PM4Py
  3. Calculates the rework rate and the time it costs
  4. Finds the slowest transitions (the bottlenecks)

Before running:
    pip install pm4py pandas google-cloud-bigquery db-dtypes pyarrow
    and install Graphviz for Windows (it draws the diagrams) from graphviz.org,
    choosing the option to add it to PATH. Then close and reopen your terminal.
"""

from pathlib import Path

import pandas as pd
import pm4py
import os
os.environ["PATH"] += os.pathsep + r"C:\Program Files (x86)\Graphviz\bin"

# ---------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------
USE_BIGQUERY = True                       # False = read data/raw/clean_events.csv instead
PROJECT_ID = "careflow-513010"
EVENTS_TABLE = "careflow_dbt.fct_events"  # dataset.table created by dbt

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CLEAN_CSV = PROJECT_ROOT / "data" / "raw" / "clean_events.csv"
OUT_DIR = Path(__file__).resolve().parent / "outputs"


# ---------------------------------------------------------------------
# 1. Load the events
# ---------------------------------------------------------------------
def load_events() -> pd.DataFrame:
    """Return one row per event with: case_id, activity_name, event_timestamp, ..."""
    if USE_BIGQUERY:
        from google.cloud import bigquery

        client = bigquery.Client(project=PROJECT_ID)
        sql = f"""
            SELECT case_id, activity_name, event_timestamp,
                   department, acuity_level, missing_form_flag
            FROM `{PROJECT_ID}.{EVENTS_TABLE}`
        """
        df = client.query(sql).to_dataframe()
    else:
        df = pd.read_csv(CLEAN_CSV)
        df = df.rename(columns={"activity": "activity_name", "timestamp": "event_timestamp"})

    df["event_timestamp"] = pd.to_datetime(df["event_timestamp"], utc=True)
    return df.sort_values(["case_id", "event_timestamp"]).reset_index(drop=True)


# ---------------------------------------------------------------------
# 2. Process diagrams (PM4Py)
# ---------------------------------------------------------------------
def draw_diagrams(df: pd.DataFrame) -> None:
    # PM4Py needs to know which column is the case, the activity and the time
    log = pm4py.format_dataframe(
        df,
        case_id="case_id",
        activity_key="activity_name",
        timestamp_key="event_timestamp",
    )

    print(f"Cases:  {log['case:concept:name'].nunique():,}")
    print(f"Events: {len(log):,}")

    # Variants = the different paths patients took, with how many took each
    variants = pm4py.get_variants(log)
    ranked = sorted(variants.items(), key=lambda item: item[1], reverse=True)
    print(f"\nDifferent paths (variants) found: {len(ranked)}")
    print("Most common paths:")
    for path, count in ranked[:6]:
        print(f"  {count:5d} patients  {' -> '.join(path)}")

    # Diagram 1: how MANY patients take each arrow (the spaghetti diagram)
    dfg, start_acts, end_acts = pm4py.discover_dfg(log)
    pm4py.save_vis_dfg(dfg, start_acts, end_acts, str(OUT_DIR / "01_dfg_frequency.png"))

    # Diagram 2: how LONG each arrow takes on average (shows the bottleneck)
    perf_dfg, perf_start, perf_end = pm4py.discover_performance_dfg(log)
    pm4py.save_vis_performance_dfg(
        perf_dfg, perf_start, perf_end, str(OUT_DIR / "02_dfg_performance.png")
    )

    # Diagram 3: cleaner map that ignores rare, noisy paths
    heu_net = pm4py.discover_heuristics_net(log, dependency_threshold=0.5)
    pm4py.save_vis_heuristics_net(heu_net, str(OUT_DIR / "03_heuristics_net.png"))

    print(f"\nSaved 3 diagrams in {OUT_DIR}")


# ---------------------------------------------------------------------
# 3. Rework analysis (your headline numbers)
# ---------------------------------------------------------------------
def rework_analysis(df: pd.DataFrame) -> None:
    cases = df.groupby("case_id").agg(
        arrival=("event_timestamp", "min"),
        last_event=("event_timestamp", "max"),
        triage_visits=("activity_name", lambda s: (s == "Triage").sum()),
        had_xray=("activity_name", lambda s: (s == "X-Ray").any()),
    )
    cases["total_minutes"] = (cases["last_event"] - cases["arrival"]).dt.total_seconds() / 60
    cases["has_rework"] = cases["triage_visits"] > 1  # Triage more than once = sent back

    xray = cases[cases["had_xray"]]
    rework = xray[xray["has_rework"]]
    normal = xray[~xray["has_rework"]]

    rework_rate = len(rework) / len(xray) * 100
    avg_rework = rework["total_minutes"].mean()
    avg_normal = normal["total_minutes"].mean()

    # What-if: rework patients had waited like the other X-Ray patients
    fixed = cases["total_minutes"].copy()
    fixed[cases["has_rework"] & cases["had_xray"]] = avg_normal
    saving = cases["total_minutes"].mean() - fixed.mean()

    print("\n" + "=" * 60)
    print("REWORK ANALYSIS")
    print("=" * 60)
    print(f"Patients:                     {len(cases):,}")
    print(f"Patients who had an X-Ray:    {len(xray):,}")
    print(f"Sent back to Triage after it: {len(rework):,}  ({rework_rate:.1f}% of X-Ray patients)")
    print(f"Average total time, rework:   {avg_rework:.0f} min")
    print(f"Average total time, no rework:{avg_normal:.0f} min")
    print(f"Extra time caused by rework:  {avg_rework - avg_normal:.0f} min per affected patient")
    print(f"Average over ALL patients:    {cases['total_minutes'].mean():.0f} min")
    print(f"Saving if the form is fixed:  about {saving:.0f} min per patient on average")

    summary = pd.DataFrame(
        {
            "metric": [
                "patients", "xray_patients", "rework_patients", "rework_rate_pct",
                "avg_minutes_rework", "avg_minutes_no_rework",
                "avg_minutes_all", "estimated_saving_minutes",
            ],
            "value": [
                len(cases), len(xray), len(rework), round(rework_rate, 1),
                round(avg_rework, 1), round(avg_normal, 1),
                round(cases["total_minutes"].mean(), 1), round(saving, 1),
            ],
        }
    )
    summary.to_csv(OUT_DIR / "rework_summary.csv", index=False)


# ---------------------------------------------------------------------
# 4. Bottlenecks: average wait on every transition
# ---------------------------------------------------------------------
def transition_waits(df: pd.DataFrame) -> None:
    ev = df.copy()

    # Give the second Triage visit its own name so the rework step shows up separately
    ev["visit_no"] = ev.groupby(["case_id", "activity_name"]).cumcount() + 1
    ev["step"] = ev["activity_name"]
    ev.loc[(ev["activity_name"] == "Triage") & (ev["visit_no"] > 1), "step"] = "Triage (2nd visit)"

    ev["next_step"] = ev.groupby("case_id")["step"].shift(-1)
    ev["next_time"] = ev.groupby("case_id")["event_timestamp"].shift(-1)
    ev["minutes"] = (ev["next_time"] - ev["event_timestamp"]).dt.total_seconds() / 60

    table = (
        ev.dropna(subset=["next_step"])
        .groupby(["step", "next_step"])["minutes"]
        .agg(patients="count", avg_minutes="mean", max_minutes="max")
        .round(1)
        .reset_index()
        .sort_values("avg_minutes", ascending=False)
    )
    table.to_csv(OUT_DIR / "transition_waits_all.csv", index=False)
    table = table[table["patients"] >= 20]   # ignore rare transitions caused by dropped rows

    print("\n" + "=" * 60)
    print("SLOWEST TRANSITIONS (average wait in minutes)")
    print("=" * 60)
    print(table.head(8).to_string(index=False))

    table.to_csv(OUT_DIR / "transition_waits.csv", index=False)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print("Loading events ...")
    df = load_events()

    draw_diagrams(df)
    rework_analysis(df)
    transition_waits(df)
    print("\nDone.")


if __name__ == "__main__":
    main()
