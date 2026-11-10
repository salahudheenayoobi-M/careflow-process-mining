-- Data quality log: counts every problem found in the raw table.
-- Use these numbers in your report ("we removed 30 duplicates, repaired 45 names, ...").

with raw as (

    select * from {{ source('raw', 'er_events') }}

),

metrics as (

    select 1 as sort_order, 'raw_rows' as metric, count(*) as row_count
    from raw

    union all

    select 2, 'missing_case_id', countif(case_id is null or trim(case_id) = '')
    from raw

    union all

    select 3, 'missing_timestamp', countif(`timestamp` is null)
    from raw

    union all

    select 4, 'nonstandard_activity_names',
        countif(activity not in ('Arrival', 'Registration', 'Triage', 'X-Ray',
                                 'Lab Test', 'Doctor Consult', 'Discharge'))
    from raw

    union all

    select 5, 'exact_duplicate_rows',
        count(*) - (select count(*) from (select distinct * from raw))
    from raw

    union all

    select 6, 'rows_after_cleaning', count(*)
    from {{ ref('stg_er_events') }}

)

select metric, row_count
from metrics
order by sort_order
