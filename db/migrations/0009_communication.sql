-- 0009_communication.sql
-- The messaging layer: templates, campaigns, and the log the Communication
-- Guard reasons over.
--
-- message_log is not an audit afterthought. It is the Guard's working memory:
-- frequency limits, recent-contact checks and duplicate prevention are all
-- queries against this table, and its partial unique index is what makes
-- "send the reminder exactly once" true under retries.

create table message_templates (
  id           uuid        primary key default gen_random_uuid(),
  business_id  uuid        not null references businesses(id) on delete cascade,
  key          text        not null,
  message_type text        not null,
  category     text        not null check (category in ('transactional','marketing')),
  body         text        not null,   -- {{placeholder}} substitution
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now(),
  constraint message_templates_key_unique unique (business_id, key)
);

create table campaigns (
  id            uuid        primary key default gen_random_uuid(),
  business_id   uuid        not null references businesses(id) on delete cascade,
  name          text        not null,
  campaign_type text        not null
                check (campaign_type in ('reactivation','seasonal','review_request','payment_reminder')),
  status        text        not null default 'draft'
                check (status in ('draft','scheduled','running','completed','failed')),
  template_key  text,
  scheduled_for timestamptz,
  started_at    timestamptz,
  completed_at  timestamptz,
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now()
);

create table campaign_recipients (
  id          uuid        primary key default gen_random_uuid(),
  business_id uuid        not null references businesses(id) on delete cascade,
  campaign_id uuid        not null references campaigns(id) on delete cascade,
  customer_id uuid        not null references customers(id) on delete cascade,
  status      text        not null default 'pending'
              check (status in ('pending','sent','blocked','failed','replied','opted_out')),
  block_reason text,
  sent_at     timestamptz,
  replied_at  timestamptz,
  created_at  timestamptz not null default now(),
  constraint campaign_recipients_unique unique (campaign_id, customer_id)
);

create table message_log (
  id                  uuid        primary key default gen_random_uuid(),
  business_id         uuid        not null references businesses(id) on delete cascade,
  customer_id         uuid        references customers(id) on delete set null,
  campaign_id         uuid        references campaigns(id) on delete set null,

  message_type        text        not null,   -- appointment_reminder | post_service_followup
                                              -- payment_reminder | review_request | reactivation
                                              -- appointment_confirmation | seasonal
  category            text        not null check (category in ('transactional','marketing')),
  channel             text        not null default 'telegram',
  body                text,

  status              text        not null check (status in ('sent','blocked','failed')),
  block_reason        text,       -- populated when the Guard refuses
  telegram_message_id bigint,
  error               text,

  -- Identifies the thing being messaged about, e.g. the appointment id for a
  -- reminder. Combined with message_type this is what makes a retry a no-op.
  dedupe_key          text,
  created_at          timestamptz not null default now()
);

-- At most one *successful* send per (type, subject). Blocked and failed rows are
-- deliberately excluded so a message the Guard refused today can still be sent
-- tomorrow once the reason clears.
create unique index message_log_dedupe_idx
  on message_log (business_id, message_type, dedupe_key)
  where dedupe_key is not null and status = 'sent';

create index message_log_customer_idx on message_log (business_id, customer_id, created_at desc);
create index message_log_recent_idx   on message_log (business_id, created_at desc);
create index campaigns_business_idx   on campaigns (business_id, status, scheduled_for);
create index campaign_recipients_idx  on campaign_recipients (business_id, campaign_id, status);

create trigger message_templates_updated_at before update on message_templates for each row execute function set_updated_at();
create trigger campaigns_updated_at         before update on campaigns         for each row execute function set_updated_at();

alter table message_templates    enable row level security;
alter table campaigns            enable row level security;
alter table campaign_recipients  enable row level security;
alter table message_log          enable row level security;

create policy tenant_read on message_templates
  for select to anon using (business_id = '00000000-0000-0000-0000-000000000001'::uuid);
create policy tenant_read on campaigns
  for select to anon using (business_id = '00000000-0000-0000-0000-000000000001'::uuid);
create policy tenant_read on campaign_recipients
  for select to anon using (business_id = '00000000-0000-0000-0000-000000000001'::uuid);
create policy tenant_read on message_log
  for select to anon using (business_id = '00000000-0000-0000-0000-000000000001'::uuid);
