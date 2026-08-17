-- 0014_usage.sql
-- What the AI actually cost.
--
-- Cost is computed and stored at write time rather than derived on read. Rates
-- change; a report of what last month cost must not silently change with them.

create table usage_events (
  id                  uuid        primary key default gen_random_uuid(),
  business_id         uuid        not null references businesses(id) on delete cascade,
  conversation_id     uuid        references conversations(id) on delete set null,

  source              text        not null check (source in ('realtime','text','embedding')),
  model               text        not null,
  purpose             text,       -- voice | personalisation | summary | …

  input_text_tokens   integer     not null default 0,
  input_audio_tokens  integer     not null default 0,
  input_cached_tokens integer     not null default 0,
  output_text_tokens  integer     not null default 0,
  output_audio_tokens integer     not null default 0,

  -- Wall-clock seconds of conversation, for realtime sessions only.
  duration_seconds    numeric(10,2) not null default 0,

  -- USD, at the rates configured when the event was recorded.
  cost_usd            numeric(12,6) not null default 0,

  created_at          timestamptz not null default now()
);

create index usage_events_recent_idx on usage_events (business_id, created_at desc);
create index usage_events_conv_idx   on usage_events (business_id, conversation_id);

alter table usage_events enable row level security;

create policy tenant_read on usage_events
  for select to anon using (business_id = '00000000-0000-0000-0000-000000000001'::uuid);

alter publication supabase_realtime add table usage_events;


-- Roll-up for the AI Activity page. One row.
create or replace view v_usage_summary
with (security_invoker = on) as
select
  b.id as business_id,

  (select count(*) from conversations c
    where c.business_id = b.id and c.channel = 'voice')              as total_calls,

  (select coalesce(sum(u.duration_seconds), 0) / 60.0 from usage_events u
    where u.business_id = b.id and u.source = 'realtime')            as voice_minutes,

  (select coalesce(sum(
      u.input_text_tokens + u.input_audio_tokens
    + u.output_text_tokens + u.output_audio_tokens), 0)
     from usage_events u where u.business_id = b.id)                 as total_tokens,

  (select coalesce(sum(u.input_audio_tokens + u.output_audio_tokens), 0)
     from usage_events u where u.business_id = b.id)                 as audio_tokens,

  (select coalesce(sum(u.cost_usd), 0) from usage_events u
    where u.business_id = b.id)                                      as total_cost_usd,

  (select coalesce(sum(u.cost_usd), 0) from usage_events u
    where u.business_id = b.id and u.source = 'realtime')            as voice_cost_usd,

  (select coalesce(sum(u.cost_usd), 0) from usage_events u
    where u.business_id = b.id and u.source <> 'realtime')           as text_cost_usd,

  (select count(*) from ai_decisions d where d.business_id = b.id)   as total_decisions,

  (select count(*) from ai_decisions d
    where d.business_id = b.id and d.status = 'blocked')             as blocked_decisions,

  (select count(*) from ai_decisions d
    where d.business_id = b.id and d.status = 'failure')             as failed_decisions

from businesses b;


-- Daily series for the Overview charts. Zero-filled so a quiet day is a gap in
-- the line at zero rather than a missing point the chart interpolates over.
create or replace view v_daily_activity
with (security_invoker = on) as
with days as (
  select generate_series(
    (current_date - interval '13 days')::date, current_date, interval '1 day'
  )::date as day
)
select
  b.id as business_id,
  d.day,
  (select count(*) from appointments a
    where a.business_id = b.id
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

grant select on v_usage_summary, v_daily_activity to anon;
