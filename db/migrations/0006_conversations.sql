-- 0006_conversations.sql
-- Conversations, their transcripts, and the observable record of what the AI
-- decided.
--
-- ai_decisions is the backing table for the AI Activity page. The frontend
-- subscribes to it over Supabase Realtime, which is why a decision appears on
-- screen while the customer is still talking.

create table conversations (
  id             uuid        primary key default gen_random_uuid(),
  business_id    uuid        not null references businesses(id) on delete cascade,
  -- Null until the agent identifies who it is speaking to.
  customer_id    uuid        references customers(id) on delete set null,
  channel        text        not null default 'voice'
                 check (channel in ('voice','telegram','web')),
  status         text        not null default 'active'
                 check (status in ('active','ended','escalated')),
  livekit_room   text,
  current_intent text,
  summary        text,
  requires_human boolean     not null default false,
  started_at     timestamptz not null default now(),
  ended_at       timestamptz,
  created_at     timestamptz not null default now(),
  updated_at     timestamptz not null default now()
);

create table messages (
  id              uuid        primary key default gen_random_uuid(),
  business_id     uuid        not null references businesses(id) on delete cascade,
  conversation_id uuid        not null references conversations(id) on delete cascade,
  role            text        not null check (role in ('customer','agent','system','human')),
  content         text        not null,
  created_at      timestamptz not null default now()
);

-- One row per observable AI action. Deliberately not a log of reasoning:
-- summary is a short user-safe statement of what was decided, never
-- chain-of-thought.
create table ai_decisions (
  id              uuid        primary key default gen_random_uuid(),
  business_id     uuid        not null references businesses(id) on delete cascade,
  conversation_id uuid        references conversations(id) on delete cascade,
  customer_id     uuid        references customers(id) on delete set null,

  event_type      text        not null,   -- customer_identified | intent_detected | memory_retrieved
                                          -- lead_scored | availability_checked | appointment_booked
                                          -- message_sent | escalated | safety_tripwire | query_answered
  status          text        not null default 'success'
                  check (status in ('success','failure','blocked','pending')),
  summary         text        not null,
  detail          jsonb       not null default '{}'::jsonb,
  confidence      real        check (confidence between 0 and 1),
  tool_name       text,
  duration_ms     integer,
  created_at      timestamptz not null default now()
);

create index conversations_business_idx on conversations (business_id, started_at desc);
create index messages_conversation_idx  on messages (business_id, conversation_id, created_at);
create index ai_decisions_feed_idx       on ai_decisions (business_id, created_at desc);
create index ai_decisions_conversation_idx on ai_decisions (business_id, conversation_id, created_at);

create trigger conversations_updated_at before update on conversations for each row execute function set_updated_at();

alter table conversations enable row level security;
alter table messages      enable row level security;
alter table ai_decisions  enable row level security;

create policy tenant_read on conversations
  for select to anon using (business_id = '00000000-0000-0000-0000-000000000001'::uuid);
create policy tenant_read on messages
  for select to anon using (business_id = '00000000-0000-0000-0000-000000000001'::uuid);
create policy tenant_read on ai_decisions
  for select to anon using (business_id = '00000000-0000-0000-0000-000000000001'::uuid);

-- The live feed. Realtime still enforces the policies above.
alter publication supabase_realtime add table ai_decisions;
alter publication supabase_realtime add table conversations;
alter publication supabase_realtime add table messages;
