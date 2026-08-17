-- 0015_activity_window.sql
-- Shift the activity window to straddle today.
--
-- A purely backward-looking window is wrong for a service business: the work
-- that matters most is the work still to come, and 0014's window made a
-- calendar full of upcoming jobs render as an empty chart.
--
-- Ten days back, three forward. Revenue stays meaningfully historical while
-- scheduled jobs are visible.

-- Dropped rather than replaced: CREATE OR REPLACE VIEW can only append
-- columns, and this adds is_future in the middle, which Postgres reads as
-- renaming an existing column.
drop view if exists v_daily_activity;

create view v_daily_activity
with (security_invoker = on) as
with days as (
  select generate_series(
    (current_date - interval '10 days')::date,
    (current_date + interval '3 days')::date,
    interval '1 day'
  )::date as day
)
select
  b.id as business_id,
  d.day,
  (d.day > current_date) as is_future,
  (select count(*) from appointments a
    where a.business_id = b.id
      and a.status not in ('cancelled','no_show')
      and (a.starts_at at time zone b.timezone)::date = d.day)          as jobs,
  (select count(*) from appointments a
    where a.business_id = b.id and a.status = 'completed'
      and (a.completed_at at time zone b.timezone)::date = d.day)       as completed,
  (select coalesce(sum(p.amount), 0) from payments p
    where p.business_id = b.id
      and (p.paid_at at time zone b.timezone)::date = d.day)            as collected,
  (select count(*) from ai_decisions x
    where x.business_id = b.id
      and (x.created_at at time zone b.timezone)::date = d.day)         as decisions,
  (select count(*) from conversations c
    where c.business_id = b.id
      and (c.started_at at time zone b.timezone)::date = d.day)         as calls
from businesses b cross join days d
order by d.day;

grant select on v_daily_activity to anon;
