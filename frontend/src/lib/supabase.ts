import { createClient } from "@supabase/supabase-js";

const url = import.meta.env.VITE_SUPABASE_URL;
const anonKey = import.meta.env.VITE_SUPABASE_ANON_KEY;

if (!url || !anonKey) {
  throw new Error(
    "VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY must be set. Copy .env from the repo root.",
  );
}

/**
 * Read-only client.
 *
 * The anon key ships inside this bundle, so Row Level Security — not this
 * client — is what actually restricts access. Policies grant `anon` SELECT and
 * nothing else; every mutation goes through FastAPI with the service-role key.
 */
export const supabase = createClient(url, anonKey, {
  auth: { persistSession: false },
});

/** Single demo tenant. Becomes a JWT claim when auth lands. */
export const BUSINESS_ID = "00000000-0000-0000-0000-000000000001";
