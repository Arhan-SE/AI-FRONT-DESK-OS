-- 0012_job_pipeline.sql
-- The owner-driven job pipeline.
--
-- The owner never sends a message. They report what happened in the real world
-- — confirmed, started, finished, invoiced, paid — and each transition is what
-- decides whether an automation becomes due. This makes every outbound message
-- causally traceable to a human action rather than to a clock nobody can see.
--
--   SCHEDULED → CONFIRMED → IN PROGRESS → COMPLETED → INVOICE SENT → PAID
--                                                                  ↘ OVERDUE

alter table appointments drop constraint appointments_status_check;

alter table appointments add constraint appointments_status_check
  check (status in ('booked','confirmed','in_progress','completed','cancelled','no_show'));

-- The exclusion constraint must cover every status that occupies a technician's
-- time. Omitting 'confirmed' would let a second booking overlap a job the owner
-- has just confirmed — the exact moment it is most certainly happening.
alter table appointments drop constraint appointments_no_technician_overlap;

alter table appointments add constraint appointments_no_technician_overlap
  exclude using gist (
    technician_id with =,
    blocked_range with &&
  ) where (status in ('booked','confirmed','in_progress'));

-- Transition timestamps. Kept as columns rather than a separate event table:
-- the pipeline is linear and short, and this keeps the Jobs query a single row
-- read instead of an aggregate over history.
alter table appointments add column if not exists confirmed_at timestamptz;
alter table appointments add column if not exists started_at   timestamptz;

drop index if exists appointments_calendar_idx;
create index appointments_calendar_idx on appointments (business_id, starts_at)
  where status in ('booked','confirmed','in_progress');

-- One row per job, joining everything the pipeline board needs.
create or replace view v_jobs
with (security_invoker = on) as
select
  a.id,
  a.business_id,
  a.starts_at,
  a.ends_at,
  a.status                       as appointment_status,
  a.source,
  a.notes,
  a.confirmed_at,
  a.started_at,
  a.completed_at,
  a.cancelled_at,
  c.id                           as customer_id,
  c.full_name                    as customer_name,
  c.phone                        as customer_phone,
  c.telegram_chat_id is not null as customer_reachable,
  s.name                         as service_name,
  s.base_price                   as service_price,
  t.full_name                    as technician_name,
  i.id                           as invoice_id,
  i.invoice_number,
  i.amount                       as invoice_amount,
  i.status                       as invoice_status,
  i.due_on,

  -- The single label the board renders. Invoice state supersedes appointment
  -- state once money is involved, because that is what the owner is chasing.
  case
    when a.status = 'cancelled'        then 'cancelled'
    when a.status = 'no_show'          then 'no_show'
    when i.status = 'paid'             then 'paid'
    when i.status = 'overdue'          then 'overdue'
    when i.status = 'sent'             then 'invoice_sent'
    when a.status = 'completed'        then 'completed'
    when a.status = 'in_progress'      then 'in_progress'
    when a.status = 'confirmed'        then 'confirmed'
    else 'scheduled'
  end as stage

from appointments a
join customers   c on c.id = a.customer_id
join services    s on s.id = a.service_id
join technicians t on t.id = a.technician_id
left join invoices i on i.appointment_id = a.id;

grant select on v_jobs to anon;
