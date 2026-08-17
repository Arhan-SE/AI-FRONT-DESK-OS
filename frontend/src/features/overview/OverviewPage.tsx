import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { Page } from "@/components/AppShell";
import { ChartFrame, TrendArea, TrendBars, MagnitudeBars } from "@/components/charts";
import { useDailyActivity, useUsageSummary } from "@/lib/pageQueries";
import { api } from "@/lib/api";

const usd = (n: number) =>
  n >= 1 ? `$${n.toFixed(2)}` : n > 0 ? `$${n.toFixed(4)}` : "$0.00";

const compactTokens = (n: number) =>
  n >= 1_000_000 ? `${(n / 1_000_000).toFixed(2)}M`
  : n >= 1_000 ? `${(n / 1_000).toFixed(1)}K`
  : String(n);
import {
  MetricTile,
  Panel,
  PanelHeader,
  Table,
  Th,
  Td,
  Tr,
  StatusDot,
  StatusLabel,
  EmptyState,
  ErrorState,
  TableSkeleton,
  Tag,
  type Tone,
} from "@/components/ui/primitives";
import {
  useDashboardMetrics,
  useAttentionItems,
  useActivityFeed,
  useActivityFeedRealtime,
  useUpcomingAppointments,
} from "@/lib/queries";
import {
  formatCurrencyCompact,
  formatCurrency,
  formatNumber,
  formatClock,
  formatDateTime,
  formatRelative,
} from "@/lib/format";
import { CheckCircle2, Radio } from "lucide-react";

/** Pipeline counts come from the same endpoint the Jobs board uses. */
const useJobsForPipeline = () =>
  useQuery({ queryKey: ["jobs"], queryFn: api.listJobs, refetchInterval: 20_000 });

const kindLabel: Record<string, string> = {
  overdue_payment: "Payment",
  hot_lead: "Lead",
  human_task: "Task",
};

export function OverviewPage() {
  // Subscribe before rendering so nothing that lands mid-paint is missed.
  useActivityFeedRealtime();

  const metrics = useDashboardMetrics();
  const attention = useAttentionItems();
  const activity = useActivityFeed(25);
  const upcoming = useUpcomingAppointments();
  const daily = useDailyActivity();
  const jobs = useJobsForPipeline();
  const usage = useUsageSummary();

  const m = metrics.data;

  const chart = useMemo(
    () =>
      (daily.data ?? []).map((d) => ({
        label: new Date(d.day).toLocaleDateString("en-IN", { day: "2-digit", month: "short" }),
        jobs: d.jobs,
        collected: Number(d.collected),
      })),
    [daily.data],
  );

  // Stage counts straight from the jobs board, so the two never disagree.
  const pipeline = useMemo(() => {
    const rows = jobs.data ?? [];
    const count = (stage: string) => rows.filter((j) => j.stage === stage).length;
    return [
      { label: "Scheduled", value: count("scheduled") },
      { label: "Confirmed", value: count("confirmed") },
      { label: "In progress", value: count("in_progress") },
      { label: "Completed", value: count("completed") },
      { label: "Invoiced", value: count("invoice_sent") },
      { label: "Overdue", value: count("overdue"), tone: "critical" as const },
      { label: "Paid", value: count("paid"), tone: "success" as const },
    ];
  }, [jobs.data]);

  return (
    <Page title="Overview">
      {metrics.isError ? (
        <Panel className="mb-6">
          <ErrorState
            description="The dashboard metrics could not be loaded. This is usually a connection problem."
            onRetry={() => void metrics.refetch()}
          />
        </Panel>
      ) : (
        <div className="mb-6 grid grid-cols-2 gap-3 lg:grid-cols-3 xl:grid-cols-6">
          <MetricTile
            label="Open leads"
            value={formatNumber(m?.open_leads)}
            hint={m ? `${m.hot_leads} hot` : undefined}
            tone={m && m.hot_leads > 0 ? "warning" : "neutral"}
            loading={metrics.isPending}
          />
          <MetricTile
            label="Upcoming jobs"
            value={formatNumber(m?.upcoming_appointments)}
            hint="scheduled ahead"
            loading={metrics.isPending}
          />
          <MetricTile
            label="Jobs this month"
            value={formatNumber(m?.jobs_this_month)}
            hint="completed"
            loading={metrics.isPending}
          />
          <MetricTile
            label="Outstanding"
            value={formatCurrencyCompact(m?.outstanding_amount)}
            hint={m ? `${m.overdue_invoices} overdue` : undefined}
            tone={m && m.overdue_invoices > 0 ? "critical" : "neutral"}
            loading={metrics.isPending}
          />
          <MetricTile
            label="Avg rating"
            value={m?.avg_rating ?? "—"}
            hint={m ? `${m.reviews_collected} reviews` : undefined}
            loading={metrics.isPending}
          />
          <MetricTile
            label="Reactivation"
            value={formatNumber(m?.dormant_customers)}
            hint={m ? `${formatCurrencyCompact(m.dormant_value)} lapsed` : undefined}
            loading={metrics.isPending}
          />
        </div>
      )}

      {/* --------------------------------------------------------- trends */}
      <div className="mb-6 grid gap-3 lg:grid-cols-3">
        <ChartFrame title="Jobs" hint="last 14 days" empty={!chart.some((d) => d.jobs > 0)}>
          <TrendBars data={chart} dataKey="jobs" />
        </ChartFrame>
        <ChartFrame title="Collected" hint="last 14 days"
          empty={!chart.some((d) => d.collected > 0)}>
          <TrendArea data={chart} dataKey="collected" format={(v) => formatCurrency(v)} />
        </ChartFrame>
        <Panel>
          <PanelHeader title="Pipeline" description="Where work is right now" />
          <div className="py-3">
            <MagnitudeBars rows={pipeline} />
          </div>
        </Panel>
      </div>

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)]">
        {/* ------------------------------------------------------- attention */}
        <Panel>
          <PanelHeader
            title="Needs attention"
            description="Only items where someone has to act"
          />
          {attention.isPending ? (
            <TableSkeleton rows={5} cols={3} />
          ) : attention.isError ? (
            <ErrorState onRetry={() => void attention.refetch()} />
          ) : !attention.data?.length ? (
            <EmptyState
              icon={CheckCircle2}
              title="Nothing needs attention"
              description="No overdue payments, unworked hot leads, or open escalations."
            />
          ) : (
            <Table>
              <thead>
                <tr>
                  <Th>Customer</Th>
                  <Th>Item</Th>
                  <Th align="right">Age</Th>
                </tr>
              </thead>
              <tbody>
                {attention.data.map((item) => (
                  <Tr key={`${item.kind}-${item.entity_id}`}>
                    <Td>
                      <span className="flex items-center gap-2">
                        <StatusDot tone={item.tone as Tone} />
                        <span className="font-medium">{item.subject}</span>
                      </span>
                    </Td>
                    <Td className="text-ink-muted">
                      <span className="flex items-center gap-2">
                        <Tag>{kindLabel[item.kind] ?? item.kind}</Tag>
                        <span className="truncate">{item.detail}</span>
                      </span>
                    </Td>
                    <Td align="right" className="font-mono text-ink-subtle">
                      {item.age_days}d
                    </Td>
                  </Tr>
                ))}
              </tbody>
            </Table>
          )}
        </Panel>

        {/* -------------------------------------------------------- activity */}
        <Panel>
          <PanelHeader
            title="AI activity"
            description="Decisions as they happen"
            action={
              <span className="flex items-center gap-1.5">
                <Radio className="size-3.5 text-success" strokeWidth={2} />
                <span className="t-meta">live</span>
              </span>
            }
          />
          {activity.isPending ? (
            <TableSkeleton rows={5} cols={2} />
          ) : activity.isError ? (
            <ErrorState onRetry={() => void activity.refetch()} />
          ) : !activity.data?.length ? (
            <EmptyState
              icon={Radio}
              title="No AI activity yet"
              description="Decisions appear here in real time once a conversation starts."
            />
          ) : (
            <ul className="divide-y divide-line">
              {activity.data.map((e) => (
                <li key={e.id} className="flex items-baseline gap-3 px-4 py-2.5">
                  <span className="t-meta shrink-0">{formatClock(e.created_at)}</span>
                  <StatusDot
                    tone={
                      e.status === "failure"
                        ? "critical"
                        : e.status === "blocked"
                          ? "warning"
                          : "success"
                    }
                    className="translate-y-[3px]"
                  />
                  <span className="min-w-0 flex-1 t-cell">{e.summary}</span>
                  {e.confidence != null ? (
                    <span className="t-meta shrink-0">
                      {(e.confidence * 100).toFixed(0)}%
                    </span>
                  ) : null}
                </li>
              ))}
            </ul>
          )}
        </Panel>
      </div>

      {/* ------------------------------------------------------- next up */}
      <Panel className="mt-6">
        <PanelHeader title="Next appointments" description="Confirmed and upcoming" />
        {upcoming.isPending ? (
          <TableSkeleton rows={5} cols={5} />
        ) : upcoming.isError ? (
          <ErrorState onRetry={() => void upcoming.refetch()} />
        ) : !upcoming.data?.length ? (
          <EmptyState title="No upcoming appointments" />
        ) : (
          <Table>
            <thead>
              <tr>
                <Th>When</Th>
                <Th>Customer</Th>
                <Th>Service</Th>
                <Th>Technician</Th>
                <Th>Booked via</Th>
                <Th align="right">Starts</Th>
              </tr>
            </thead>
            <tbody>
              {upcoming.data.map((a) => (
                <Tr key={a.id}>
                  <Td className="font-medium">{formatDateTime(a.starts_at)}</Td>
                  <Td>{a.customers?.full_name ?? "—"}</Td>
                  <Td className="text-ink-muted">{a.services?.name ?? "—"}</Td>
                  <Td className="text-ink-muted">{a.technicians?.full_name ?? "—"}</Td>
                  <Td>
                    <StatusLabel tone={a.source === "voice" ? "success" : "neutral"}>
                      {a.source === "voice" ? "AI voice" : a.source}
                    </StatusLabel>
                  </Td>
                  <Td align="right" className="text-ink-subtle">
                    {formatRelative(a.starts_at)}
                  </Td>
                </Tr>
              ))}
            </tbody>
          </Table>
        )}
      </Panel>

      {/* AI cost and usage. Lives here rather than on its own page: the
          decision feed above already covers what the AI did, and this is the
          only part that was not shown anywhere else. */}
      <Panel className="mt-6">
        <PanelHeader
          title="AI usage"
          description="Metered from every call and generated message"
        />
        <div className="grid grid-cols-2 divide-x divide-line lg:grid-cols-5">
          {[
            { label: "Voice calls", value: formatNumber(usage.data?.total_calls) },
            {
              label: "Voice minutes",
              value: usage.data ? Number(usage.data.voice_minutes).toFixed(1) : "—",
            },
            {
              label: "Tokens",
              value: usage.data ? compactTokens(Number(usage.data.total_tokens)) : "—",
            },
            {
              label: "Decisions",
              value: formatNumber(usage.data?.total_decisions),
            },
            {
              label: "Cost",
              value: usage.data ? usd(Number(usage.data.total_cost_usd)) : "—",
              hint: "at configured rates",
            },
          ].map((tile) => (
            <div key={tile.label} className="px-4 py-3">
              <div className="t-label">{tile.label}</div>
              <div className="mt-1 text-[22px] font-semibold leading-tight">{tile.value}</div>
              {tile.hint ? <div className="t-meta mt-0.5">{tile.hint}</div> : null}
            </div>
          ))}
        </div>
      </Panel>

      {m ? (
        <p className="t-meta mt-6">
          {formatNumber(m.total_customers)} customers · {formatCurrency(m.overdue_amount)} overdue ·{" "}
          {m.reviews_awaiting} review requests awaiting reply
        </p>
      ) : null}
    </Page>
  );
}
