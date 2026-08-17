import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Page } from "@/components/AppShell";
import {
  Panel, PanelHeader, MetricTile, Table, Th, Td, Tr,
  StatusDot, EmptyState, ErrorState, TableSkeleton, type Tone,
} from "@/components/ui/primitives";
import { Button, InlineError } from "@/components/ui/controls";
import { useInvoices, type Invoice } from "@/lib/pageQueries";
import { api, ApiError } from "@/lib/api";
import { formatCurrency, formatCurrencyCompact, formatDate, formatRelative } from "@/lib/format";
import { Receipt, Play } from "lucide-react";

const STATUS: Record<string, { label: string; tone: Tone }> = {
  paid: { label: "Paid", tone: "success" },
  overdue: { label: "Overdue", tone: "critical" },
  sent: { label: "Awaiting payment", tone: "neutral" },
  draft: { label: "Draft", tone: "neutral" },
  void: { label: "Void", tone: "neutral" },
};

export function PaymentsPage() {
  const qc = useQueryClient();
  const invoices = useInvoices();
  const [error, setError] = useState<string | null>(null);

  const runDue = useMutation({
    mutationFn: api.runDue,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["invoices"] });
      qc.invalidateQueries({ queryKey: ["ai-decisions"] });
    },
    onError: (e: unknown) =>
      setError(e instanceof ApiError ? e.message : "Could not run the reminders."),
  });

  const all = invoices.data ?? [];
  const sum = (rows: Invoice[]) => rows.reduce((t, i) => t + Number(i.amount), 0);

  const outstanding = all.filter((i) => i.status === "sent" || i.status === "overdue");
  const overdue = all.filter((i) => i.status === "overdue");
  const paid = all.filter((i) => i.status === "paid");

  return (
    <Page
      title="Payments"
      action={
        <Button onClick={() => runDue.mutate()} loading={runDue.isPending}
          title="Advance scheduled reminders to now and send them">
          <Play className="size-3.5" strokeWidth={2} />
          Send due reminders
        </Button>
      }
    >
      <div className="mb-5 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <MetricTile label="Outstanding" value={formatCurrencyCompact(sum(outstanding))}
          hint={`${outstanding.length} invoice${outstanding.length === 1 ? "" : "s"}`}
          loading={invoices.isPending} />
        <MetricTile label="Overdue" value={formatCurrencyCompact(sum(overdue))}
          hint={overdue.length ? `${overdue.length} being chased` : "none"}
          tone={overdue.length ? "critical" : "neutral"} loading={invoices.isPending} />
        <MetricTile label="Collected" value={formatCurrencyCompact(sum(paid))}
          hint={`${paid.length} paid`} tone={paid.length ? "success" : "neutral"}
          loading={invoices.isPending} />
        <MetricTile label="Reminders sent"
          value={all.reduce((t, i) => t + i.reminders_sent, 0)}
          hint="automatic" loading={invoices.isPending} />
      </div>

      <InlineError message={error} />

      <Panel className={error ? "mt-3" : ""}>
        <PanelHeader
          title="Invoices"
          description="Raised from the Jobs board — reminders send themselves once due"
        />
        {invoices.isPending ? (
          <TableSkeleton rows={5} cols={6} />
        ) : invoices.isError ? (
          <ErrorState onRetry={() => void invoices.refetch()} />
        ) : all.length === 0 ? (
          <EmptyState
            icon={Receipt}
            title="No invoices yet"
            description="Complete a job on the Jobs board and press Send invoice — it appears here."
          />
        ) : (
          <Table>
            <thead>
              <tr>
                <Th>Invoice</Th><Th>Customer</Th><Th>Service</Th>
                <Th align="right">Amount</Th><Th>Due</Th><Th>Status</Th><Th align="right">Reminders</Th>
              </tr>
            </thead>
            <tbody>
              {all.map((inv) => {
                const meta = STATUS[inv.status] ?? { label: inv.status, tone: "neutral" as Tone };
                return (
                  <Tr key={inv.id}>
                    <Td className="font-mono text-[12px]">{inv.invoice_number}</Td>
                    <Td className="font-medium">{inv.customer_name}</Td>
                    <Td className="text-ink-muted">{inv.service_name ?? "—"}</Td>
                    <Td align="right" className="font-medium">{formatCurrency(inv.amount)}</Td>
                    <Td className="text-ink-muted">
                      {formatDate(inv.due_on)}
                      {inv.status === "overdue" ? (
                        <span className="t-meta ml-1.5 text-critical">
                          +{inv.days_past_due}d
                        </span>
                      ) : null}
                    </Td>
                    <Td>
                      <span className="flex items-center gap-2">
                        <StatusDot tone={meta.tone} />
                        {meta.label}
                        {inv.paid_at ? (
                          <span className="t-meta">{formatRelative(inv.paid_at)}</span>
                        ) : null}
                      </span>
                    </Td>
                    <Td align="right" className="text-ink-subtle">
                      {inv.reminders_sent > 0 ? (
                        <span title={`Last sent ${formatRelative(inv.last_reminder_at)}`}>
                          {inv.reminders_sent} sent
                        </span>
                      ) : inv.next_reminder_at ? (
                        <span className="t-meta" title={inv.next_reminder_at}>
                          due {formatRelative(inv.next_reminder_at)}
                        </span>
                      ) : (
                        "—"
                      )}
                    </Td>
                  </Tr>
                );
              })}
            </tbody>
          </Table>
        )}
      </Panel>
    </Page>
  );
}
