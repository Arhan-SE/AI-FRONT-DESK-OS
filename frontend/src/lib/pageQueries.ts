import { useQuery } from "@tanstack/react-query";
import { supabase, BUSINESS_ID } from "./supabase";

function unwrap<T>({ data, error }: { data: T | null; error: { message: string } | null }): T {
  if (error) throw new Error(error.message);
  return data as T;
}

const from = (view: string) =>
  supabase.from(view).select("*").eq("business_id", BUSINESS_ID);

/* ------------------------------------------------------------------ invoices */

export interface Invoice {
  id: string;
  invoice_number: string;
  amount: number;
  status: "draft" | "sent" | "paid" | "overdue" | "void";
  issued_on: string;
  due_on: string;
  paid_at: string | null;
  customer_id: string;
  customer_name: string;
  customer_reachable: boolean;
  service_name: string | null;
  service_date: string | null;
  payment_method: string | null;
  days_past_due: number;
  reminders_sent: number;
  last_reminder_at: string | null;
  next_reminder_at: string | null;
}

export function useInvoices() {
  return useQuery({
    queryKey: ["invoices"],
    queryFn: async () =>
      unwrap(await from("v_invoices").order("issued_on", { ascending: false })) as Invoice[],
    refetchInterval: 20_000,
  });
}

/* ----------------------------------------------------------------- customers */

export interface CustomerRow {
  id: string;
  full_name: string;
  phone: string | null;
  email: string | null;
  address: string | null;
  status: string;
  reachable: boolean;
  // bigint in Postgres — PostgREST returns it as a number in JSON.
  telegram_chat_id: number | null;
  telegram_opted_in: boolean;
  do_not_contact: boolean;
  last_contacted_at: string | null;
  jobs_completed: number;
  jobs_upcoming: number;
  last_service_at: string | null;
  total_paid: number;
  amount_outstanding: number;
  avg_rating: number | null;
  messages_sent: number;
  messages_blocked: number;
}

export function useCustomers() {
  return useQuery({
    queryKey: ["customers"],
    queryFn: async () =>
      unwrap(await from("v_customers").order("full_name")) as CustomerRow[],
    refetchInterval: 30_000,
  });
}

/* --------------------------------------------------------------- appointments */

export interface JobRow {
  id: string;
  stage: string;
  starts_at: string;
  ends_at: string;
  customer_name: string;
  service_name: string;
  technician_name: string;
  source: string;
  appointment_status: string;
  invoice_number: string | null;
  invoice_amount: number | null;
}

export function useAppointments() {
  return useQuery({
    queryKey: ["appointments"],
    queryFn: async () =>
      unwrap(await from("v_jobs").order("starts_at", { ascending: true })) as JobRow[],
    refetchInterval: 20_000,
  });
}

/* ------------------------------------------------------------------ campaigns */

export interface CampaignRow {
  id: string;
  name: string;
  campaign_type: string;
  status: string;
  created_at: string;
  started_at: string | null;
  audience: number;
  sent: number;
  blocked: number;
  failed: number;
  replied: number;
  pending: number;
}

export function useCampaigns() {
  return useQuery({
    queryKey: ["campaigns"],
    queryFn: async () =>
      unwrap(
        await from("v_campaigns").order("created_at", { ascending: false }),
      ) as CampaignRow[],
    refetchInterval: 10_000,
  });
}

/* ---------------------------------------------------------------------- leads */

export interface LeadRow {
  id: string;
  status: string;
  source: string;
  urgency: string | null;
  requested_service: string | null;
  location: string | null;
  preferred_timing: string | null;
  next_action: string | null;
  created_at: string;
  customers: { full_name: string } | null;
}

export function useLeads() {
  return useQuery({
    queryKey: ["leads"],
    queryFn: async () =>
      unwrap(
        await supabase
          .from("leads")
          .select(
            "id,status,source,urgency,requested_service,location,preferred_timing,next_action,created_at,customers(full_name)",
          )
          .eq("business_id", BUSINESS_ID)
          .order("created_at", { ascending: false }),
      ) as unknown as LeadRow[],
    refetchInterval: 15_000,
  });
}

/* ---------------------------------------------------------------- lead scores */

export interface LeadScore {
  lead_id: string;
  score: number;
  classification: "HOT" | "WARM" | "COLD";
  confidence: number;
  reasoning: string[];
}

export function useLeadScores() {
  return useQuery({
    queryKey: ["lead-scores"],
    queryFn: async () =>
      unwrap(
        await supabase
          .from("v_lead_current_score")
          .select("lead_id,score,classification,confidence,reasoning")
          .eq("business_id", BUSINESS_ID),
      ) as LeadScore[],
  });
}

/* -------------------------------------------------------------------- reviews */

export interface ReviewRow {
  id: string;
  rating: number | null;
  comment: string | null;
  requested_at: string | null;
  submitted_at: string | null;
  customers: { full_name: string } | null;
}

export function useReviews() {
  return useQuery({
    queryKey: ["reviews"],
    queryFn: async () =>
      unwrap(
        await supabase
          .from("reviews")
          .select("id,rating,comment,requested_at,submitted_at,customers(full_name)")
          .eq("business_id", BUSINESS_ID)
          .order("created_at", { ascending: false }),
      ) as unknown as ReviewRow[],
    refetchInterval: 20_000,
  });
}
