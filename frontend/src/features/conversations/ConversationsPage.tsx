import { useState, useEffect } from "react";
import { Page } from "@/components/AppShell";
import {
  Panel, PanelHeader, StatusDot, EmptyState, ErrorState, TableSkeleton, Tag,
} from "@/components/ui/primitives";
import {
  useConversations, useMessages, useConversationDecisions,
} from "@/lib/pageQueries";
import { formatRelative, formatClock, formatDateTime } from "@/lib/format";
import { MessagesSquare, Mic } from "lucide-react";

export function ConversationsPage() {
  const conversations = useConversations();
  const [selected, setSelected] = useState<string | null>(null);

  const all = conversations.data ?? [];

  // Default to the most recent call so the panel is never pointlessly blank.
  useEffect(() => {
    if (selected === null && all.length > 0) setSelected(all[0].id);
  }, [all, selected]);

  const messages = useMessages(selected);
  const decisions = useConversationDecisions(selected);
  const current = all.find((c) => c.id === selected) ?? null;

  return (
    <Page title="Conversations">
      <div className="grid gap-6 xl:grid-cols-[minmax(0,340px)_minmax(0,1fr)]">
        {/* ------------------------------------------------------- list */}
        <Panel className="flex flex-col">
          <PanelHeader title="Calls" description={`${all.length} recorded`} />
          {conversations.isPending ? (
            <TableSkeleton rows={5} cols={2} />
          ) : conversations.isError ? (
            <ErrorState onRetry={() => void conversations.refetch()} />
          ) : all.length === 0 ? (
            <EmptyState
              icon={MessagesSquare}
              title="No conversations yet"
              description="Start a call from Live Call and it is recorded here."
            />
          ) : (
            <ul className="divide-y divide-line overflow-y-auto">
              {all.map((c) => (
                <li key={c.id}>
                  <button
                    type="button"
                    onClick={() => setSelected(c.id)}
                    className={[
                      "w-full px-4 py-3 text-left transition-colors duration-150",
                      selected === c.id ? "bg-surface" : "hover:bg-surface/60",
                    ].join(" ")}
                  >
                    <span className="flex items-center gap-2">
                      <StatusDot tone={c.status === "active" ? "success" : "neutral"} />
                      <span className="t-cell font-medium">
                        {c.customers?.full_name ?? "Unknown caller"}
                      </span>
                      {c.channel === "voice" ? (
                        <Mic className="size-3 text-ink-subtle" strokeWidth={2} />
                      ) : null}
                      <span className="ml-auto t-meta">{formatRelative(c.started_at)}</span>
                    </span>
                    <span className="mt-1 block truncate text-[12px] text-ink-muted">
                      {c.summary ?? (c.status === "active" ? "In progress…" : "No summary")}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Panel>

        {/* --------------------------------------------------- transcript */}
        <div className="space-y-6">
          <Panel className="flex flex-col">
            <PanelHeader
              title={current ? (current.customers?.full_name ?? "Unknown caller") : "Transcript"}
              description={
                current
                  ? `${formatDateTime(current.started_at)}${current.status === "active" ? " · in progress" : ""}`
                  : undefined
              }
              action={current?.channel ? <Tag>{current.channel}</Tag> : undefined}
            />
            <div className="min-h-[300px] max-h-[440px] overflow-y-auto px-4 py-3">
              {!selected ? (
                <EmptyState title="Select a call" />
              ) : messages.isPending ? (
                <TableSkeleton rows={4} cols={2} />
              ) : !messages.data?.length ? (
                <EmptyState
                  title="No transcript"
                  description="Nothing was said, or the call ended before anyone spoke."
                />
              ) : (
                <ul className="space-y-2.5">
                  {messages.data.map((m) => (
                    <li key={m.id} className="flex gap-3">
                      <span
                        className={[
                          "w-[68px] shrink-0 pt-px text-[11px] font-medium uppercase tracking-wide",
                          m.role === "agent" ? "text-ink" : "text-ink-subtle",
                        ].join(" ")}
                      >
                        {m.role === "agent" ? "AI" : m.role === "customer" ? "Customer" : m.role}
                      </span>
                      <span
                        className={[
                          "t-cell",
                          m.role === "agent" ? "text-ink" : "text-ink-muted",
                        ].join(" ")}
                      >
                        {m.content}
                      </span>
                      <span className="ml-auto shrink-0 t-meta">{formatClock(m.created_at)}</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </Panel>

          {/* What the AI actually did during this specific call — the
              transcript says what was said, this says what was decided. */}
          <Panel>
            <PanelHeader title="Decisions in this call" />
            {!decisions.data?.length ? (
              <EmptyState title="No decisions recorded" />
            ) : (
              <ul className="divide-y divide-line">
                {decisions.data.map((d) => (
                  <li key={d.id} className="flex items-baseline gap-3 px-4 py-2">
                    <span className="t-meta shrink-0">{formatClock(d.created_at)}</span>
                    <StatusDot
                      tone={
                        d.status === "failure" ? "critical"
                        : d.status === "blocked" ? "warning" : "success"
                      }
                      className="translate-y-[3px]"
                    />
                    <span className="min-w-0 flex-1 t-cell">{d.summary}</span>
                  </li>
                ))}
              </ul>
            )}
          </Panel>
        </div>
      </div>
    </Page>
  );
}
