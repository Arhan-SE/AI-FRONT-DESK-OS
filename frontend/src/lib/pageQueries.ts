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

/* --------------------------------------------------------------- ai usage */

export interface UsageSummary {
  total_calls: number;
  voice_minutes: number;
  total_tokens: number;
  audio_tokens: number;
  total_cost_usd: number;
  voice_cost_usd: number;
  text_cost_usd: number;
  total_decisions: number;
  blocked_decisions: number;
  failed_decisions: number;
}

export function useUsageSummary() {
  return useQuery({
    queryKey: ["usage-summary"],
    queryFn: async () =>
      unwrap(
        await from("v_usage_summary").single(),
      ) as UsageSummary,
    refetchInterval: 10_000,
  });
}

export interface UsageEvent {
  id: string;
  source: string;
  model: string;
  purpose: string | null;
  input_text_tokens: number;
  input_audio_tokens: number;
  output_text_tokens: number;
  output_audio_tokens: number;
  duration_seconds: number;
  cost_usd: number;
  created_at: string;
}

export function useUsageEvents(limit = 40) {
  return useQuery({
    queryKey: ["usage-events", limit],
    queryFn: async () =>
      unwrap(
        await from("usage_events").order("created_at", { ascending: false }).limit(limit),
      ) as UsageEvent[],
    refetchInterval: 10_000,
  });
}

export interface DailyActivity {
  day: string;
  jobs: number;
  completed: number;
  collected: number;
  decisions: number;
  calls: number;
}

export function useDailyActivity() {
  return useQuery({
    queryKey: ["daily-activity"],
    queryFn: async () =>
      unwrap(await from("v_daily_activity").order("day")) as DailyActivity[],
    refetchInterval: 30_000,
  });
}

/* ------------------------------------------------------------- conversations */

export interface ConversationRow {
  id: string;
  channel: string;
  status: string;
  summary: string | null;
  current_intent: string | null;
  started_at: string;
  ended_at: string | null;
  customers: { full_name: string } | null;
}

export function useConversations() {
  return useQuery({
    queryKey: ["conversations"],
    queryFn: async () =>
      unwrap(
        await supabase
          .from("conversations")
          .select("id,channel,status,summary,current_intent,started_at,ended_at,customers(full_name)")
          .eq("business_id", BUSINESS_ID)
          .order("started_at", { ascending: false })
          .limit(50),
      ) as unknown as ConversationRow[],
    refetchInterval: 10_000,
  });
}

export interface MessageRow {
  id: string;
  role: "customer" | "agent" | "system" | "human";
  content: string;
  created_at: string;
}

export function useMessages(conversationId: string | null) {
  return useQuery({
    queryKey: ["messages", conversationId],
    enabled: conversationId !== null,
    queryFn: async () =>
      unwrap(
        await supabase
          .from("messages")
          .select("id,role,content,created_at")
          .eq("business_id", BUSINESS_ID)
          .eq("conversation_id", conversationId!)
          .order("created_at", { ascending: true }),
      ) as MessageRow[],
    // A call in progress should stream into the panel while it happens.
    refetchInterval: 4_000,
  });
}

export function useConversationDecisions(conversationId: string | null) {
  return useQuery({
    queryKey: ["conversation-decisions", conversationId],
    enabled: conversationId !== null,
    queryFn: async () =>
      unwrap(
        await supabase
          .from("ai_decisions")
          .select("id,event_type,status,summary,created_at")
          .eq("business_id", BUSINESS_ID)
          .eq("conversation_id", conversationId!)
          .order("created_at", { ascending: true }),
      ) as { id: string; event_type: string; status: string; summary: string; created_at: string }[],
    refetchInterval: 4_000,
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
