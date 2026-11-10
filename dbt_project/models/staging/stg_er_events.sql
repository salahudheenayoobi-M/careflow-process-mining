-- Staging model: cleans the raw ER event log.
-- The ORDER of the steps matters:
--   1) rename columns
--   2) standardize activity names (so "xray" and "X-Ray" become the same value)
--   3) drop unusable rows (no case_id, no timestamp, unknown activity)
--   4) remove exact duplicates (only works after step 2)

with source as (

    select * from {{ source('raw', 'er_events') }}

),

renamed as (

    select
        nullif(trim(case_id), '')   as case_id,
        activity                    as raw_activity,
        `timestamp`                 as event_timestamp,
        department,
        acuity_level,
        missing_form_flag
    from source

),

standardized as (

    select
        case_id,
        -- lowercase, then remove spaces, underscores and hyphens, then map to the proper name
        case regexp_replace(lower(raw_activity), r'[\s_\-]', '')
            when 'arrival'        then 'Arrival'
            when 'registration'   then 'Registration'
            when 'triage'         then 'Triage'
            when 'xray'           then 'X-Ray'
            when 'labtest'        then 'Lab Test'
            when 'doctorconsult'  then 'Doctor Consult'
            when 'discharge'      then 'Discharge'
        end                         as activity_name,
        event_timestamp,
        department,
        acuity_level,
        missing_form_flag
    from renamed

),

valid_rows as (

    select *
    from standardized
    where case_id is not null
      and event_timestamp is not null
      and activity_name is not null

),

deduplicated as (

    select distinct * from valid_rows

)

select * from deduplicated
