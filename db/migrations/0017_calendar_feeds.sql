-- 0017_calendar_feeds.sql
-- Read-only iCal subscription feeds.
--
-- A calendar client cannot log in — it fetches a URL on a timer, unattended,
-- forever. So the URL itself has to be the credential: a long random token that
-- identifies one technician's feed and grants nothing else. Guessing one is not
-- feasible, revoking one is a single UPDATE, and losing one exposes a schedule
-- rather than an account.
--
-- The database stays the source of truth. This publishes what it already knows;
-- nothing is ever read back in from a calendar client, so the exclusion
-- constraint that makes double-booking impossible remains the only authority on
-- what is booked.

alter table technicians
  add column if not exists calendar_token text unique;

alter table businesses
  add column if not exists calendar_token text unique;

-- 18 random bytes = 36 hex characters. Long enough that guessing is hopeless,
-- short enough to paste into a calendar app without wrapping.
update technicians
   set calendar_token = encode(gen_random_bytes(18), 'hex')
 where calendar_token is null;

update businesses
   set calendar_token = encode(gen_random_bytes(18), 'hex')
 where calendar_token is null;

-- New technicians get a feed without anyone remembering to issue one.
alter table technicians
  alter column calendar_token set default encode(gen_random_bytes(18), 'hex');

alter table businesses
  alter column calendar_token set default encode(gen_random_bytes(18), 'hex');

-- The feed endpoint looks a technician up by token alone, so this lookup is on
-- the hot path of every calendar refresh.
create index if not exists technicians_calendar_token_idx
  on technicians (calendar_token);

-- The token is a credential. The browser reads under the anon role, and no
-- dashboard view needs it, so it is not exposed there — the feed URLs are
-- served by the API, which holds the service-role key.
