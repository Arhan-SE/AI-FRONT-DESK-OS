-- 0008_revenue.sql
-- Invoices, payments, and reviews.
--
-- No payment processing is involved. Invoices are records the business keeps;
-- what the system automates is chasing them.

create table invoices (
  id             uuid          primary key default gen_random_uuid(),
  business_id    uuid          not null references businesses(id) on delete cascade,
  customer_id    uuid          not null references customers(id) on delete cascade,
  appointment_id uuid          references appointments(id) on delete set null,

  invoice_number text          not null,
  amount         numeric(10,2) not null check (amount >= 0),
  currency       text          not null default 'INR',
  status         text          not null default 'sent'
                 check (status in ('draft','sent','paid','overdue','void')),
  issued_on      date          not null default current_date,
  due_on         date          not null,
  paid_at        timestamptz,
  created_at     timestamptz   not null default now(),
  updated_at     timestamptz   not null default now(),

  constraint invoices_number_unique unique (business_id, invoice_number),
  constraint invoices_due_after_issue check (due_on >= issued_on)
);

create table payments (
  id          uuid          primary key default gen_random_uuid(),
  business_id uuid          not null references businesses(id) on delete cascade,
  invoice_id  uuid          not null references invoices(id) on delete cascade,
  amount      numeric(10,2) not null check (amount > 0),
  method      text          not null default 'cash'
              check (method in ('cash','card','upi','bank_transfer','other')),
  reference   text,
  paid_at     timestamptz   not null default now(),
  created_at  timestamptz   not null default now()
);

create table reviews (
  id             uuid        primary key default gen_random_uuid(),
  business_id    uuid        not null references businesses(id) on delete cascade,
  customer_id    uuid        not null references customers(id) on delete cascade,
  appointment_id uuid        references appointments(id) on delete set null,

  rating         smallint    check (rating between 1 and 5),
  comment        text,
  source         text        not null default 'telegram'
                 check (source in ('telegram','voice','web','manual')),
  -- requested_at is set when the review request goes out; submitted_at when the
  -- customer actually replies. The gap between them is the response rate shown
  -- on the Reviews page.
  requested_at   timestamptz,
  submitted_at   timestamptz,
  created_at     timestamptz not null default now(),
  updated_at     timestamptz not null default now(),

  constraint reviews_one_per_appointment unique (appointment_id)
);

create index invoices_status_idx   on invoices (business_id, status, due_on);
create index invoices_customer_idx on invoices (business_id, customer_id, issued_on desc);
create index invoices_overdue_idx  on invoices (business_id, due_on) where status in ('sent','overdue');
create index payments_invoice_idx  on payments (business_id, invoice_id);
create index reviews_business_idx  on reviews (business_id, submitted_at desc);

create trigger invoices_updated_at before update on invoices for each row execute function set_updated_at();
create trigger reviews_updated_at  before update on reviews  for each row execute function set_updated_at();

alter table invoices enable row level security;
alter table payments enable row level security;
alter table reviews  enable row level security;

create policy tenant_read on invoices
  for select to anon using (business_id = '00000000-0000-0000-0000-000000000001'::uuid);
create policy tenant_read on payments
  for select to anon using (business_id = '00000000-0000-0000-0000-000000000001'::uuid);
create policy tenant_read on reviews
  for select to anon using (business_id = '00000000-0000-0000-0000-000000000001'::uuid);
