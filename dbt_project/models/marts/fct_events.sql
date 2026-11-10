-- Event-level table: one row per patient event.
-- This is the table PM4Py will read (case_id, activity_name, event_timestamp).
-- The extra columns show the next step and the wait until it, which is
-- what makes bottlenecks visible.

select
    case_id,
    activity_name,
    event_timestamp,
    department,
    acuity_level,
    missing_form_flag,
    row_number() over w                                                       as step_number,
    lead(activity_name) over w                                                as next_activity,
    timestamp_diff(lead(event_timestamp) over w, event_timestamp, minute)     as minutes_to_next
from {{ ref('stg_er_events') }}
window w as (partition by case_id order by event_timestamp)
