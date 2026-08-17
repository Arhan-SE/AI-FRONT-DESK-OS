import { useState, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Page } from "@/components/AppShell";
import {
  Panel, PanelHeader, Table, Th, Td, Tr, StatusDot, MetricTile,
  EmptyState, ErrorState, TableSkeleton, Tag,
} from "@/components/ui/primitives";
import { Button, Dialog, Field, Select, Input, InlineError } from "@/components/ui/controls";
import { useCampaigns } from "@/lib/pageQueries";
import { api, ApiError, type CampaignType } from "@/lib/api";
import { formatRelative } from "@/lib/format";
import { Megaphone, Plus, Play, ShieldCheck } from "lucide-react";

const TYPES: { value: CampaignType; label: string; blurb: string }[] = [
  { value: "reactivation", label: "Win back lapsed customers",
    blurb: "Customers with no completed job in the last 90 days" },
  { value: "seasonal", label: "Seasonal reminder",
    blurb: "Everyone who has not opted out" },
  { value: "review_request", label: "Chase missing reviews",
    blurb: "Completed jobs with no review submitted" },
];

export function CampaignsPage() {
  const qc = useQueryClient();
  const campaigns = useCampaigns();
  const [open, setOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const runDue = useMutation({
    mutationFn: api.runDue,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["campaigns"] });
      qc.invalidateQueries({ queryKey: ["ai-decisions"] });
    },
    onError: (e: unknown) =>
      setError(e instanceof ApiError ? e.message : "Could not run the campaign queue."),
  });

  const all = campaigns.data ?? [];
  const totals = all.reduce(
    (t, c) => ({ sent: t.sent + c.sent, blocked: t.blocked + c.blocked }),
    { sent: 0, blocked: 0 },
  );

  return (
    <Page
      title="Campaigns"
      action={
        <div className="flex items-center gap-2">
          <Button onClick={() => runDue.mutate()} loading={runDue.isPending}>
            <Play className="size-3.5" strokeWidth={2} />
            Run queued
          </Button>
          <Button variant="primary" onClick={() => setOpen(true)}>
            <Plus className="size-3.5" strokeWidth={2} />
            New campaign
          </Button>
        </div>
      }
    >
      <div className="mb-5 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <MetricTile label="Campaigns" value={all.length} loading={campaigns.isPending} />
        <MetricTile label="Messages sent" value={totals.sent}
          tone={totals.sent ? "success" : "neutral"} loading={campaigns.isPending} />
        <MetricTile label="Blocked by Guard" value={totals.blocked}
          hint="refused, with a reason" tone={totals.blocked ? "warning" : "neutral"}
          loading={campaigns.isPending} />
        <MetricTile label="Replies" value={all.reduce((t, c) => t + c.replied, 0)}
          loading={campaigns.isPending} />
      </div>

      <InlineError message={error} />

      <Panel className={error ? "mt-3" : ""}>
        <PanelHeader
          title="All campaigns"
          description="Every recipient passes the Communication Guard individually"
        />
        {campaigns.isPending ? (
          <TableSkeleton rows={4} cols={5} />
        ) : campaigns.isError ? (
          <ErrorState onRetry={() => void campaigns.refetch()} />
        ) : all.length === 0 ? (
          <EmptyState
            icon={Megaphone}
            title="No campaigns yet"
            description="Create one — you can see exactly who is eligible before sending."
          />
        ) : (
          <Table>
            <thead>
              <tr>
                <Th>Campaign</Th><Th>Type</Th><Th>Status</Th>
                <Th align="right">Audience</Th><Th align="right">Sent</Th>
                <Th align="right">Blocked</Th><Th align="right">Created</Th>
              </tr>
            </thead>
            <tbody>
              {all.map((c) => (
                <Tr key={c.id}>
                  <Td className="font-medium">{c.name}</Td>
                  <Td><Tag>{c.campaign_type.replace("_", " ")}</Tag></Td>
                  <Td>
                    <span className="flex items-center gap-2">
                      <StatusDot tone={c.status === "completed" ? "success" : "neutral"} />
                      {c.status}
                    </span>
                  </Td>
                  <Td align="right">{c.audience}</Td>
                  <Td align="right" className="font-medium">{c.sent}</Td>
                  <Td align="right" className={c.blocked ? "text-warning" : "text-ink-subtle"}>
                    {c.blocked || "—"}
                  </Td>
                  <Td align="right" className="text-ink-subtle">{formatRelative(c.created_at)}</Td>
                </Tr>
              ))}
            </tbody>
          </Table>
        )}
      </Panel>

      <NewCampaignDialog open={open} onClose={() => setOpen(false)} />
    </Page>
  );
}

function NewCampaignDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const qc = useQueryClient();
  const [type, setType] = useState<CampaignType>("reactivation");
  const [name, setName] = useState("");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [error, setError] = useState<string | null>(null);

  // The Guard is a pure decision, so the audience can be evaluated before
  // anything is sent. This is the preview.
  const preview = useQuery({
    queryKey: ["campaign-preview", type],
    queryFn: () => api.campaignPreview(type),
    enabled: open,
  });

  useEffect(() => {
    if (!preview.data) return;
    // Preselect only those who would actually receive it.
    setSelected(new Set(preview.data.candidates.filter((c) => c.eligible).map((c) => c.customer_id)));
  }, [preview.data]);

  useEffect(() => {
    if (open && !name) setName(TYPES.find((t) => t.value === type)?.label ?? "Campaign");
  }, [open, type, name]);

  const launch = useMutation({
    mutationFn: () =>
      api.launchCampaign({ name, campaign_type: type, customer_ids: [...selected] }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["campaigns"] });
      onClose();
      setName("");
    },
    onError: (e: unknown) =>
      setError(e instanceof ApiError ? e.message : "Could not launch the campaign."),
  });

  const toggle = (id: string) =>
    setSelected((s) => {
      const next = new Set(s);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="New campaign"
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>Cancel</Button>
          <Button variant="primary" loading={launch.isPending}
            disabled={selected.size === 0 || !name}
            onClick={() => launch.mutate()}>
            Queue {selected.size} message{selected.size === 1 ? "" : "s"}
          </Button>
        </>
      }
    >
      <Field label="Audience">
        <Select value={type} onChange={(v) => setType(v as CampaignType)}>
          {TYPES.map((t) => (
            <option key={t.value} value={t.value}>{t.label}</option>
          ))}
        </Select>
      </Field>
      <p className="t-meta -mt-1">{TYPES.find((t) => t.value === type)?.blurb}</p>

      <Field label="Campaign name">
        <Input value={name} onChange={setName} placeholder="Pre-monsoon service push" />
      </Field>

      <div>
        <div className="mb-1.5 flex items-center justify-between">
          <span className="t-label">Eligibility</span>
          {preview.data ? (
            <span className="flex items-center gap-1.5 t-meta">
              <ShieldCheck className="size-3.5" strokeWidth={1.75} />
              {preview.data.eligible} of {preview.data.total} eligible
            </span>
          ) : null}
        </div>

        {preview.isPending ? (
          <p className="t-label">Checking the Guard…</p>
        ) : preview.isError ? (
          <InlineError message="Could not evaluate the audience." />
        ) : preview.data?.total === 0 ? (
          <p className="t-label">Nobody matches this audience yet.</p>
        ) : (
          <ul className="max-h-[190px] space-y-px overflow-y-auto rounded-[4px] border border-line">
            {preview.data?.candidates.map((c) => (
              <li key={c.customer_id}>
                <label
                  className={[
                    "flex cursor-pointer items-center gap-2 px-2.5 py-1.5",
                    c.eligible ? "hover:bg-surface" : "opacity-60",
                  ].join(" ")}
                >
                  <input
                    type="checkbox"
                    className="accent-ink"
                    checked={selected.has(c.customer_id)}
                    onChange={() => toggle(c.customer_id)}
                  />
                  <span className="min-w-0 flex-1 truncate text-[13px]">{c.name}</span>
                  {c.eligible ? (
                    <StatusDot tone="success" />
                  ) : (
                    // The reason is shown, not hidden — the owner should know
                    // why someone will not be contacted before they send.
                    <span className="truncate text-[11px] text-ink-subtle" title={c.reason ?? ""}>
                      {c.reason}
                    </span>
                  )}
                </label>
              </li>
            ))}
          </ul>
        )}
      </div>

      <InlineError message={error} />
    </Dialog>
  );
}
