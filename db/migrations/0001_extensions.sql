-- 0001_extensions.sql
-- Extensions and shared helpers. Run first.

create extension if not exists pgcrypto;    -- gen_random_uuid()
create extension if not exists btree_gist;  -- uuid equality inside EXCLUDE constraints
create extension if not exists vector;      -- semantic customer memory

-- Every table carries updated_at; keep it honest without app-side discipline.
--
-- search_path is pinned: an unpinned function can be hijacked by a caller who
-- puts a malicious schema earlier in their own search_path.
create or replace function set_updated_at()
returns trigger
language plpgsql
set search_path = pg_catalog
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;
