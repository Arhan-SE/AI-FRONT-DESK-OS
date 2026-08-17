import { Page } from "@/components/AppShell";
import {
  Panel, PanelHeader, Table, Th, Td, Tr, StatusDot,
  EmptyState, ErrorState, TableSkeleton, MetricTile,
} from "@/components/ui/primitives";
import { useCustomers } from "@/lib/pageQueries";
import { formatCurrency, formatRelative } from "@/lib/format";
import { Users, MessageSquareOff, Check } from "lucide-react";

export function CustomersPage() {
  const customers = useCustomers();
  const all = customers.data ?? [];

  const reachable = all.filter((c) => c.reachable).length;
  const outstanding = all.reduce((t, c) => t + Number(c.amount_outstanding), 0);
  const collected = all.reduce((t, c) => t + Number(c.total_paid), 0);

  return (
    <Page title="Customers">
      <div className="mb-5 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <MetricTile label="Customers" value={all.length} loading={customers.isPending} />
        <MetricTile
          label="Reachable on Telegram"
          value={`${reachable}/${all.length || 0}`}
          hint={reachable === 0 ? "none linked yet" : undefined}
          tone={reachable === 0 && all.length > 0 ? "warning" : "neutral"}
          loading={customers.isPending}
        />
        <MetricTile label="Collected" value={formatCurrency(collected)} loading={customers.isPending} />
        <MetricTile
          label="Outstanding"
          value={formatCurrency(outstanding)}
          tone={outstanding > 0 ? "critical" : "neutral"}
          loading={customers.isPending}
        />
      </div>

      <Panel>
        <PanelHeader
          title="All customers"
          description="Messaging requires a linked Telegram chat — unlinked customers cannot be contacted"
        />
        {customers.isPending ? (
          <TableSkeleton rows={5} cols={6} />
        ) : customers.isError ? (
          <ErrorState onRetry={() => void customers.refetch()} />
        ) : all.length === 0 ? (
          <EmptyState icon={Users} title="No customers yet" />
        ) : (
          <Table>
            <thead>
              <tr>
                <Th>Name</Th><Th>Phone</Th><Th align="right">Jobs</Th>
                <Th>Last service</Th><Th align="right">Paid</Th>
                <Th align="right">Outstanding</Th><Th>Telegram</Th>
              </tr>
            </thead>
            <tbody>
              {all.map((c) => (
                <Tr key={c.id}>
                  <Td>
                    <span className="flex items-center gap-2">
                      <span className="font-medium">{c.full_name}</span>
                      {c.do_not_contact ? (
                        <span className="t-meta text-critical">do not contact</span>
                      ) : null}
                    </span>
                  </Td>
                  <Td className="font-mono text-[12px] text-ink-muted">{c.phone ?? "—"}</Td>
                  <Td align="right">
                    {c.jobs_completed}
                    {c.jobs_upcoming > 0 ? (
                      <span className="t-meta ml-1">+{c.jobs_upcoming}</span>
                    ) : null}
                  </Td>
                  <Td className="text-ink-muted">
                    {c.last_service_at ? formatRelative(c.last_service_at) : "never"}
                  </Td>
                  <Td align="right">{formatCurrency(c.total_paid)}</Td>
                  <Td align="right" className={c.amount_outstanding > 0 ? "font-medium" : "text-ink-subtle"}>
                    {c.amount_outstanding > 0 ? formatCurrency(c.amount_outstanding) : "—"}
                  </Td>
                  <Td>
                    {c.reachable ? (
                      <span className="flex items-center gap-2">
                        <StatusDot tone="success" />
                        <Check className="size-3.5 text-ink-muted" strokeWidth={2} />
                      </span>
                    ) : (
                      <span
                        className="flex items-center gap-2 text-ink-subtle"
                        title="Messages to this customer will be blocked by the Communication Guard"
                      >
                        <MessageSquareOff className="size-3.5" strokeWidth={1.75} />
                        <span className="t-meta">not linked</span>
                      </span>
                    )}
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
