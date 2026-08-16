-- 001_demo_business.sql
-- Six months of operating history for the demo business.
--
-- This is generated, not hand-written: loops over real dates producing real
-- rows, so every figure the dashboard shows is an aggregate over actual data.
-- Nothing in the UI is hardcoded.
--
-- Deterministic via setseed(), so re-running produces the same business and a
-- rehearsed demo matches the live one.
--
-- Safe to re-run: it clears the demo tenant first.

do $$
declare
  biz   uuid := '00000000-0000-0000-0000-000000000001';
  tz    text := 'Asia/Kolkata';

  first_names text[] := array['Aarav','Vivaan','Aditya','Diya','Ananya','Ishaan','Kabir','Meera',
                              'Rohan','Saanvi','Arjun','Kavya','Nikhil','Priya','Rahul','Sneha',
                              'Karthik','Divya','Manish','Pooja','Siddharth','Neha','Varun','Ritu',
                              'Aniket','Shreya','Gaurav','Tanvi','Harsh','Lakshmi'];
  last_names  text[] := array['Sharma','Verma','Reddy','Nair','Iyer','Patel','Gupta','Rao',
                              'Menon','Desai','Kulkarni','Joshi','Chopra','Bhat','Pillai','Shetty'];
  areas       text[] := array['Indiranagar','Koramangala','Whitefield','HSR Layout','Jayanagar',
                              'Malleshwaram','Electronic City','Banashankari','Hebbal','BTM Layout'];

  svc_ac_service uuid; svc_ac_repair uuid; svc_install uuid;
  svc_deep_clean uuid; svc_gas uuid; svc_amc uuid;
  tech_ids uuid[]; svc_ids uuid[];
  cust_ids uuid[];

  d            date;
  slot_times   time[] := array['09:00','12:00','15:00']::time[];
  slot_t       time;
  tech         uuid;
  svc          uuid;
  cust         uuid;
  dur          int;
  buf          int;
  price        numeric;
  starts       timestamptz;
  ends         timestamptz;
  appt         uuid;
  appt_status  text;
  inv          uuid;
  inv_no       int := 1000;
  r            real;
  i            int;
  lead_id_v    uuid;
  conv_id      uuid;
  score_v      int;
begin
  perform setseed(0.4242);

  -- Clear the demo tenant. Cascades handle the children.
  delete from businesses where id = biz;

  -- ---------------------------------------------------------------- business
  insert into businesses (id, name, trade, timezone, phone, email, address)
  values (biz, 'Apex Climate Care', 'hvac', tz, '+91 80 4123 7788',
          'care@apexclimate.in', '14, 100 Feet Road, Indiranagar, Bengaluru 560038');

  -- Mon-Sat 09:00-18:00, closed Sunday (weekday 0).
  insert into business_hours (business_id, weekday, opens_at, closes_at, is_closed)
  select biz, w, '09:00'::time, '18:00'::time, (w = 0)
  from generate_series(0, 6) as w;

  insert into business_holidays (business_id, holiday_on, name) values
    (biz, date '2026-08-15', 'Independence Day'),
    (biz, date '2026-10-02', 'Gandhi Jayanti'),
    (biz, date '2026-11-08', 'Deepavali');

  -- ---------------------------------------------------------------- services
  insert into services (business_id, name, description, duration_minutes, buffer_minutes, base_price, required_skill)
  values (biz, 'AC Service', 'Standard split-AC service and filter clean', 60, 15, 1499, 'hvac')
  returning id into svc_ac_service;

  insert into services (business_id, name, description, duration_minutes, buffer_minutes, base_price, required_skill)
  values (biz, 'AC Repair', 'Diagnosis and repair of cooling faults', 90, 15, 2499, 'hvac')
  returning id into svc_ac_repair;

  insert into services (business_id, name, description, duration_minutes, buffer_minutes, base_price, required_skill)
  values (biz, 'AC Installation', 'New split-AC mounting and commissioning', 120, 30, 4999, 'install')
  returning id into svc_install;

  insert into services (business_id, name, description, duration_minutes, buffer_minutes, base_price, required_skill)
  values (biz, 'Deep Cleaning', 'Jet-spray coil and blower deep clean', 90, 15, 1999, 'hvac')
  returning id into svc_deep_clean;

  insert into services (business_id, name, description, duration_minutes, buffer_minutes, base_price, required_skill)
  values (biz, 'Gas Refill', 'Refrigerant top-up and leak check', 60, 15, 2999, 'hvac')
  returning id into svc_gas;

  insert into services (business_id, name, description, duration_minutes, buffer_minutes, base_price, required_skill)
  values (biz, 'Annual Maintenance Visit', 'Scheduled AMC inspection', 45, 15, 999, 'hvac')
  returning id into svc_amc;

  svc_ids := array[svc_ac_service, svc_ac_repair, svc_install, svc_deep_clean, svc_gas, svc_amc];

  -- ------------------------------------------------------------- technicians
  insert into technicians (business_id, full_name, phone, skills) values
    (biz, 'Ramesh Kumar',  '+91 98450 11223', array['hvac','install']),
    (biz, 'Suresh Babu',   '+91 98450 33445', array['hvac']),
    (biz, 'Anil Prakash',  '+91 98450 55667', array['hvac','install']);

  select array_agg(id order by full_name) into tech_ids from technicians where business_id = biz;

  -- Mon-Sat 09:00-18:00 for every technician.
  insert into technician_schedules (business_id, technician_id, weekday, starts_at, ends_at)
  select biz, t, w, '09:00'::time, '18:00'::time
  from unnest(tech_ids) as t, generate_series(1, 6) as w;

  insert into technician_time_off (business_id, technician_id, starts_at, ends_at, reason)
  values (biz, tech_ids[2], now() + interval '9 days', now() + interval '12 days', 'Family function');

  -- ----------------------------------------------------------------- customers
  for i in 1..45 loop
    insert into customers (business_id, full_name, phone, email, address, status, first_seen_at)
    values (
      biz,
      first_names[1 + floor(random() * array_length(first_names,1))::int] || ' ' ||
        last_names[1 + floor(random() * array_length(last_names,1))::int],
      '+91 9' || lpad(floor(random() * 999999999)::text, 9, '0'),
      null,
      areas[1 + floor(random() * array_length(areas,1))::int] || ', Bengaluru',
      'active',
      now() - make_interval(days => 30 + floor(random() * 300)::int)
    );
  end loop;

  select array_agg(id) into cust_ids from customers where business_id = biz;

  -- --------------------------------------------------------------- appointments
  -- Three slots a day at 09:00 / 12:00 / 15:00. The widest service blocks
  -- 150 minutes, so a 3-hour spacing can never trip the exclusion constraint.
  d := current_date - 180;
  while d <= current_date + 14 loop
    if extract(dow from d) <> 0 then
      foreach tech in array tech_ids loop
        foreach slot_t in array slot_times loop
          -- roughly 45% slot utilisation
          if random() < 0.45 then
            svc  := svc_ids[1 + floor(random() * array_length(svc_ids,1))::int];
            cust := cust_ids[1 + floor(random() * array_length(cust_ids,1))::int];

            select duration_minutes, buffer_minutes, base_price
              into dur, buf, price
              from services where id = svc;

            starts := (d + slot_t) at time zone tz;
            ends   := starts + make_interval(mins => dur);

            if d < current_date then
              r := random();
              appt_status := case when r < 0.90 then 'completed'
                                  when r < 0.96 then 'cancelled'
                                  else 'no_show' end;
            else
              appt_status := 'booked';
            end if;

            begin
              insert into appointments (business_id, customer_id, service_id, technician_id,
                                        starts_at, ends_at, buffer_minutes, blocked_until,
                                        status, source, completed_at, cancelled_at)
              values (biz, cust, svc, tech, starts, ends, buf,
                      ends + make_interval(mins => buf),
                      appt_status,
                      case when random() < 0.55 then 'voice' else 'manual' end,
                      case when appt_status = 'completed' then ends end,
                      case when appt_status = 'cancelled' then starts - interval '1 day' end)
              returning id into appt;
            exception when exclusion_violation then
              -- Unreachable given the 3-hour spacing, but if it ever fires we
              -- must not let a stale appt id leak into the invoice below.
              appt := null;
            end;

            -- ------------------------------------------------------ invoices
            if appt is not null and appt_status = 'completed' then
              inv_no := inv_no + 1;
              r := random();
              insert into invoices (business_id, customer_id, appointment_id, invoice_number,
                                    amount, status, issued_on, due_on, paid_at)
              values (biz, cust, appt, 'INV-' || inv_no, price,
                      case when r < 0.72 then 'paid'
                           when d < current_date - 14 then 'overdue'
                           else 'sent' end,
                      d, d + 14,
                      case when r < 0.72 then ends + make_interval(days => floor(random()*10)::int) end)
              returning id into inv;

              if r < 0.72 then
                insert into payments (business_id, invoice_id, amount, method, paid_at)
                values (biz, inv, price,
                        (array['cash','upi','card','bank_transfer'])[1 + floor(random()*4)::int],
                        ends + make_interval(days => floor(random()*10)::int));
              end if;

              -- ---------------------------------------------------- reviews
              if random() < 0.42 then
                insert into reviews (business_id, customer_id, appointment_id, rating, comment,
                                     source, requested_at, submitted_at)
                values (biz, cust, appt,
                        (array[5,5,5,4,4,3])[1 + floor(random()*6)::int],
                        (array['Prompt and professional.',
                               'Technician explained the issue clearly.',
                               'Good service, arrived on time.',
                               'Cooling is much better now.',
                               'Reasonable pricing, will use again.',
                               'Took longer than expected but sorted it.'])[1 + floor(random()*6)::int],
                        'telegram', ends + interval '1 day', ends + interval '2 days');
              elsif random() < 0.3 then
                -- requested but never answered: real response-rate figures
                insert into reviews (business_id, customer_id, appointment_id, source, requested_at)
                values (biz, cust, appt, 'telegram', ends + interval '1 day');
              end if;

              update customers
                 set last_service_at = greatest(coalesce(last_service_at, ends), ends),
                     lifetime_value  = lifetime_value + price
               where id = cust;
            end if;
          end if;
        end loop;
      end loop;
    end if;
    d := d + 1;
  end loop;

  -- Anyone untouched for 120+ days is dormant — the reactivation audience.
  update customers
     set status = 'dormant'
   where business_id = biz
     and (last_service_at is null or last_service_at < now() - interval '120 days');

  -- --------------------------------------------------------------------- leads
  for i in 1..22 loop
    cust := cust_ids[1 + floor(random() * array_length(cust_ids,1))::int];
    svc  := svc_ids[1 + floor(random() * array_length(svc_ids,1))::int];

    insert into conversations (business_id, customer_id, channel, status, current_intent,
                               summary, started_at, ended_at)
    values (biz, cust, 'voice', 'ended', 'NEW_LEAD',
            'Customer enquired about ' || (select name from services where id = svc) || '.',
            now() - make_interval(days => floor(random()*60)::int, mins => floor(random()*600)::int),
            now() - make_interval(days => floor(random()*60)::int))
    returning id into conv_id;

    insert into leads (business_id, customer_id, conversation_id, service_id, status, source,
                       urgency, requested_service, location, preferred_timing, next_action, created_at)
    values (biz, cust, conv_id, svc,
            (array['new','qualified','contacted','converted','lost'])[1 + floor(random()*5)::int],
            'voice',
            (array['low','medium','high'])[1 + floor(random()*3)::int],
            (select name from services where id = svc),
            areas[1 + floor(random() * array_length(areas,1))::int] || ', Bengaluru',
            (array['morning','afternoon','evening'])[1 + floor(random()*3)::int],
            'Call back to confirm slot',
            now() - make_interval(days => floor(random()*60)::int))
    returning id into lead_id_v;

    score_v := 35 + floor(random() * 62)::int;
    insert into lead_scores (business_id, lead_id, score, classification, confidence, factors, reasoning)
    values (biz, lead_id_v, score_v,
            case when score_v >= 75 then 'HOT' when score_v >= 50 then 'WARM' else 'COLD' end,
            0.62 + random() * 0.35,
            jsonb_build_object(
              'intent',         least(25, floor(score_v * 0.28)::int),
              'urgency',        least(20, floor(score_v * 0.21)::int),
              'service_match',  least(20, floor(score_v * 0.22)::int),
              'customer_value', least(20, floor(score_v * 0.17)::int),
              'engagement',     least(15, floor(score_v * 0.12)::int)),
            case when score_v >= 75
              then array['Clear service intent','High stated urgency','Service matches offering']
              when score_v >= 50
              then array['Service intent present','Timing flexible','Within service area']
              else array['Exploratory enquiry','No timeline given'] end);
  end loop;

  -- --------------------------------------------------------- message templates
  insert into message_templates (business_id, key, message_type, category, body) values
    (biz, 'appointment_confirmation', 'appointment_confirmation', 'transactional',
     'Hi {{name}}, your {{service}} is confirmed for {{when}} with {{technician}}. — Apex Climate Care'),
    (biz, 'appointment_reminder', 'appointment_reminder', 'transactional',
     'Reminder: your {{service}} is tomorrow at {{time}}. Reply CHANGE to reschedule. — Apex Climate Care'),
    (biz, 'post_service_followup', 'post_service_followup', 'transactional',
     'Hi {{name}}, hope the {{service}} on {{date}} sorted things out. Any issues, just reply here.'),
    (biz, 'payment_reminder', 'payment_reminder', 'transactional',
     'Hi {{name}}, invoice {{invoice}} for Rs {{amount}} was due on {{due}}. Reply PAID once settled.'),
    (biz, 'review_request', 'review_request', 'transactional',
     'Hi {{name}}, how did we do on your {{service}}? Reply 1-5 (5 = excellent). Thanks!'),
    (biz, 'reactivation', 'reactivation', 'marketing',
     'Hi {{name}}, it has been {{months}} months since your last AC service. Pre-monsoon slots are open — reply YES to book.'),
    (biz, 'seasonal', 'seasonal', 'marketing',
     'Summer is here. Book an AC service before peak season and skip the wait. Reply YES.');

  raise notice 'Seed complete.';
end $$;
