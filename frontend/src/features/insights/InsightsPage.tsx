/**
 * Insights — what the owner should look at this morning.
 *
 * Every figure on this page is computed in SQL. The model ranks them, explains
 * the consequence, and names the next step; it never produces a number. That
 * split is why an insight here can be trusted enough to act on.
 */

import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  Panel, EmptyState, ErrorState, Skeleton, StatusDot,
} from "@/components/ui/primitives";
import { Button } from "@/components/ui/controls";
import { Page } from "@/components/AppShell";
import { api, type Insight } from "@/lib/api";
import { cn } from "@/lib/cn";
import { Lightbulb, RefreshCw, ArrowRight, Circle } from "lucide-react";

const SEVERITY: Record<string, { tone: "critical" | "warning" | "neutral"; label: string }> = {
  urgent: { tone: "critical", label: "Needs attention" },
  watch: { tone: "warning", label: "Worth watching" },
  opportunity: { tone: "neutral", label: "Opportunity" },
};

export function InsightsPage() {
  const insights = useQuery({
    queryKey: ["insights"],
    queryFn: api.insights,
    staleTime: 5 * 60_000,
    refetchOnWindowFocus: false,
  });

  const data = insights.data;
  const urgent = data?.insights.filter((i) => i.severity === "urgent").length ?? 0;

  return (
    <Page
      title="Insights"
      description="The business, read every morning and ranked by what it costs you to ignore"
      action={
        <Button
          onClick={() => void insights.refetch()}
          disabled={insights.isFetching}
        >
          <RefreshCw
            className={cn("size-3.5", insights.isFetching && "animate-spin")}
            strokeWidth={2}
          />
          {insights.isFetching ? "Analysing…" : "Re-analyse"}
        </Button>
      }
    >
      {insights.isPending ? (
        <LoadingCards />
      ) : insights.isError ? (
        <ErrorState onRetry={() => void insights.refetch()} />
      ) : !data || data.insights.length === 0 ? (
        <Panel>
          <EmptyState
            icon={Lightbulb}
            title="Nothing to report yet"
            description={
              data?.error ??
              "Once there are jobs, invoices and customers to read, the analysis appears here."
            }
          />
        </Panel>
      ) : (
        <div className="space-y-5">
          {data.error ? (
            <p className="rounded-[6px] border border-line bg-surface px-3 py-2 text-[12px] text-ink-muted">
              {data.error}
            </p>
          ) : null}

          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[12px] text-ink-muted">
            <span className="flex items-center gap-1.5">
              <StatusDot tone={urgent > 0 ? "critical" : "success"} />
              {urgent > 0
                ? `${urgent} needing attention`
                : "Nothing urgent"}
            </span>
            <span>·</span>
            <span>{Object.keys(data.facts).length} areas analysed</span>
            <span>·</span>
            <span className="tabular-nums">{(data.generated_ms / 1000).toFixed(1)}s</span>
          </div>

          <div className="space-y-3">
            {data.insights.map((insight, i) => (
              <InsightCard key={i} insight={insight} rank={i + 1} />
            ))}
          </div>

          <p className="text-[11px] leading-relaxed text-ink-subtle">
            Every figure above is computed directly from your data. The analysis
            ranks and explains them — it does not produce numbers of its own.
          </p>
        </div>
      )}
    </Page>
  );
}

function InsightCard({ insight, rank }: { insight: Insight; rank: number }) {
  const severity = SEVERITY[insight.severity] ?? SEVERITY.watch;

  return (
    <Panel>
      <div className="flex flex-col gap-4 p-4 sm:flex-row sm:items-start">
        {/* Rank is real information here: the list is ordered by cost of
            ignoring it, so position carries meaning. */}
        <div className="flex shrink-0 items-center gap-3 sm:w-[92px] sm:flex-col sm:items-start sm:gap-1">
          <span className="font-mono text-[11px] text-ink-subtle tabular-nums">
            {String(rank).padStart(2, "0")}
          </span>
          <span className="flex items-center gap-1.5 whitespace-nowrap text-[11px] text-ink-muted">
            <Circle
              className={cn(
                "size-2 shrink-0",
                severity.tone === "critical" && "fill-critical text-critical",
                severity.tone === "warning" && "fill-warning text-warning",
                severity.tone === "neutral" && "fill-ink-subtle text-ink-subtle",
              )}
            />
            {severity.label}
          </span>
        </div>

        <div className="min-w-0 flex-1 space-y-2">
          <h3 className="text-[15px] font-semibold leading-snug text-ink">
            {insight.title}
          </h3>
          <p className="text-[13px] leading-relaxed text-ink">{insight.finding}</p>
          {insight.why ? (
            <p className="text-[13px] leading-relaxed text-ink-muted">{insight.why}</p>
          ) : null}

          {insight.recommendation ? (
            <div className="flex items-start gap-2 border-l-2 border-line-strong pl-3 pt-1">
              <p className="text-[13px] leading-relaxed text-ink">
                <span className="text-ink-muted">Do this — </span>
                {insight.recommendation}
              </p>
            </div>
          ) : null}

          {insight.action ? (
            <Link
              to={insight.action.to}
              className={cn(
                "inline-flex items-center gap-1.5 pt-1 text-[12px] font-medium text-ink",
                "underline-offset-4 transition-colors duration-150 hover:underline",
              )}
            >
              {insight.action.label}
              <ArrowRight className="size-3.5" strokeWidth={2} />
            </Link>
          ) : null}
        </div>

        {insight.metric ? (
          <div className="shrink-0 text-left sm:w-[140px] sm:text-right">
            <div className="text-[24px] font-semibold leading-none text-ink tabular-nums">
              {insight.metric}
            </div>
            {insight.metric_label ? (
              <div className="pt-1 text-[11px] leading-tight text-ink-muted">
                {insight.metric_label}
              </div>
            ) : null}
          </div>
        ) : null}
      </div>
    </Panel>
  );
}

function LoadingCards() {
  return (
    <div className="space-y-3">
      <p className="text-[12px] text-ink-muted">Reading your business…</p>
      {[0, 1, 2, 3].map((i) => (
        <Panel key={i}>
          <div className="space-y-2.5 p-4">
            <Skeleton className="h-4 w-1/3" />
            <Skeleton className="h-3 w-full" />
            <Skeleton className="h-3 w-4/5" />
          </div>
        </Panel>
      ))}
    </div>
  );
}
