-- 0004_catalog.sql
-- What the business sells and who can deliver it. These four tables are the
-- inputs to availability: without them the scheduling engine has nothing to
-- compute from.

create table services (
  id               uuid          primary key default gen_random_uuid(),
  business_id      uuid          not null references businesses(id) on delete cascade,
  name             text          not null,
  description      text,
  duration_minutes integer       not null check (duration_minutes > 0),
  -- Travel and write-up time. Reserved on the technician's calendar but never
  -- spoken to the customer as part of the appointment length.
  buffer_minutes   integer       not null default 15 check (buffer_minutes >= 0),
  base_price       numeric(10,2) not null default 0,
  required_skill   text,
  is_active        boolean       not null default true,
  created_at       timestamptz   not null default now(),
  updated_at       timestamptz   not null default now()
);

create table technicians (
  id          uuid        primary key default gen_random_uuid(),
  business_id uuid        not null references businesses(id) on delete cascade,
  full_name   text        not null,
  phone       text,
  email       text,
  skills      text[]      not null default '{}',
  is_active   boolean     not null default true,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);

-- Weekly working windows. A technician with no row for a weekday does not work
-- that day; availability is the intersection of this and business_hours.
create table technician_schedules (
  id             uuid        primary key default gen_random_uuid(),
  business_id    uuid        not null references businesses(id) on delete cascade,
  technician_id  uuid        not null references technicians(id) on delete cascade,
  weekday        smallint    not null check (weekday between 0 and 6),
  starts_at      time        not null,
  ends_at        time        not null,
  created_at     timestamptz not null default now(),
  updated_at     timestamptz not null default now(),
  constraint technician_schedules_unique  unique (technician_id, weekday),
  constraint technician_schedules_ordered check (ends_at > starts_at)
);

create table technician_time_off (
  id            uuid        primary key default gen_random_uuid(),
  business_id   uuid        not null references businesses(id) on delete cascade,
  technician_id uuid        not null references technicians(id) on delete cascade,
  starts_at     timestamptz not null,
  ends_at       timestamptz not null,
  reason        text,
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now(),
  constraint technician_time_off_ordered check (ends_at > starts_at)
);

alter table customer_preferences
  add constraint customer_preferences_technician_fk
  foreign key (preferred_technician_id) references technicians(id) on delete set null;

create index services_business_idx             on services (business_id, is_active);
create index technicians_business_idx          on technicians (business_id, is_active);
create index technician_schedules_lookup_idx   on technician_schedules (business_id, weekday);
create index technician_time_off_lookup_idx    on technician_time_off (business_id, technician_id, starts_at, ends_at);

create trigger services_updated_at             before update on services             for each row execute function set_updated_at();
create trigger technicians_updated_at          before update on technicians          for each row execute function set_updated_at();
create trigger technician_schedules_updated_at before update on technician_schedules for each row execute function set_updated_at();
create trigger technician_time_off_updated_at  before update on technician_time_off  for each row execute function set_updated_at();

alter table services             enable row level security;
alter table technicians          enable row level security;
alter table technician_schedules enable row level security;
alter table technician_time_off  enable row level security;

create policy tenant_read on services
  for select to anon using (business_id = '00000000-0000-0000-0000-000000000001'::uuid);
create policy tenant_read on technicians
  for select to anon using (business_id = '00000000-0000-0000-0000-000000000001'::uuid);
create policy tenant_read on technician_schedules
  for select to anon using (business_id = '00000000-0000-0000-0000-000000000001'::uuid);
create policy tenant_read on technician_time_off
  for select to anon using (business_id = '00000000-0000-0000-0000-000000000001'::uuid);
