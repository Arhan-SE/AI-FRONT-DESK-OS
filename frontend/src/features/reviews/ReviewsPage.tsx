import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Page } from "@/components/AppShell";
import {
  Panel, PanelHeader, MetricTile, Table, Th, Td, Tr, StatusDot,
  EmptyState, ErrorState, TableSkeleton,
} from "@/components/ui/primitives";
import { Button, Dialog, InlineError } from "@/components/ui/controls";
import { useReviews } from "@/lib/pageQueries";
import { api, ApiError } from "@/lib/api";
import { formatRelative } from "@/lib/format";
import { Star, Send, ShieldCheck } from "lucide-react";

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
  const [outreachOpen, setOutreachOpen] = useState(false);
  const all = reviews.data ?? [];

  const answered = all.filter((r) => r.submitted_at !== null);
  const awaiting = all.filter((r) => r.submitted_at === null && r.requested_at !== null);
  const avg = answered.length
    ? (answered.reduce((t, r) => t + (r.rating ?? 0), 0) / answered.length).toFixed(2)
    : "—";
  const rate = all.length ? Math.round((answered.length / all.length) * 100) : 0;

  return (
    <Page
      title="Reviews"
      action={
        <Button variant="primary" onClick={() => setOutreachOpen(true)}>
          <Send className="size-3.5" strokeWidth={2} />
          Request reviews
        </Button>
      }
    >
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

      <ReviewOutreachDialog open={outreachOpen} onClose={() => setOutreachOpen(false)} />
    </Page>
  );
}

/**
 * Review outreach. The audience is computed, not chosen: every completed job
 * with no review submitted. The Guard is run over it first so the owner sees
 * who will actually be reached before committing.
 */
function ReviewOutreachDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const qc = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const [sent, setSent] = useState<number | null>(null);

  const preview = useQuery({
    queryKey: ["campaign-preview", "review_request"],
    queryFn: () => api.campaignPreview("review_request"),
    enabled: open,
  });

  const run = useMutation({
    mutationFn: async () => {
      const ids = preview.data?.candidates.filter((c) => c.eligible).map((c) => c.customer_id) ?? [];
      const result = await api.launchCampaign({
        name: `Review requests — ${new Date().toLocaleDateString("en-IN")}`,
        campaign_type: "review_request",
        customer_ids: ids,
      });
      // Queue and send in one action; waiting is not useful here.
      await api.runDue();
      return result;
    },
    onSuccess: (r) => {
      setSent(r.queued);
      qc.invalidateQueries({ queryKey: ["reviews"] });
      qc.invalidateQueries({ queryKey: ["campaigns"] });
      qc.invalidateQueries({ queryKey: ["ai-decisions"] });
    },
    onError: (e: unknown) =>
      setError(e instanceof ApiError ? e.message : "Could not send the requests."),
  });

  const eligible = preview.data?.eligible ?? 0;

  return (
    <Dialog
      open={open}
      onClose={() => { setSent(null); setError(null); onClose(); }}
      title="Request reviews"
      footer={
        <>
          <Button variant="ghost" onClick={() => { setSent(null); onClose(); }}>
            {sent === null ? "Cancel" : "Close"}
          </Button>
          {sent === null ? (
            <Button variant="primary" loading={run.isPending} disabled={eligible === 0}
              onClick={() => run.mutate()}>
              Send {eligible} request{eligible === 1 ? "" : "s"}
            </Button>
          ) : null}
        </>
      }
    >
      {sent !== null ? (
        <p className="t-body">
          Queued {sent} request{sent === 1 ? "" : "s"} and ran the queue. Ratings
          appear here as customers reply.
        </p>
      ) : preview.isPending ? (
        <p className="t-label">Checking who is eligible…</p>
      ) : preview.isError ? (
        <InlineError message="Could not work out the audience." />
      ) : preview.data?.total === 0 ? (
        <p className="t-body">
          Nobody is waiting on a review request. Complete a job first.
        </p>
      ) : (
        <>
          <p className="t-body">
            {preview.data?.total} customer{preview.data?.total === 1 ? "" : "s"} completed
            a job without leaving a review.
          </p>
          <div className="flex items-center gap-1.5 t-meta">
            <ShieldCheck className="size-3.5" strokeWidth={1.75} />
            {eligible} of {preview.data?.total} pass the Communication Guard
          </div>
          <ul className="max-h-[170px] space-y-px overflow-y-auto rounded-[4px] border border-line">
            {preview.data?.candidates.map((c) => (
              <li key={c.customer_id}
                className="flex items-center gap-2 px-2.5 py-1.5 text-[13px]">
                <StatusDot tone={c.eligible ? "success" : "warning"} />
                <span className="min-w-0 flex-1 truncate">{c.name}</span>
                {!c.eligible ? (
                  <span className="truncate text-[11px] text-ink-subtle" title={c.reason ?? ""}>
                    {c.reason}
                  </span>
                ) : null}
              </li>
            ))}
          </ul>
        </>
      )}
      <InlineError message={error} />
    </Dialog>
  );
}
