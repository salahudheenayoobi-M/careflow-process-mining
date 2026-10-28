# CareFlow Data Design

## Activities
- Arrival
- Registration
- Triage
- X-Ray
- Lab Test
- Doctor Consult
- Discharge

## Paths

![CareFlow ER Patient Paths](patient_flow_paths.png)

| Path | Sequence | % of patients |
|------|----------|---------------|
| A | Arrival → Registration → Triage → Doctor Consult → Discharge | 20 |
| B | Arrival → Registration → Triage → X-Ray → Doctor Consult → Discharge | 30 |
| C | Arrival → Registration → Triage → X-Ray → Triage → Doctor Consult → Discharge | 20 |
| D | Arrival → Registration → Triage → Lab Test → Doctor Consult → Discharge | 30 |

**Total: 100%**

### Math check

| Rule | Calculation | Result |
|------|-------------|--------|
| All paths sum to 100 | 20 + 30 + 20 + 30 | **100 ✓** |
| X-Ray patients (B + C) | 30 + 20 | **50 (50% of all patients)** |
| C = 40% of X-Ray patients | 20 ÷ 50 | **0.40 = 40% ✓** |
| B = 60% of X-Ray patients | 30 ÷ 50 | **0.60 = 60% ✓** |

### Design rationale

- **B + C = 50%** — half of ER patients need imaging, realistic for a general ER.
- **C = 20%** — exactly 40% of X-Ray patients loop back to Triage (the bottleneck story).
- **D = 30%** — lab tests are the most common diagnostic in a real ER.
- **A = 20%** — patients with minor complaints who go straight to the doctor after triage.

## Waiting Times

Each row is the wait **between** two activities — the time a patient spends waiting before the next step begins. The script will sample a random value from within the min–max range for every patient.

### Normal transitions

| From | To | Min (min) | Max (min) | Notes |
|------|----|-----------|-----------|-------|
| Arrival | Registration | 2 | 8 | Quick admin check-in |
| Registration | Triage | 5 | 15 | Short queue for triage nurse |
| Triage | X-Ray | 15 | 35 | Waiting for imaging room |
| Triage | Lab Test | 10 | 30 | Waiting for blood draw |
| X-Ray | Doctor Consult | 20 | 60 | Waiting for results + doctor |
| Lab Test | Doctor Consult | 30 | 70 | Lab results take longer than imaging |
| Triage | Doctor Consult | 30 | 90 | Longest normal wait — doctor availability |
| Doctor Consult | Discharge | 10 | 30 | Paperwork, prescriptions, instructions |

### Rework transitions (Path C only)

| From | To | Min (min) | Max (min) | Notes |
|------|----|-----------|-----------|-------|
| X-Ray | Triage *(return)* | 25 | 55 | Re-queued for triage after imaging findings |
| Triage *(2nd visit)* | Doctor Consult | 40 | 120 | Back in the queue at lower priority |

### Total time comparison

This is the approximate **end-to-end wait** per path (sum of all transition waits):

| Path | Transitions | Min total (min) | Max total (min) |
|------|-------------|-----------------|-----------------|
| A | Arrival→Reg→Tri→Doc→Dis | 47 | 143 |
| B | Arrival→Reg→Tri→XR→Doc→Dis | 52 | 148 |
| C | Arrival→Reg→Tri→XR→**Tri→Doc**→Dis | 97 | 263 |
| D | Arrival→Reg→Tri→Lab→Doc→Dis | 57 | 153 |

> **Path C patients wait ~75–85 minutes longer on average** than any other path. This is the bottleneck the process-mining analysis should surface.

| Path | Average total wait (midpoint) |
|------|-------------------------------|
| A | 95 min |
| B | 100 min |
| **C** | **180 min** |
| D | 105 min |

> [!NOTE]
> The min/max ranges overlap between paths — one unlucky Path B patient can wait longer than a lucky Path C patient. That's realistic, but the honest headline is the **average** difference.

### System-wide impact

| Scenario | Calculation | Average wait |
|----------|-------------|-------------|
| Current | 0.2×95 + 0.3×100 + 0.2×180 + 0.3×105 | **~116 min** |
| If rework is fixed (Path C → Path B) | 0.2×95 + 0.5×100 + 0.3×105 | **~100 min** |
| **Savings** | | **~16 min/patient** |

### Design rationale for times

- **Arrival → Registration** and **Registration → Triage** are fast (2–15 min) — these are admin steps, not clinical bottlenecks.
- **Triage → Doctor Consult** has the widest normal range (30–90 min) because doctor availability is the primary constraint in any ER.
- **X-Ray → Triage (return)** is 25–55 min — the patient must wait for a triage nurse *again*, but the nurse now needs to review the X-Ray results first.
- **Triage (2nd) → Doctor Consult** is the slowest transition in the entire system (40–120 min) — rework patients re-enter the doctor queue behind new arrivals, making this the core of the bottleneck story.

> [!IMPORTANT]
> **Scripting note:** "Triage → Doctor Consult" appears twice with different wait ranges: **30–90 min** for the first visit and **40–120 min** for the second (rework). The generator script must select the wait based on *which Triage visit it is* (1st vs 2nd), not just the activity name pair.

## Extra Columns

Each row in the event log will have these columns beyond the standard `case_id`, `activity`, and `timestamp`:

| Column | Type | Allowed values | Logic |
|--------|------|----------------|-------|
| `department` | string | `Reception`, `Triage`, `Radiology`, `Laboratory`, `Emergency`, `Discharge` | Set per activity (see mapping below) |
| `acuity_level` | integer | `1`, `2`, `3`, `4`, `5` | Assigned once per patient at Triage; stays constant for all their events |
| `missing_form_flag` | boolean | `true`, `false` | `true` for **~90% of Path C** patients and **~5% of others** (avoids a perfect correlation that looks artificial) |

### Department mapping

| Activity | Department |
|----------|------------|
| Arrival | Reception |
| Registration | Reception |
| Triage | Triage |
| X-Ray | Radiology |
| Lab Test | Laboratory |
| Doctor Consult | Emergency |
| Discharge | Discharge |

### Acuity level distribution

ESI (Emergency Severity Index) 1–5, where 1 = most urgent:

| Level | Meaning | % of patients |
|-------|---------|---------------|
| 1 | Resuscitation | 2 |
| 2 | Emergent | 13 |
| 3 | Urgent | 45 |
| 4 | Less urgent | 30 |
| 5 | Non-urgent | 10 |

> [!NOTE]
> Acuity is independent of path. A Level 2 patient can be on Path A (no tests) or Path C (rework). The acuity column is useful for filtering and segmentation in the analysis, but it doesn't change the waiting times in this simulation.

## Size and Mess

### Dataset size

| Parameter | Value |
|-----------|-------|
| Number of patients | **1,500** |
| Date range | **2025-10-01 to 2025-10-21** (3 weeks) |
| Arrivals per day | ~71 (spread across 24 hours, weighted toward 8 AM – 10 PM) |

### Intentional data quality errors

These are planted on purpose so the cleaning script has real work to do:

| Error type | Description | Count | % of events |
|------------|-------------|-------|-------------|
| **Duplicate rows** | Exact duplicate events (same case_id, activity, timestamp) | ~30 rows | 0.33% |
| **Missing case IDs** | `case_id` is blank or `NaN` | ~20 rows | 0.22% |
| **Inconsistent activity names** | `"xray"`, `"x-ray"`, `"Xray"` instead of `"X-Ray"`; `"lab_test"` instead of `"Lab Test"` | ~45 rows | 0.50% |
| **Null timestamps** | `timestamp` is blank or `NaT` | ~15 rows | 0.17% |

**Total dirty rows: ~110 out of ~9,000 events (~1.2%)**

### Clean vs dirty file strategy

The generator will save **two files**:

| File | Path | Contents |
|------|------|----------|
| Clean copy | `data/raw/clean_events.csv` | Perfect data, no errors — used as ground truth |
| Dirty copy | `data/raw/er_events.csv` | Same data with errors planted — this is the "real" input |

> [!IMPORTANT]
> After cleaning, compare the cleaned output against `clean_events.csv` to prove the pipeline works. Row counts, activity distributions, and path frequencies should match.

### Handling dropped rows

Removing a row with a missing `case_id` or null `timestamp` deletes an event from a patient's journey, which can make a normal trace look like a fake variant (e.g., a missing Triage row makes Path B look like Arrival → Registration → X-Ray → …). The cleaning script should:

1. **Repair** where possible (fill missing case_id from surrounding rows if the rest of the trace is intact)
2. **Drop** only as a last resort
3. **Log** every action taken — this makes a strong point in the report

> [!TIP]
> The cleaning script should log every fix it makes. That way the report can say: *"We removed 30 duplicates, repaired 45 inconsistent activity names, …"* — concrete numbers make the data-quality section credible.

### Why these numbers

- **1,500 patients** — large enough for meaningful process-mining metrics, small enough to generate and inspect quickly.
- **3 weeks** — enough to show daily/weekly patterns without making the CSV unwieldy.
- **~1.2% error rate** — realistic for a hospital system; high enough to demonstrate the cleaning pipeline, low enough that the core analysis isn't swamped by noise.
