-- 0003_customers.sql
-- Customers, their preferences, and the two memory layers.

create table customers (
  id                 uuid        primary key default gen_random_uuid(),
  business_id        uuid        not null references businesses(id) on delete cascade,
  full_name          text        not null,
  phone              text,
  email              text,
  address            text,
  -- Messaging identity. Telegram cannot address a phone number: a customer is
  -- reachable only after they have pressed Start on the bot, which is what
  -- populates this column. No chat id means the Communication Guard blocks.
  telegram_chat_id   bigint,
  telegram_opted_in  boolean     not null default false,
  do_not_contact     boolean     not null default false,
  status             text        not null default 'active'
                     check (status in ('active','dormant','archived')),
  first_seen_at      timestamptz not null default now(),
  last_service_at    timestamptz,
  last_contacted_at  timestamptz,
  lifetime_value     numeric(12,2) not null default 0,
  created_at         timestamptz not null default now(),
  updated_at         timestamptz not null default now(),
  constraint customers_telegram_unique unique (business_id, telegram_chat_id)
);

create table customer_preferences (
  id                     uuid        primary key default gen_random_uuid(),
  business_id            uuid        not null references businesses(id) on delete cascade,
  customer_id            uuid        not null references customers(id) on delete cascade,
  preferred_time_window  text        check (preferred_time_window in ('morning','afternoon','evening')),
  preferred_technician_id uuid,
  language               text        not null default 'en',
  notes                  text,
  created_at             timestamptz not null default now(),
  updated_at             timestamptz not null default now(),
  constraint customer_preferences_unique unique (customer_id)
);

-- Semantic memory. Durable facts worth recalling in a later conversation,
-- not a transcript of every utterance.
create table customer_memory (
  id           uuid          primary key default gen_random_uuid(),
  business_id  uuid          not null references businesses(id) on delete cascade,
  customer_id  uuid          not null references customers(id) on delete cascade,
  summary      text          not null,
  importance   real          not null default 0.5 check (importance between 0 and 1),
  source       text          not null default 'conversation'
               check (source in ('conversation','service','manual','system')),
  embedding    vector(1536),
  created_at   timestamptz   not null default now(),
  updated_at   timestamptz   not null default now()
);

create index customers_business_idx        on customers (business_id, status);
create index customers_name_idx            on customers (business_id, lower(full_name));
create index customers_phone_idx           on customers (business_id, phone);
create index customer_memory_customer_idx  on customer_memory (business_id, customer_id, created_at desc);

-- HNSW rather than IVFFlat: it needs no training pass and behaves well on the
-- small-to-medium row counts this system will hold.
create index customer_memory_embedding_idx on customer_memory
  using hnsw (embedding vector_cosine_ops);

create trigger customers_updated_at            before update on customers            for each row execute function set_updated_at();
create trigger customer_preferences_updated_at before update on customer_preferences for each row execute function set_updated_at();
create trigger customer_memory_updated_at      before update on customer_memory      for each row execute function set_updated_at();

alter table customers            enable row level security;
alter table customer_preferences enable row level security;
alter table customer_memory      enable row level security;

create policy tenant_read on customers
  for select to anon using (business_id = '00000000-0000-0000-0000-000000000001'::uuid);
create policy tenant_read on customer_preferences
  for select to anon using (business_id = '00000000-0000-0000-0000-000000000001'::uuid);
create policy tenant_read on customer_memory
  for select to anon using (business_id = '00000000-0000-0000-0000-000000000001'::uuid);
