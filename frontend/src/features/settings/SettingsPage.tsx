import { useQuery } from "@tanstack/react-query";
import { Page } from "@/components/AppShell";
import {
  Panel, PanelHeader, StatusDot, ErrorState, TableSkeleton, type Tone,
} from "@/components/ui/primitives";
import { api } from "@/lib/api";
import { useCustomers } from "@/lib/pageQueries";

interface Health {
  database: { postgres: string; customers: number; appointments: number };
  telegram_configured: boolean;
  ai_configured: boolean;
  timezone: string;
  livekit_url: string;
  models: { voice: string; reasoning: string };
  rates_usd_per_million: Record<string, number>;
  policy: Record<string, string | number>;
}

const LABEL: Record<string, string> = {
  slot_hold_seconds: "Offered slots held for",
  min_booking_lead_minutes: "Earliest bookable slot",
  followup_delay_hours: "Follow-up after a job",
  review_delay_hours: "Review request after a job",
  invoice_due_days: "Invoice payment terms",
  marketing_cooldown_days: "Marketing cooldown",
  quiet_hours: "Quiet hours",
};

const UNIT: Record<string, string> = {
  slot_hold_seconds: "seconds",
  min_booking_lead_minutes: "minutes from now",
  followup_delay_hours: "hours",
  review_delay_hours: "hours",
  invoice_due_days: "days",
  marketing_cooldown_days: "days",
};

const RATE_LABEL: Record<string, string> = {
  reasoning_input: "Reasoning · input",
  reasoning_output: "Reasoning · output",
  realtime_audio_input: "Voice audio · input",
  realtime_audio_output: "Voice audio · output",
};

export function SettingsPage() {
  const health = useQuery({
    queryKey: ["health"],
    queryFn: () => api.health() as Promise<unknown> as Promise<Health>,
    refetchInterval: 15_000,
    retry: 0,
  });
  const customers = useCustomers();

  const h = health.data;
  const reachable = (customers.data ?? []).filter((c) => c.reachable).length;
  const total = customers.data?.length ?? 0;

  const checks: { label: string; ok: boolean; detail: string; tone: Tone }[] = h
    ? [
        {
          label: "Database",
          ok: true,
          detail: `PostgreSQL ${h.database.postgres} · ${h.database.customers} customers, ${h.database.appointments} jobs`,
          tone: "success",
        },
        {
          label: "AI provider",
          ok: h.ai_configured,
          detail: h.ai_configured
            ? `${h.models.voice} for voice, ${h.models.reasoning} for decisions`
            : "No OpenAI key configured — voice and generated copy are unavailable",
          tone: h.ai_configured ? "success" : "critical",
        },
        {
          label: "Voice transport",
          ok: true,
          detail: `LiveKit at ${h.livekit_url} — self-hosted, media never leaves this machine`,
          tone: "success",
        },
        {
          label: "Messaging",
          ok: h.telegram_configured,
          detail: h.telegram_configured
            ? `Telegram connected · ${reachable} of ${total} customers linked`
            : "No Telegram bot token — the Guard will block every outbound message",
          tone: h.telegram_configured ? "success" : "warning",
        },
      ]
    : [];

  return (
    <Page title="Settings">
      <Panel className="mb-6">
        <PanelHeader
          title="System status"
          description="What is configured, and what is not"
        />
        {health.isPending ? (
          <TableSkeleton rows={4} cols={2} />
        ) : health.isError ? (
          <ErrorState
            title="Cannot reach the API"
            description="The dashboard reads from Supabase directly, so pages still load — but nothing can be changed until the API is running on port 8000."
            onRetry={() => void health.refetch()}
          />
        ) : (
          <ul className="divide-y divide-line">
            {checks.map((c) => (
              <li key={c.label} className="flex items-start gap-3 px-4 py-3">
                <StatusDot tone={c.tone} className="mt-[7px]" />
                <span className="min-w-0">
                  <span className="block text-[13.5px] font-medium">{c.label}</span>
                  <span className="t-meta">{c.detail}</span>
                </span>
              </li>
            ))}
          </ul>
        )}
      </Panel>

      <div className="grid gap-6 lg:grid-cols-2">
        <Panel>
          <PanelHeader
            title="Business rules"
            description="How the system decides timing"
          />
          {h ? (
            <ul className="divide-y divide-line">
              {Object.entries(h.policy).map(([key, value]) => (
                <li key={key} className="flex items-baseline justify-between gap-4 px-4 py-2.5">
                  <span className="t-cell text-ink-muted">{LABEL[key] ?? key}</span>
                  <span className="shrink-0 text-[13px] font-medium tabular-nums">
                    {value}
                    {UNIT[key] ? <span className="t-meta ml-1.5">{UNIT[key]}</span> : null}
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <TableSkeleton rows={5} cols={2} />
          )}
        </Panel>

        <Panel>
          <PanelHeader
            title="Model rates"
            description="USD per million tokens"
          />
          {h ? (
            <>
              <ul className="divide-y divide-line">
                {Object.entries(h.rates_usd_per_million).map(([key, value]) => (
                  <li key={key} className="flex items-baseline justify-between gap-4 px-4 py-2.5">
                    <span className="t-cell text-ink-muted">{RATE_LABEL[key] ?? key}</span>
                    <span className="shrink-0 text-[13px] font-medium tabular-nums">
                      ${Number(value).toFixed(2)}
                    </span>
                  </li>
                ))}
              </ul>
              {/* The cost figures on Overview are arithmetic over these. Saying
                  so here is the difference between a number and a claim. */}
              <p className="t-meta border-t border-line px-4 py-3">
                Every cost shown in this product is calculated from these rates,
                not billed by the provider. Verify them against current pricing
                before quoting a figure. Edit in{" "}
                <span className="font-mono">backend/src/genesis/settings.py</span>.
              </p>
            </>
          ) : (
            <TableSkeleton rows={4} cols={2} />
          )}
        </Panel>
      </div>

      <Panel className="mt-6">
        <PanelHeader title="Demo tenant" />
        <div className="grid gap-x-8 gap-y-2 px-4 py-4 sm:grid-cols-2">
          {[
            ["Business", "Apex Climate Care"],
            ["Trade", "Air conditioning · Bengaluru"],
            ["Timezone", h?.timezone ?? "—"],
            ["Customers", `${total} real, ${reachable} contactable`],
          ].map(([k, v]) => (
            <div key={k} className="flex items-baseline justify-between gap-4 border-b border-line pb-2">
              <span className="t-label">{k}</span>
              <span className="text-[13px] font-medium">{v}</span>
            </div>
          ))}
        </div>
      </Panel>
    </Page>
  );
}
