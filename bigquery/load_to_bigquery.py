"""
CareFlow: load the raw (dirty) ER event log into BigQuery.

Put this file in the  bigquery/  folder of your repo.
It reads  data/raw/er_events.csv  and writes it to the table
    <PROJECT_ID>.careflow.raw_events

Before running:
    pip install google-cloud-bigquery
    gcloud auth application-default login      (one-time login)
Then change PROJECT_ID below to your own Google Cloud project ID.
"""

from pathlib import Path

from google.cloud import bigquery

# ---------------------------------------------------------------------
# Settings: change PROJECT_ID, the rest can stay as they are
# ---------------------------------------------------------------------
PROJECT_ID = "your-gcp-project-id"   # <-- CHANGE THIS (shown in the BigQuery project picker)
DATASET = "careflow"
TABLE = "raw_events"
LOCATION = "US"                      # dataset location; keep the same one for dbt later

CSV_PATH = Path(__file__).resolve().parent.parent / "data" / "raw" / "er_events.csv"

# The raw layer keeps the data exactly as it arrived (dirty values included).
# Blank cells in the CSV become NULL, which dbt will deal with in the cleaning step.
SCHEMA = [
    bigquery.SchemaField("case_id", "STRING"),
    bigquery.SchemaField("activity", "STRING"),
    bigquery.SchemaField("timestamp", "TIMESTAMP"),
    bigquery.SchemaField("department", "STRING"),
    bigquery.SchemaField("acuity_level", "INTEGER"),
    bigquery.SchemaField("missing_form_flag", "BOOLEAN"),
]


def main() -> None:
    if PROJECT_ID == "your-gcp-project-id":
        raise SystemExit("Edit PROJECT_ID at the top of this file first.")
    if not CSV_PATH.exists():
        raise SystemExit(f"CSV not found: {CSV_PATH}\nRun the generator script first.")

    client = bigquery.Client(project=PROJECT_ID)

    # 1. Make sure the dataset exists (does nothing if it is already there)
    dataset = bigquery.Dataset(f"{PROJECT_ID}.{DATASET}")
    dataset.location = LOCATION
    client.create_dataset(dataset, exists_ok=True)

    # 2. Describe the load job
    table_id = f"{PROJECT_ID}.{DATASET}.{TABLE}"
    job_config = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.CSV,
        skip_leading_rows=1,  # skip the header row
        schema=SCHEMA,
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,  # re-running replaces the table
    )

    # 3. Upload the file and wait for it to finish
    print(f"Uploading {CSV_PATH.name} to {table_id} ...")
    with open(CSV_PATH, "rb") as f:
        job = client.load_table_from_file(f, table_id, job_config=job_config)
    job.result()

    # 4. Confirm
    table = client.get_table(table_id)
    print(f"Done. {table.num_rows:,} rows are now in {table_id}")


if __name__ == "__main__":
    main()
