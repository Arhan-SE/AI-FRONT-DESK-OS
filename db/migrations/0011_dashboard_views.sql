-- 0011_dashboard_views.sql
-- Read models for the Overview page.
--
-- security_invoker = on is essential: without it a view runs as its owner and
-- silently bypasses Row Level Security, which would hand the browser every
-- tenant's aggregates through a side door. With it, the view is subject to the
-- caller's policies exactly like a direct table read.

-- Latest score per lead. Scores are append-only, so "current" means most recent.
create or replace view v_lead_current_score
with (security_invoker = on) as
select distinct on (ls.lead_id)
  ls.lead_id,
  ls.business_id,
  ls.score,
  ls.classification,
  ls.confidence,
  ls.factors,
  ls.reasoning,
  ls.created_at
from lead_scores ls
order by ls.lead_id, ls.created_at desc;

-- One row. Every figure on the Overview page is an aggregate over real rows.
create or replace view v_dashboard_metrics
with (security_invoker = on) as
select
  b.id as business_id,

  (select count(*) from leads l
    where l.business_id = b.id and l.status in ('new','qualified'))            as open_leads,

  (select count(*) from leads l
     join v_lead_current_score s on s.lead_id = l.id
    where l.business_id = b.id
      and s.classification = 'HOT'
      and l.status not in ('converted','lost'))                                as hot_leads,

  (select count(*) from appointments a
    where a.business_id = b.id and a.status = 'booked'
      and a.starts_at > now())                                                 as upcoming_appointments,

  (select count(*) from appointments a
    where a.business_id = b.id and a.status = 'completed'
      and a.completed_at >= date_trunc('month', now()))                        as jobs_this_month,

  (select coalesce(sum(i.amount), 0) from invoices i
    where i.business_id = b.id and i.status in ('sent','overdue'))             as outstanding_amount,

  (select count(*) from invoices i
    where i.business_id = b.id and i.status = 'overdue')                       as overdue_invoices,

  (select coalesce(sum(i.amount), 0) from invoices i
    where i.business_id = b.id and i.status = 'overdue')                       as overdue_amount,

  (select round(avg(r.rating)::numeric, 2) from reviews r
    where r.business_id = b.id and r.rating is not null)                       as avg_rating,

  (select count(*) from reviews r
    where r.business_id = b.id and r.submitted_at is not null)                 as reviews_collected,

  (select count(*) from reviews r
    where r.business_id = b.id and r.requested_at is not null
      and r.submitted_at is null)                                              as reviews_awaiting,

  (select count(*) from customers c
    where c.business_id = b.id and c.status = 'dormant')                       as dormant_customers,

  (select coalesce(sum(c.lifetime_value), 0) from customers c
    where c.business_id = b.id and c.status = 'dormant')                       as dormant_value,

  (select count(*) from customers c
    where c.business_id = b.id)                                                as total_customers,

  (select count(*) from tasks t
    where t.business_id = b.id and t.status = 'open')                          as open_tasks

from businesses b;

-- Things a human should look at, newest first. One shape for several sources so
-- the Attention panel is a single list rather than four stacked widgets.
create or replace view v_attention
with (security_invoker = on) as
  select
    i.business_id,
    'overdue_payment'::text                          as kind,
    'critical'::text                                 as tone,
    c.full_name                                      as subject,
    'Invoice ' || i.invoice_number || ' — ' ||
      to_char(i.amount, 'FM99,99,999') || ' overdue'  as detail,
    (current_date - i.due_on)::int                   as age_days,
    i.due_on::timestamptz                            as occurred_at,
    i.id                                             as entity_id
  from invoices i
  join customers c on c.id = i.customer_id
  where i.status = 'overdue'

union all
  select
    l.business_id,
    'hot_lead',
    'warning',
    coalesce(c.full_name, 'Unknown caller'),
    'Lead scored ' || s.score || '/100 — no follow-up yet',
    (current_date - l.created_at::date)::int,
    l.created_at,
    l.id
  from leads l
  join v_lead_current_score s on s.lead_id = l.id
  left join customers c on c.id = l.customer_id
  where s.classification = 'HOT'
    and l.status in ('new','qualified')

union all
  select
    t.business_id,
    'human_task',
    case when t.priority in ('urgent','high') then 'critical' else 'neutral' end,
    coalesce(c.full_name, 'System'),
    t.title,
    (current_date - t.created_at::date)::int,
    t.created_at,
    t.id
  from tasks t
  left join customers c on c.id = t.customer_id
  where t.status = 'open';

grant select on v_lead_current_score, v_dashboard_metrics, v_attention to anon;
