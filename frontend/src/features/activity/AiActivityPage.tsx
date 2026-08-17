import { useMemo, useState } from "react";
import { Page } from "@/components/AppShell";
import {
  Panel, PanelHeader, MetricTile, Table, Th, Td, Tr, StatusDot, Tag,
  EmptyState, ErrorState, TableSkeleton,
} from "@/components/ui/primitives";
import { Button } from "@/components/ui/controls";
import { ChartFrame, TrendArea } from "@/components/charts";
import {
  useUsageSummary, useUsageEvents, useDailyActivity,
} from "@/lib/pageQueries";
import { useActivityFeed, useActivityFeedRealtime } from "@/lib/queries";
import { formatClock, formatNumber, formatRelative } from "@/lib/format";
import { Radio, Activity, CircleDollarSign } from "lucide-react";

const usd = (n: number) =>
  n >= 1 ? `$${n.toFixed(2)}` : n > 0 ? `$${n.toFixed(4)}` : "$0.00";

const compactTokens = (n: number) =>
  n >= 1_000_000 ? `${(n / 1_000_000).toFixed(2)}M`
  : n >= 1_000 ? `${(n / 1_000).toFixed(1)}K`
  : String(n);

type Filter = "all" | "success" | "blocked" | "failure";

export function AiActivityPage() {
  useActivityFeedRealtime();

  const usage = useUsageSummary();
  const events = useUsageEvents(30);
  const daily = useDailyActivity();
  const feed = useActivityFeed(120);
  const [filter, setFilter] = useState<Filter>("all");

  const u = usage.data;

  const series = useMemo(
    () =>
      (daily.data ?? []).map((d) => ({
        label: new Date(d.day).toLocaleDateString("en-IN", { day: "2-digit", month: "short" }),
        decisions: d.decisions,
      })),
    [daily.data],
  );

  const visible = (feed.data ?? []).filter(
    (e) => filter === "all" || e.status === filter,
  );

  const counts = {
    all: feed.data?.length ?? 0,
    success: feed.data?.filter((e) => e.status === "success").length ?? 0,
    blocked: feed.data?.filter((e) => e.status === "blocked").length ?? 0,
    failure: feed.data?.filter((e) => e.status === "failure").length ?? 0,
  };

  return (
    <Page title="AI Activity">
      {/* ------------------------------------------------------- usage */}
      <div className="mb-5 grid grid-cols-2 gap-3 lg:grid-cols-3 xl:grid-cols-6">
        <MetricTile label="Voice calls" value={formatNumber(u?.total_calls)}
          loading={usage.isPending} />
        <MetricTile label="Voice minutes"
          value={u ? Number(u.voice_minutes).toFixed(1) : "—"}
          hint="realtime audio" loading={usage.isPending} />
        <MetricTile label="Tokens"
          value={u ? compactTokens(Number(u.total_tokens)) : "—"}
          hint={u ? `${compactTokens(Number(u.audio_tokens))} audio` : undefined}
          loading={usage.isPending} />
        <MetricTile label="Total cost"
          value={u ? usd(Number(u.total_cost_usd)) : "—"}
          hint="at configured rates" loading={usage.isPending} />
        <MetricTile label="Decisions" value={formatNumber(u?.total_decisions)}
          loading={usage.isPending} />
        <MetricTile label="Blocked" value={formatNumber(u?.blocked_decisions)}
          hint="Guard refusals" tone={u && u.blocked_decisions > 0 ? "warning" : "neutral"}
          loading={usage.isPending} />
      </div>

      <div className="mb-6 grid gap-3 lg:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
        <ChartFrame
          title="AI decisions"
          hint="last 14 days"
          empty={!series.some((s) => s.decisions > 0)}
        >
          <TrendArea data={series} dataKey="decisions" />
        </ChartFrame>

        <Panel>
          <PanelHeader title="Where the money goes" />
          {!u || Number(u.total_cost_usd) === 0 ? (
            <EmptyState icon={CircleDollarSign} title="Nothing spent yet"
              description="Make a call and the breakdown appears here." />
          ) : (
            <div className="space-y-3 px-4 py-4">
              {[
                { label: "Realtime voice", value: Number(u.voice_cost_usd) },
                { label: "Text reasoning", value: Number(u.text_cost_usd) },
              ].map((row) => {
                const pct = Number(u.total_cost_usd)
                  ? (row.value / Number(u.total_cost_usd)) * 100 : 0;
                return (
                  <div key={row.label}>
                    <div className="mb-1 flex items-baseline justify-between">
                      <span className="t-label">{row.label}</span>
                      <span className="text-[13px] font-medium tabular-nums">
                        {usd(row.value)}
                      </span>
                    </div>
                    <span className="block h-2 overflow-hidden rounded-[4px] bg-surface">
                      <span className="block h-full rounded-[4px] bg-ink"
                        style={{ width: `${Math.max(pct === 0 ? 0 : 3, pct)}%` }} />
                    </span>
                    <span className="t-meta">{pct.toFixed(0)}% of spend</span>
                  </div>
                );
              })}
              {/* Stated, not implied: this is arithmetic over a rate card,
                  not a bill from the provider. */}
              <p className="t-meta pt-1">
                Calculated from configured rates in settings — verify against
                current provider pricing before quoting.
              </p>
            </div>
          )}
        </Panel>
      </div>

      {/* ------------------------------------------------------- feed */}
      <Panel className="mb-6">
        <PanelHeader
          title="Decision log"
          description="Every observable action the system took"
          action={
            <span className="flex items-center gap-1">
              {(["all", "success", "blocked", "failure"] as Filter[]).map((f) => (
                <Button key={f} variant={filter === f ? "secondary" : "ghost"}
                  onClick={() => setFilter(f)}>
                  {f === "all" ? "All" : f[0].toUpperCase() + f.slice(1)} ({counts[f]})
                </Button>
              ))}
            </span>
          }
        />
        {feed.isPending ? (
          <TableSkeleton rows={6} cols={3} />
        ) : feed.isError ? (
          <ErrorState onRetry={() => void feed.refetch()} />
        ) : visible.length === 0 ? (
          <EmptyState icon={Radio} title="Nothing here"
            description={filter === "all"
              ? "Decisions stream in the moment they happen."
              : "No events with this status."} />
        ) : (
          <ul className="max-h-[420px] divide-y divide-line overflow-y-auto">
            {visible.map((e) => (
              <li key={e.id} className="flex items-baseline gap-3 px-4 py-2.5">
                <span className="t-meta w-[64px] shrink-0">{formatClock(e.created_at)}</span>
                <StatusDot
                  tone={e.status === "failure" ? "critical"
                      : e.status === "blocked" ? "warning" : "success"}
                  className="translate-y-[3px]"
                />
                <span className="min-w-0 flex-1 t-cell">{e.summary}</span>
                {e.tool_name ? <Tag>{e.tool_name}</Tag> : null}
                {e.confidence != null ? (
                  <span className="t-meta shrink-0">{(e.confidence * 100).toFixed(0)}%</span>
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </Panel>

      {/* ------------------------------------------------------ usage log */}
      <Panel>
        <PanelHeader title="Model usage" description="Per request, with cost at configured rates" />
        {events.isPending ? (
          <TableSkeleton rows={4} cols={5} />
        ) : !events.data?.length ? (
          <EmptyState icon={Activity} title="No model usage recorded"
            description="Voice calls and generated messages are metered here." />
        ) : (
          <Table>
            <thead>
              <tr>
                <Th>When</Th><Th>Model</Th><Th>Purpose</Th>
                <Th align="right">In</Th><Th align="right">Out</Th>
                <Th align="right">Seconds</Th><Th align="right">Cost</Th>
              </tr>
            </thead>
            <tbody>
              {events.data.map((e) => (
                <Tr key={e.id}>
                  <Td className="text-ink-subtle">{formatRelative(e.created_at)}</Td>
                  <Td className="font-mono text-[12px]">{e.model}</Td>
                  <Td><Tag>{e.purpose ?? e.source}</Tag></Td>
                  <Td align="right">
                    {formatNumber(e.input_text_tokens + e.input_audio_tokens)}
                    {e.input_audio_tokens > 0 ? (
                      <span className="t-meta ml-1">audio</span>
                    ) : null}
                  </Td>
                  <Td align="right">
                    {formatNumber(e.output_text_tokens + e.output_audio_tokens)}
                  </Td>
                  <Td align="right" className="text-ink-muted">
                    {Number(e.duration_seconds) > 0 ? Number(e.duration_seconds).toFixed(1) : "—"}
                  </Td>
                  <Td align="right" className="font-medium">{usd(Number(e.cost_usd))}</Td>
                </Tr>
              ))}
            </tbody>
          </Table>
        )}
      </Panel>
    </Page>
  );
}
