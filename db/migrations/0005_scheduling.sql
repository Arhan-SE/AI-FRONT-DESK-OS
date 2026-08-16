-- 0005_scheduling.sql
-- The scheduling core. This is the most important migration in the project.
--
-- Double-booking is not prevented by application code here. It is made
-- unrepresentable by the database, so the race condition has no window to occur
-- in — including between the API process, the voice agent, and the automation
-- worker, which all write concurrently.

create table appointments (
  id              uuid        primary key default gen_random_uuid(),
  business_id     uuid        not null references businesses(id) on delete cascade,
  customer_id     uuid        not null references customers(id)  on delete cascade,
  service_id      uuid        not null references services(id),
  technician_id   uuid        not null references technicians(id),

  starts_at       timestamptz not null,
  ends_at         timestamptz not null,

  -- Copied from the service at booking time. Repricing or retiming a service
  -- later must not silently move appointments already on the calendar.
  buffer_minutes  integer     not null default 0 check (buffer_minutes >= 0),

  -- ends_at plus the buffer, written by the booking service.
  --
  -- This is a stored column rather than part of the generated expression below
  -- because `timestamptz + interval` is STABLE, not IMMUTABLE — interval
  -- arithmetic depends on the session TimeZone — and Postgres rejects
  -- non-immutable expressions in generated columns and index predicates.
  blocked_until   timestamptz not null,

  status          text        not null default 'booked'
                  check (status in ('booked','in_progress','completed','cancelled','no_show')),
  source          text        not null default 'voice'
                  check (source in ('voice','manual','web','telegram','automation')),
  notes           text,

  -- A retried booking returns the existing appointment instead of creating a
  -- second one. Enforced by the partial unique index below.
  idempotency_key text,

  completed_at    timestamptz,
  cancelled_at    timestamptz,
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now(),

  constraint appointments_ordered   check (ends_at > starts_at),
  constraint appointments_buffered  check (blocked_until >= ends_at),

  -- The technician's calendar is blocked for the service plus its buffer, so
  -- back-to-back bookings still leave travel time.
  blocked_range   tstzrange generated always as (
                    tstzrange(starts_at, blocked_until, '[)')
                  ) stored,

  -- The single most valuable line in the schema.
  constraint appointments_no_technician_overlap exclude using gist (
    technician_id with =,
    blocked_range with &&
  ) where (status in ('booked','in_progress'))
);

create unique index appointments_idempotency_idx
  on appointments (business_id, idempotency_key)
  where idempotency_key is not null;

-- Short-lived reservations placed the moment slots are offered to a customer.
--
-- Without these, a slot spoken aloud during a voice call can be taken by
-- another conversation while the customer is still deciding, and the agent
-- books something that no longer exists. Holds close that window.
create table slot_holds (
  id              uuid        primary key default gen_random_uuid(),
  business_id     uuid        not null references businesses(id) on delete cascade,
  technician_id   uuid        not null references technicians(id) on delete cascade,
  service_id      uuid        not null references services(id)    on delete cascade,
  customer_id     uuid        references customers(id) on delete set null,
  conversation_id uuid,

  starts_at       timestamptz not null,
  ends_at         timestamptz not null,
  buffer_minutes  integer     not null default 0 check (buffer_minutes >= 0),
  blocked_until   timestamptz not null,   -- see the note on appointments.blocked_until

  expires_at      timestamptz not null,
  consumed_at     timestamptz,
  created_at      timestamptz not null default now(),

  constraint slot_holds_ordered  check (ends_at > starts_at),
  constraint slot_holds_buffered check (blocked_until >= ends_at),

  hold_range      tstzrange generated always as (
                    tstzrange(starts_at, blocked_until, '[)')
                  ) stored,

  -- Two conversations cannot hold the same window. The predicate cannot test
  -- expires_at, because an index predicate must be immutable and now() is not;
  -- the automation worker deletes expired holds instead. An unswept hold blocks
  -- for a few extra seconds, which errs toward refusing a booking rather than
  -- toward double-booking.
  constraint slot_holds_no_overlap exclude using gist (
    technician_id with =,
    hold_range with &&
  ) where (consumed_at is null)
);

create index appointments_calendar_idx on appointments (business_id, starts_at)
  where status in ('booked','in_progress');
create index appointments_customer_idx on appointments (business_id, customer_id, starts_at desc);
create index appointments_completed_idx on appointments (business_id, completed_at)
  where status = 'completed';
create index slot_holds_expiry_idx      on slot_holds (expires_at) where consumed_at is null;

create trigger appointments_updated_at before update on appointments for each row execute function set_updated_at();

alter table appointments enable row level security;
alter table slot_holds   enable row level security;

create policy tenant_read on appointments
  for select to anon using (business_id = '00000000-0000-0000-0000-000000000001'::uuid);
create policy tenant_read on slot_holds
  for select to anon using (business_id = '00000000-0000-0000-0000-000000000001'::uuid);
