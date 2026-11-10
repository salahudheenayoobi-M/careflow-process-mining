-- Case-level table: one row per patient visit.
-- Feeds the Power BI KPIs: average wait, rework rate, X-Ray patients, and so on.

select
    case_id,
    min(event_timestamp)                                         as arrival_time,
    max(event_timestamp)                                         as last_event_time,
    timestamp_diff(max(event_timestamp), min(event_timestamp), minute) as total_minutes,
    countif(activity_name = 'Triage')                            as triage_visits,
    countif(activity_name = 'Triage') > 1                        as has_rework,   -- Triage more than once
    countif(activity_name = 'X-Ray') > 0                         as had_xray,
    logical_or(missing_form_flag)                                as missing_form_flag,
    any_value(acuity_level)                                      as acuity_level
from {{ ref('stg_er_events') }}
group by case_id
