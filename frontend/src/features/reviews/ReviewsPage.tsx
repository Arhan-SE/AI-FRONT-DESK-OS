import { Page } from "@/components/AppShell";
import {
  Panel, PanelHeader, MetricTile, Table, Th, Td, Tr,
  EmptyState, ErrorState, TableSkeleton,
} from "@/components/ui/primitives";
import { useReviews } from "@/lib/pageQueries";
import { formatRelative } from "@/lib/format";
import { Star } from "lucide-react";

function Stars({ rating }: { rating: number }) {
  return (
    <span className="flex items-center gap-0.5" aria-label={`${rating} out of 5`}>
      {[1, 2, 3, 4, 5].map((n) => (
        <Star
          key={n}
          className={n <= rating ? "size-3.5 fill-ink text-ink" : "size-3.5 text-line-strong"}
          strokeWidth={1.5}
        />
      ))}
    </span>
  );
}

export function ReviewsPage() {
  const reviews = useReviews();
  const all = reviews.data ?? [];

  const answered = all.filter((r) => r.submitted_at !== null);
  const awaiting = all.filter((r) => r.submitted_at === null && r.requested_at !== null);
  const avg = answered.length
    ? (answered.reduce((t, r) => t + (r.rating ?? 0), 0) / answered.length).toFixed(2)
    : "—";
  const rate = all.length ? Math.round((answered.length / all.length) * 100) : 0;

  return (
    <Page title="Reviews">
      <div className="mb-5 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <MetricTile label="Average rating" value={avg}
          hint={`${answered.length} answered`} loading={reviews.isPending} />
        <MetricTile label="Requests sent" value={all.length} loading={reviews.isPending} />
        <MetricTile label="Awaiting reply" value={awaiting.length}
          tone={awaiting.length ? "warning" : "neutral"} loading={reviews.isPending} />
        <MetricTile label="Response rate" value={all.length ? `${rate}%` : "—"}
          hint="answered / requested" loading={reviews.isPending} />
      </div>

      <Panel>
        <PanelHeader
          title="Review requests"
          description="Sent automatically 24 hours after a job is completed"
        />
        {reviews.isPending ? (
          <TableSkeleton rows={5} cols={4} />
        ) : reviews.isError ? (
          <ErrorState onRetry={() => void reviews.refetch()} />
        ) : all.length === 0 ? (
          <EmptyState
            icon={Star}
            title="No review requests yet"
            description="Complete a job and one is queued automatically."
          />
        ) : (
          <Table>
            <thead>
              <tr>
                <Th>Customer</Th><Th>Rating</Th><Th>Comment</Th>
                <Th>Requested</Th><Th align="right">Answered</Th>
              </tr>
            </thead>
            <tbody>
              {all.map((r) => (
                <Tr key={r.id}>
                  <Td className="font-medium">{r.customers?.full_name ?? "—"}</Td>
                  <Td>{r.rating ? <Stars rating={r.rating} /> : <span className="t-meta">awaiting</span>}</Td>
                  <Td className="max-w-[380px] truncate text-ink-muted">{r.comment ?? "—"}</Td>
                  <Td className="text-ink-subtle">{formatRelative(r.requested_at)}</Td>
                  <Td align="right" className="text-ink-subtle">
                    {r.submitted_at ? formatRelative(r.submitted_at) : "—"}
                  </Td>
                </Tr>
              ))}
            </tbody>
          </Table>
        )}
      </Panel>
    </Page>
  );
}
