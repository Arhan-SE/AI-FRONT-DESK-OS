/**
 * The write path.
 *
 * Reads go straight to Supabase under RLS; anything that changes state comes
 * through FastAPI, which holds the service-role key and the business rules.
 */

const BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, {
      headers: { "Content-Type": "application/json" },
      ...init,
    });
  } catch {
    // A dead backend must read as a clear sentence, not "Failed to fetch".
    throw new ApiError("Cannot reach the server. Is the API running?", 0);
  }

  if (!res.ok) {
    let detail = `Request failed (${res.status})`;
    try {
      const body = await res.json();
      if (typeof body?.detail === "string") detail = body.detail;
    } catch {
      /* non-JSON error body — keep the generic message */
    }
    throw new ApiError(detail, res.status);
  }

  return res.status === 204 ? (undefined as T) : ((await res.json()) as T);
}

export type Stage =
  | "scheduled"
  | "confirmed"
  | "in_progress"
  | "completed"
  | "invoice_sent"
  | "paid"
  | "overdue"
  | "cancelled"
  | "no_show";

export type Action =
  | "confirm"
  | "start"
  | "complete"
  | "send_invoice"
  | "mark_paid"
  | "cancel"
  | "no_show";

export interface Job {
  id: string;
  stage: Stage;
  customer_name: string;
  service_name: string;
  technician_name: string;
  starts_at: string;
  customer_reachable: boolean;
  invoice_number: string | null;
  invoice_amount: number | null;
  due_on: string | null;
}

export interface JobOptions {
  customers: { id: string; name: string; phone: string; reachable: boolean }[];
  services: { id: string; name: string; duration_minutes: number; price: number }[];
  technicians: { id: string; name: string }[];
}

export interface TransitionResult {
  job_id: string;
  action: string;
  stage: string;
  enqueued: string[];
  cancelled_jobs: number;
}

export interface QueueItem {
  id: string;
  job_type: string;
  status: string;
  scheduled_for: string;
  attempts: number;
  last_error: string | null;
}

export interface CustomerPatch {
  full_name: string;
  phone: string | null;
  email: string | null;
  address: string | null;
  telegram_chat_id: number | null;
  do_not_contact: boolean;
  status: string;
}

export type CampaignType = "reactivation" | "seasonal" | "review_request";

export interface CampaignCandidate {
  customer_id: string;
  name: string;
  eligible: boolean;
  reason: string | null;
  code: string | null;
  days_since: number;
}

export interface CampaignPreview {
  campaign_type: string;
  total: number;
  eligible: number;
  blocked: number;
  candidates: CampaignCandidate[];
}

export const api = {
  health: () => request<Record<string, unknown>>("/health"),

  listJobs: () => request<Job[]>("/api/jobs"),

  jobOptions: () => request<JobOptions>("/api/jobs/options"),

  createJob: (body: {
    customer_id: string;
    service_id: string;
    technician_id: string;
    starts_at: string;
    notes?: string;
    idempotency_key?: string;
  }) =>
    request<TransitionResult>("/api/jobs", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  transition: (jobId: string, action: Action) =>
    request<TransitionResult>(`/api/jobs/${jobId}/transition`, {
      method: "POST",
      body: JSON.stringify({ action }),
    }),

  queue: () => request<QueueItem[]>("/api/automation/queue"),

  updateCustomer: (id: string, body: Partial<CustomerPatch>) =>
    request<{ id: string; full_name: string; reachable: boolean }>(
      `/api/customers/${id}`,
      { method: "PATCH", body: JSON.stringify(body) },
    ),

  createCustomer: (body: CustomerPatch) =>
    request<{ id: string; full_name: string }>("/api/customers", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  campaignPreview: (campaignType: CampaignType, lapsedDays = 90) =>
    request<CampaignPreview>(
      `/api/campaigns/preview?campaign_type=${campaignType}&lapsed_days=${lapsedDays}`,
    ),

  launchCampaign: (body: {
    name: string;
    campaign_type: CampaignType;
    customer_ids: string[];
  }) =>
    request<{ campaign_id: string; queued: number }>("/api/campaigns", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  runDue: () =>
    request<{ advanced: number; executed: number }>("/api/automation/run-due", {
      method: "POST",
    }),
};
