-- 0002_tenancy.sql
-- The business, its opening hours, and its closures.
--
-- RLS note: every table in this schema carries business_id, including tables
-- where it is technically derivable through a parent. That denormalisation is
-- deliberate: it makes every read policy the same single-column comparison,
-- which is both fast and impossible to get subtly wrong.

create table businesses (
  id          uuid primary key default gen_random_uuid(),
  name        text        not null,
  trade       text        not null,               -- hvac | plumbing | electrical | cleaning
  timezone    text        not null default 'Asia/Kolkata',
  phone       text,
  email       text,
  address     text,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);

-- Weekly recurring opening hours. weekday: 0 = Sunday .. 6 = Saturday,
-- matching PostgreSQL's extract(dow from ...).
create table business_hours (
  id          uuid primary key default gen_random_uuid(),
  business_id uuid        not null references businesses(id) on delete cascade,
  weekday     smallint    not null check (weekday between 0 and 6),
  opens_at    time        not null,
  closes_at   time        not null,
  is_closed   boolean     not null default false,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now(),
  constraint business_hours_unique_day unique (business_id, weekday),
  constraint business_hours_ordered    check (is_closed or closes_at > opens_at)
);

-- One-off closures (public holidays, staff events).
create table business_holidays (
  id          uuid primary key default gen_random_uuid(),
  business_id uuid        not null references businesses(id) on delete cascade,
  holiday_on  date        not null,
  name        text        not null,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now(),
  constraint business_holidays_unique unique (business_id, holiday_on)
);

create index business_hours_business_idx    on business_hours (business_id, weekday);
create index business_holidays_business_idx on business_holidays (business_id, holiday_on);

create trigger businesses_updated_at        before update on businesses        for each row execute function set_updated_at();
create trigger business_hours_updated_at    before update on business_hours    for each row execute function set_updated_at();
create trigger business_holidays_updated_at before update on business_holidays for each row execute function set_updated_at();

-- --------------------------------------------------------------------------
-- Row Level Security
--
-- The anon key ships inside the JavaScript bundle, so these policies are the
-- only thing between a browser and the data. anon gets SELECT and nothing else;
-- every write goes through FastAPI using the service-role key, which bypasses
-- RLS by design.
--
-- Scoping is a constant today because there is no login yet. Adding auth is a
-- one-line change per policy: swap the literal for
--   (auth.jwt() ->> 'business_id')::uuid
-- --------------------------------------------------------------------------

alter table businesses        enable row level security;
alter table business_hours    enable row level security;
alter table business_holidays enable row level security;

create policy tenant_read on businesses
  for select to anon
  using (id = '00000000-0000-0000-0000-000000000001'::uuid);

create policy tenant_read on business_hours
  for select to anon
  using (business_id = '00000000-0000-0000-0000-000000000001'::uuid);

create policy tenant_read on business_holidays
  for select to anon
  using (business_id = '00000000-0000-0000-0000-000000000001'::uuid);
