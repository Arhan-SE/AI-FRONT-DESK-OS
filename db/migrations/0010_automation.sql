-- 0010_automation.sql
-- The job queue that drives reminders, follow-ups, payment chasing, review
-- requests and reactivation, plus human tasks and the audit trail.

create table automation_jobs (
  id            uuid        primary key default gen_random_uuid(),
  business_id   uuid        not null references businesses(id) on delete cascade,

  job_type      text        not null,   -- appointment_reminder | post_service_followup
                                        -- payment_reminder | review_request
                                        -- lead_reactivation | seasonal_campaign
                                        -- sweep_slot_holds
  scheduled_for timestamptz not null,
  status        text        not null default 'pending'
                check (status in ('pending','claimed','succeeded','failed','cancelled')),
  attempts      integer     not null default 0,
  max_attempts  integer     not null default 3,
  payload       jsonb       not null default '{}'::jsonb,
  last_error    text,

  -- Stops the scheduler enqueueing the same work twice, e.g. two reminder jobs
  -- for one appointment.
  dedupe_key    text,

  claimed_at    timestamptz,
  completed_at  timestamptz,
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now()
);

-- Failed jobs are excluded so a permanently failed job can be re-enqueued after
-- the underlying problem is fixed.
create unique index automation_jobs_dedupe_idx
  on automation_jobs (business_id, job_type, dedupe_key)
  where dedupe_key is not null and status <> 'failed';

-- Supports the worker's claim query:
--   select id from automation_jobs
--    where status = 'pending' and scheduled_for <= now()
--    order by scheduled_for
--      for update skip locked limit n
-- SKIP LOCKED is what lets several workers share the queue without ever handing
-- the same job to two of them.
create index automation_jobs_claim_idx
  on automation_jobs (status, scheduled_for)
  where status = 'pending';

create index automation_jobs_business_idx on automation_jobs (business_id, created_at desc);

-- Work that needs a person: escalations, low-confidence handoffs, tripwire hits.
create table tasks (
  id              uuid        primary key default gen_random_uuid(),
  business_id     uuid        not null references businesses(id) on delete cascade,
  customer_id     uuid        references customers(id) on delete set null,
  conversation_id uuid        references conversations(id) on delete set null,
  lead_id         uuid        references leads(id) on delete set null,

  title           text        not null,
  description     text,
  task_type       text        not null default 'follow_up'
                  check (task_type in ('follow_up','escalation','callback','approval','safety')),
  priority        text        not null default 'normal'
                  check (priority in ('low','normal','high','urgent')),
  status          text        not null default 'open'
                  check (status in ('open','in_progress','done','dismissed')),
  due_at          timestamptz,
  completed_at    timestamptz,
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now()
);

create table notifications (
  id          uuid        primary key default gen_random_uuid(),
  business_id uuid        not null references businesses(id) on delete cascade,
  title       text        not null,
  body        text,
  severity    text        not null default 'info'
              check (severity in ('info','warning','critical')),
  read_at     timestamptz,
  created_at  timestamptz not null default now()
);

create table audit_logs (
  id          uuid        primary key default gen_random_uuid(),
  business_id uuid        not null references businesses(id) on delete cascade,
  actor       text        not null default 'system',  -- system | agent | automation | human
  action      text        not null,
  entity_type text,
  entity_id   uuid,
  detail      jsonb       not null default '{}'::jsonb,
  created_at  timestamptz not null default now()
);

create index tasks_open_idx        on tasks (business_id, status, priority, created_at desc);
create index notifications_idx     on notifications (business_id, created_at desc) where read_at is null;
create index audit_logs_entity_idx on audit_logs (business_id, entity_type, entity_id, created_at desc);

create trigger automation_jobs_updated_at before update on automation_jobs for each row execute function set_updated_at();
create trigger tasks_updated_at            before update on tasks            for each row execute function set_updated_at();

alter table automation_jobs enable row level security;
alter table tasks           enable row level security;
alter table notifications   enable row level security;
alter table audit_logs      enable row level security;

create policy tenant_read on automation_jobs
  for select to anon using (business_id = '00000000-0000-0000-0000-000000000001'::uuid);
create policy tenant_read on tasks
  for select to anon using (business_id = '00000000-0000-0000-0000-000000000001'::uuid);
create policy tenant_read on notifications
  for select to anon using (business_id = '00000000-0000-0000-0000-000000000001'::uuid);
create policy tenant_read on audit_logs
  for select to anon using (business_id = '00000000-0000-0000-0000-000000000001'::uuid);

alter publication supabase_realtime add table automation_jobs;
alter publication supabase_realtime add table tasks;
