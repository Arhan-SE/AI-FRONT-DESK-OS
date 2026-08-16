-- 002_dormant_cohort.sql
-- Customers who used the business once or twice and then stopped.
--
-- 001 only generates the last 180 days, so every customer it creates has been
-- serviced recently and nothing is dormant. Lead Reactivation needs an audience
-- with real lapsed history — not a status flag flipped on an active customer,
-- which is what the reactivation scorer would have to see through.
--
-- These customers get appointments 200-400 days back, so their dormancy is a
-- fact derivable from the data rather than an assertion.

do $$
declare
  biz uuid := '00000000-0000-0000-0000-000000000001';
  tz  text := 'Asia/Kolkata';
  first_names text[] := array['Rajesh','Sunita','Vikram','Anjali','Deepak','Kiran','Sanjay','Nisha',
                              'Mohan','Geeta','Prakash','Sudha','Ravi','Latha','Ashok','Vandana',
                              'Naveen','Rekha','Girish','Bhavana'];
  last_names  text[] := array['Krishnan','Murthy','Prasad','Naidu','Hegde','Acharya','Shenoy',
                              'Kamath','Rangan','Subramanian'];
  areas       text[] := array['Rajajinagar','Basavanagudi','Yelahanka','Marathahalli','JP Nagar',
                              'Vijayanagar','Bellandur','Kalyan Nagar'];
  svc_ids uuid[]; tech_ids uuid[];
  cust uuid; svc uuid; tech uuid;
  dur int; buf int; price numeric;
  d date; starts timestamptz; ends timestamptz;
  appt uuid; inv_no int; visits int;
  i int; j int;
begin
  perform setseed(0.8181);

  select array_agg(id) into svc_ids  from services    where business_id = biz;
  select array_agg(id) into tech_ids from technicians where business_id = biz;
  select coalesce(max(substring(invoice_number from 5)::int), 2000) into inv_no
    from invoices where business_id = biz;

  for i in 1..35 loop
    insert into customers (business_id, full_name, phone, address, status, first_seen_at)
    values (biz,
      first_names[1 + floor(random()*array_length(first_names,1))::int] || ' ' ||
        last_names[1 + floor(random()*array_length(last_names,1))::int],
      '+91 9' || lpad(floor(random()*999999999)::text, 9, '0'),
      areas[1 + floor(random()*array_length(areas,1))::int] || ', Bengaluru',
      'active',
      now() - make_interval(days => 400 + floor(random()*200)::int))
    returning id into cust;

    visits := 1 + floor(random()*3)::int;   -- one to three visits, then silence

    for j in 1..visits loop
      svc  := svc_ids[1 + floor(random()*array_length(svc_ids,1))::int];
      tech := tech_ids[1 + floor(random()*array_length(tech_ids,1))::int];
      d    := current_date - (200 + floor(random()*200)::int);

      if extract(dow from d) = 0 then
        d := d + 1;
      end if;

      select duration_minutes, buffer_minutes, base_price into dur, buf, price
        from services where id = svc;

      starts := (d + (array['09:00','12:00','15:00'])[1 + floor(random()*3)::int]::time) at time zone tz;
      ends   := starts + make_interval(mins => dur);

      begin
        insert into appointments (business_id, customer_id, service_id, technician_id,
                                  starts_at, ends_at, buffer_minutes, blocked_until,
                                  status, source, completed_at)
        values (biz, cust, svc, tech, starts, ends, buf, ends + make_interval(mins => buf),
                'completed', 'manual', ends)
        returning id into appt;
      exception when exclusion_violation then
        appt := null;   -- slot taken by another lapsed customer; skip this visit
      end;

      if appt is not null then
        inv_no := inv_no + 1;
        insert into invoices (business_id, customer_id, appointment_id, invoice_number,
                              amount, status, issued_on, due_on, paid_at)
        values (biz, cust, appt, 'INV-' || inv_no, price, 'paid', d, d + 14, ends + interval '3 days');

        update customers
           set last_service_at = greatest(coalesce(last_service_at, ends), ends),
               lifetime_value  = lifetime_value + price
         where id = cust;
      end if;
    end loop;
  end loop;

  -- Dormancy is derived, never asserted.
  update customers
     set status = 'dormant'
   where business_id = biz
     and last_service_at is not null
     and last_service_at < now() - interval '120 days';
end $$;
