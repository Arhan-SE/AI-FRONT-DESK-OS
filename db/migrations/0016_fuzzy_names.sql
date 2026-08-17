-- 0016_fuzzy_names.sql
-- Trigram matching for caller identification.
--
-- Speech recognition does not spell names consistently. "Muhammad Kareem" came
-- back as "Mohammed Kareem" on one call and "Mohammad Kareem" on the next, and
-- exact matching created a new customer each time — so the same person
-- accumulated three records, none of which had his history.
--
-- Trigram similarity closes that gap without loosening the rule that matters:
-- the agent still refuses to guess between two plausible people, it just no
-- longer treats a spelling variant as a stranger.

create extension if not exists pg_trgm;

create index if not exists customers_name_trgm_idx
  on customers using gin (full_name gin_trgm_ops);
