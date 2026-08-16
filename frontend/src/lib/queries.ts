import { useQuery } from "@tanstack/react-query";
import { useEffect } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { supabase, BUSINESS_ID } from "./supabase";

/** Supabase returns an error object rather than throwing; react-query needs a throw. */
function unwrap<T>({ data, error }: { data: T | null; error: { message: string } | null }): T {
  if (error) throw new Error(error.message);
  return data as T;
}

export interface DashboardMetrics {
  open_leads: number;
  hot_leads: number;
  upcoming_appointments: number;
  jobs_this_month: number;
  outstanding_amount: string;
  overdue_invoices: number;
  overdue_amount: string;
  avg_rating: string | null;
  reviews_collected: number;
  reviews_awaiting: number;
  dormant_customers: number;
  dormant_value: string;
  total_customers: number;
  open_tasks: number;
}

export function useDashboardMetrics() {
  return useQuery({
    queryKey: ["dashboard-metrics"],
    queryFn: async () =>
      unwrap(
        await supabase
          .from("v_dashboard_metrics")
          .select("*")
          .eq("business_id", BUSINESS_ID)
          .single(),
      ) as DashboardMetrics,
    staleTime: 30_000,
  });
}

export interface AttentionItem {
  kind: string;
  tone: "critical" | "warning" | "neutral";
  subject: string;
  detail: string;
  age_days: number;
  occurred_at: string;
  entity_id: string;
}

export function useAttentionItems(limit = 8) {
  return useQuery({
    queryKey: ["attention", limit],
    queryFn: async () =>
      unwrap(
        await supabase
          .from("v_attention")
          .select("*")
          .eq("business_id", BUSINESS_ID)
          .order("age_days", { ascending: false })
          .limit(limit),
      ) as AttentionItem[],
    staleTime: 30_000,
  });
}

export interface AiDecision {
  id: string;
  event_type: string;
  status: "success" | "failure" | "blocked" | "pending";
  summary: string;
  confidence: number | null;
  tool_name: string | null;
  duration_ms: number | null;
  created_at: string;
}

export function useActivityFeed(limit = 40) {
  return useQuery({
    queryKey: ["ai-decisions", limit],
    queryFn: async () =>
      unwrap(
        await supabase
          .from("ai_decisions")
          .select("id,event_type,status,summary,confidence,tool_name,duration_ms,created_at")
          .eq("business_id", BUSINESS_ID)
          .order("created_at", { ascending: false })
          .limit(limit),
      ) as AiDecision[],
    staleTime: 5_000,
  });
}

/**
 * Push new AI decisions into the cache as Postgres commits them.
 *
 * This is what makes a decision appear on screen while the customer is still
 * speaking. Realtime enforces the same RLS policies as a direct read, so the
 * subscription cannot leak rows a plain query would have hidden.
 */
export function useActivityFeedRealtime() {
  const qc = useQueryClient();

  useEffect(() => {
    const channel = supabase
      .channel("ai-decisions-live")
      .on(
        "postgres_changes",
        {
          event: "INSERT",
          schema: "public",
          table: "ai_decisions",
          filter: `business_id=eq.${BUSINESS_ID}`,
        },
        () => {
          qc.invalidateQueries({ queryKey: ["ai-decisions"] });
          qc.invalidateQueries({ queryKey: ["dashboard-metrics"] });
        },
      )
      .subscribe();

    return () => {
      void supabase.removeChannel(channel);
    };
  }, [qc]);
}

export interface UpcomingAppointment {
  id: string;
  starts_at: string;
  status: string;
  source: string;
  customers: { full_name: string } | null;
  services: { name: string } | null;
  technicians: { full_name: string } | null;
}

export function useUpcomingAppointments(limit = 8) {
  return useQuery({
    queryKey: ["upcoming-appointments", limit],
    queryFn: async () =>
      unwrap(
        await supabase
          .from("appointments")
          .select(
            "id,starts_at,status,source,customers(full_name),services(name),technicians(full_name)",
          )
          .eq("business_id", BUSINESS_ID)
          .eq("status", "booked")
          .gt("starts_at", new Date().toISOString())
          .order("starts_at", { ascending: true })
          .limit(limit),
      ) as unknown as UpcomingAppointment[],
    staleTime: 30_000,
  });
}
