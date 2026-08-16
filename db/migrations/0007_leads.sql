-- 0007_leads.sql
-- Leads and their qualification history.
--
-- Scores live in their own table rather than as columns on leads: a lead can be
-- rescored as a conversation develops, and the Leads detail view shows how the
-- assessment moved rather than only where it landed.

create table leads (
  id              uuid        primary key default gen_random_uuid(),
  business_id     uuid        not null references businesses(id) on delete cascade,
  customer_id     uuid        references customers(id) on delete set null,
  conversation_id uuid        references conversations(id) on delete set null,
  service_id      uuid        references services(id) on delete set null,

  status          text        not null default 'new'
                  check (status in ('new','qualified','contacted','converted','lost')),
  source          text        not null default 'voice'
                  check (source in ('voice','telegram','web','manual')),
  urgency         text        check (urgency in ('low','medium','high')),
  requested_service text,
  location        text,
  preferred_timing  text,
  notes           text,
  next_action     text,
  last_contact_at timestamptz,
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now()
);

create table lead_scores (
  id             uuid        primary key default gen_random_uuid(),
  business_id    uuid        not null references businesses(id) on delete cascade,
  lead_id        uuid        not null references leads(id) on delete cascade,

  score          integer     not null check (score between 0 and 100),
  classification text        not null check (classification in ('HOT','WARM','COLD')),
  confidence     real        not null check (confidence between 0 and 1),

  -- Per-dimension contributions: intent, urgency, service_match,
  -- customer_value, engagement. Kept as jsonb so weights stay configurable
  -- without a migration.
  factors        jsonb       not null default '{}'::jsonb,
  -- Short user-safe statements, never chain-of-thought.
  reasoning      text[]      not null default '{}',

  created_at     timestamptz not null default now()
);

create index leads_business_idx    on leads (business_id, status, created_at desc);
create index leads_customer_idx    on leads (business_id, customer_id);
create index lead_scores_lead_idx  on lead_scores (business_id, lead_id, created_at desc);

create trigger leads_updated_at before update on leads for each row execute function set_updated_at();

alter table leads       enable row level security;
alter table lead_scores enable row level security;

create policy tenant_read on leads
  for select to anon using (business_id = '00000000-0000-0000-0000-000000000001'::uuid);
create policy tenant_read on lead_scores
  for select to anon using (business_id = '00000000-0000-0000-0000-000000000001'::uuid);
