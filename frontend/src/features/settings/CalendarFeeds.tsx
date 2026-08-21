/**
 * Calendar subscription feeds.
 *
 * Each URL is a live, read-only view of the appointment book that any calendar
 * app can subscribe to. The database stays authoritative — nothing a calendar
 * client does can move a booking — so this publishes outward only.
 *
 * The URLs are credentials, so they are shown masked until asked for.
 */

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Panel, PanelHeader, TableSkeleton, ErrorState } from "@/components/ui/primitives";
import { Button } from "@/components/ui/controls";
import { api } from "@/lib/api";
import { Check, Copy, Eye, EyeOff } from "lucide-react";
import { cn } from "@/lib/cn";

export function CalendarFeeds() {
  const feeds = useQuery({ queryKey: ["calendar-feeds"], queryFn: api.calendarFeeds });
  const [revealed, setRevealed] = useState(false);

  return (
    <Panel className="mt-6">
      <PanelHeader
        title="Calendar feeds"
        description="Subscribe in Google Calendar, Apple Calendar or Outlook — jobs appear automatically"
        action={
          <Button onClick={() => setRevealed((v) => !v)}>
            {revealed ? <EyeOff className="size-3.5" /> : <Eye className="size-3.5" />}
            {revealed ? "Hide" : "Reveal"}
          </Button>
        }
      />

      {feeds.isPending ? (
        <TableSkeleton rows={4} cols={2} />
      ) : feeds.isError ? (
        <ErrorState onRetry={() => void feeds.refetch()} />
      ) : (
        <>
          <div className="divide-y divide-line">
            <FeedRow
              label={feeds.data.business.name}
              url={feeds.data.business.url}
              revealed={revealed}
              primary
            />
            {feeds.data.technicians.map((t) => (
              <FeedRow key={t.url} label={t.name} url={t.url} revealed={revealed} />
            ))}
          </div>

          <p className="border-t border-line px-4 py-3 text-[12px] leading-relaxed text-ink-muted">
            These links are read-only and are the only credential needed to view
            them — treat them like a password. Anyone with the URL sees that
            schedule.
          </p>
        </>
      )}
    </Panel>
  );
}

function FeedRow({
  label,
  url,
  revealed,
  primary = false,
}: {
  label: string;
  url: string;
  revealed: boolean;
  primary?: boolean;
}) {
  const [copied, setCopied] = useState(false);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
      setTimeout(() => setCopied(false), 1600);
    } catch {
      // Clipboard needs a secure context. Revealing the URL lets it be
      // selected by hand, which is a working answer rather than a dead button.
      setCopied(false);
    }
  };

  // Show enough of the token to tell two feeds apart, never the whole thing.
  const masked = url.replace(/\/([0-9a-f]{8})[0-9a-f]+\.ics$/, "/$1••••••••••••.ics");

  return (
    <div className="flex flex-wrap items-center gap-3 px-4 py-3">
      <span className={cn("w-40 shrink-0 text-[13px]", primary && "font-medium")}>
        {label}
      </span>
      <code className="min-w-0 flex-1 truncate font-mono text-[11px] text-ink-muted">
        {revealed ? url : masked}
      </code>
      <Button onClick={copy} title="Copy subscription URL">
        {copied ? (
          <Check className="size-3.5 text-success" strokeWidth={2} />
        ) : (
          <Copy className="size-3.5" strokeWidth={2} />
        )}
        {copied ? "Copied" : "Copy"}
      </Button>
    </div>
  );
}
