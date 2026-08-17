import { Page } from "@/components/AppShell";
import {
  Panel, PanelHeader, MetricTile, Table, Th, Td, Tr, StatusDot, Tag,
  EmptyState, ErrorState, TableSkeleton, type Tone,
} from "@/components/ui/primitives";
import { useState } from "react";
import { useLeads, useLeadScores, type LeadRow } from "@/lib/pageQueries";
import { LeadDialog } from "./LeadDialog";
import { Button } from "@/components/ui/controls";
import { formatRelative } from "@/lib/format";
import { Target, Plus } from "lucide-react";

const CLASS_TONE: Record<string, Tone> = {
  HOT: "critical", WARM: "warning", COLD: "neutral",
};

export function LeadsPage() {
  const leads = useLeads();
  const scores = useLeadScores();
  const [editing, setEditing] = useState<LeadRow | null>(null);
  const [creating, setCreating] = useState(false);

  const all = leads.data ?? [];
  const byLead = new Map((scores.data ?? []).map((s) => [s.lead_id, s]));

  const hot = all.filter((l) => byLead.get(l.id)?.classification === "HOT").length;
  const open = all.filter((l) => ["new", "qualified"].includes(l.status)).length;
  const converted = all.filter((l) => l.status === "converted").length;
  const rate = all.length ? Math.round((converted / all.length) * 100) : 0;

  return (
    <Page
      title="Leads"
      action={
        <Button variant="primary" onClick={() => setCreating(true)}>
          <Plus className="size-3.5" strokeWidth={2} />
          New lead
        </Button>
      }
    >
      <div className="mb-5 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <MetricTile label="Total leads" value={all.length} loading={leads.isPending} />
        <MetricTile label="Open" value={open} loading={leads.isPending} />
        <MetricTile label="Hot" value={hot} tone={hot ? "critical" : "neutral"}
          hint={hot ? "needs follow-up" : undefined} loading={leads.isPending} />
        <MetricTile label="Conversion" value={all.length ? `${rate}%` : "—"}
          hint={`${converted} converted`} loading={leads.isPending} />
      </div>

      <Panel>
        <PanelHeader
          title="All leads"
          description="Captured and scored by the AI during a conversation"
        />
        {leads.isPending ? (
          <TableSkeleton rows={5} cols={5} />
        ) : leads.isError ? (
          <ErrorState onRetry={() => void leads.refetch()} />
        ) : all.length === 0 ? (
          <EmptyState
            icon={Target}
            title="No leads yet"
            description="Leads are created when the voice agent qualifies a caller. Start a call to generate one."
          />
        ) : (
          <Table>
            <thead>
              <tr>
                <Th>Customer</Th><Th>Service wanted</Th><Th align="right">Score</Th>
                <Th>Priority</Th><Th>Status</Th><Th>Next action</Th><Th align="right">Age</Th>
              </tr>
            </thead>
            <tbody>
              {all.map((lead) => {
                const score = byLead.get(lead.id);
                return (
                  <Tr key={lead.id} onClick={() => setEditing(lead)}>
                    <Td className="font-medium">{lead.customers?.full_name ?? "Unknown caller"}</Td>
                    <Td className="text-ink-muted">{lead.requested_service ?? "—"}</Td>
                    <Td align="right" className="font-mono font-medium">
                      {score ? score.score : "—"}
                    </Td>
                    <Td>
                      {score ? (
                        <span className="flex items-center gap-2">
                          <StatusDot tone={CLASS_TONE[score.classification]} />
                          {score.classification}
                        </span>
                      ) : (
                        <span className="t-meta">unscored</span>
                      )}
                    </Td>
                    <Td><Tag>{lead.status}</Tag></Td>
                    <Td className="max-w-[220px] truncate text-ink-muted">
                      {lead.next_action ?? "—"}
                    </Td>
                    <Td align="right" className="text-ink-subtle">
                      {formatRelative(lead.created_at)}
                    </Td>
                  </Tr>
                );
              })}
            </tbody>
          </Table>
        )}
      </Panel>

      <LeadDialog
        open={editing !== null || creating}
        lead={editing}
        onClose={() => { setEditing(null); setCreating(false); }}
      />
    </Page>
  );
}
