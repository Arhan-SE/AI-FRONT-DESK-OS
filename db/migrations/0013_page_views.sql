-- 0013_page_views.sql
-- Read models for Payments, Customers and Campaigns.
--
-- These exist so each page is one query rather than a fan-out of joins done in
-- the browser. security_invoker keeps them subject to the caller's RLS.

-- Invoices with the customer, the job, and the chase history.
--
-- reminders_sent is counted from message_log rather than stored on the invoice:
-- the log is what actually happened, and a counter column would drift the first
-- time a send was blocked.
create or replace view v_invoices
with (security_invoker = on) as
select
  i.id,
  i.business_id,
  i.invoice_number,
  i.amount,
  i.status,
  i.issued_on,
  i.due_on,
  i.paid_at,
  i.created_at,
  c.id           as customer_id,
  c.full_name    as customer_name,
  c.telegram_chat_id is not null as customer_reachable,
  s.name         as service_name,
  a.id           as appointment_id,
  a.starts_at    as service_date,
  p.method       as payment_method,

  -- Negative once due, so "days" reads naturally as overdue-by.
  (current_date - i.due_on)::int as days_past_due,

  (select count(*) from message_log m
    where m.business_id = i.business_id
      and m.message_type = 'payment_reminder'
      and m.status = 'sent'
      and m.dedupe_key like i.id::text || ':%')            as reminders_sent,

  (select max(m.created_at) from message_log m
    where m.business_id = i.business_id
      and m.message_type = 'payment_reminder'
      and m.status = 'sent'
      and m.dedupe_key like i.id::text || ':%')            as last_reminder_at,

  (select min(j.scheduled_for) from automation_jobs j
    where j.business_id = i.business_id
      and j.job_type = 'payment_reminder'
      and j.status = 'pending'
      and j.dedupe_key like 'invoice:' || i.id::text || ':%') as next_reminder_at

from invoices i
join customers c on c.id = i.customer_id
left join appointments a on a.id = i.appointment_id
left join services   s on s.id = a.service_id
left join payments   p on p.invoice_id = i.id;


-- One row per customer with everything the list and detail views need.
create or replace view v_customers
with (security_invoker = on) as
select
  c.id,
  c.business_id,
  c.full_name,
  c.phone,
  c.email,
  c.address,
  c.status,
  c.telegram_chat_id,
  c.telegram_chat_id is not null as reachable,
  c.telegram_opted_in,
  c.do_not_contact,
  c.last_contacted_at,
  c.created_at,

  (select count(*) from appointments a
    where a.customer_id = c.id and a.status = 'completed')      as jobs_completed,

  (select count(*) from appointments a
    where a.customer_id = c.id
      and a.status in ('booked','confirmed','in_progress'))     as jobs_upcoming,

  (select max(a.starts_at) from appointments a
    where a.customer_id = c.id and a.status = 'completed')      as last_service_at,

  (select coalesce(sum(i.amount), 0) from invoices i
    where i.customer_id = c.id and i.status = 'paid')           as total_paid,

  (select coalesce(sum(i.amount), 0) from invoices i
    where i.customer_id = c.id and i.status in ('sent','overdue')) as amount_outstanding,

  (select round(avg(r.rating)::numeric, 1) from reviews r
    where r.customer_id = c.id and r.rating is not null)        as avg_rating,

  (select count(*) from message_log m
    where m.customer_id = c.id and m.status = 'sent')           as messages_sent,

  (select count(*) from message_log m
    where m.customer_id = c.id and m.status = 'blocked')        as messages_blocked

from customers c;


-- Campaign roll-up. Counts come from campaign_recipients so a campaign that
-- was mostly blocked reports honestly rather than claiming it "sent".
create or replace view v_campaigns
with (security_invoker = on) as
select
  ca.id,
  ca.business_id,
  ca.name,
  ca.campaign_type,
  ca.status,
  ca.template_key,
  ca.scheduled_for,
  ca.started_at,
  ca.completed_at,
  ca.created_at,
  count(cr.id)                                            as audience,
  count(cr.id) filter (where cr.status = 'sent')          as sent,
  count(cr.id) filter (where cr.status = 'blocked')       as blocked,
  count(cr.id) filter (where cr.status = 'failed')        as failed,
  count(cr.id) filter (where cr.status = 'replied')       as replied,
  count(cr.id) filter (where cr.status = 'pending')       as pending
from campaigns ca
left join campaign_recipients cr on cr.campaign_id = ca.id
group by ca.id;


grant select on v_invoices, v_customers, v_campaigns to anon;
