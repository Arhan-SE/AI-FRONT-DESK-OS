/**
 * Ask — the AI Administrative Manager.
 *
 * Cmd/Ctrl-K anywhere in the product. The owner types a question in English and
 * gets a sentence back, with the rows it came from and the SQL that produced
 * them. The query is shown deliberately: an answer the owner cannot check is
 * not an answer, and seeing the SQL is what separates this from a chatbot
 * guessing at numbers.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Sparkles, CornerDownLeft, Loader2, AlertCircle } from "lucide-react";
import { api, ApiError, type AskAnswer } from "@/lib/api";
import { cn } from "@/lib/cn";

const SUGGESTIONS = [
  "Who owes me money right now?",
  "How much did I collect this month?",
  "Which customers haven't been serviced in 3 months?",
  "Who is my busiest technician?",
  "What did the AI cost me so far?",
];

export function AskBar() {
  const [open, setOpen] = useState(false);
  const [question, setQuestion] = useState("");
  const [pending, setPending] = useState(false);
  const [result, setResult] = useState<AskAnswer | null>(null);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Cmd-K opens, Escape closes. Registered once for the whole app.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "k" && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        setOpen((v) => !v);
      }
      if (e.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => {
    if (open) requestAnimationFrame(() => inputRef.current?.focus());
  }, [open]);

  const ask = useCallback(async (q: string) => {
    const trimmed = q.trim();
    if (trimmed.length < 3 || pending) return;
    setQuestion(trimmed);
    setPending(true);
    setError(null);
    setResult(null);
    try {
      setResult(await api.ask(trimmed));
    } catch (e) {
      setError(
        e instanceof ApiError ? e.message : "Something went wrong. Try again.",
      );
    } finally {
      setPending(false);
    }
  }, [pending]);

  if (!open) return <AskTrigger onClick={() => setOpen(true)} />;

  return (
    <>
      <AskTrigger onClick={() => setOpen(true)} />
      {createPortal(
        <div
          className="fixed inset-0 z-50 flex items-start justify-center bg-ink/25 p-4 pt-[12vh]"
          onClick={() => setOpen(false)}
          role="presentation"
        >
          <div
            role="dialog"
            aria-modal="true"
            aria-label="Ask your business"
            onClick={(e) => e.stopPropagation()}
            className={cn(
              "flex max-h-[70vh] w-full max-w-[720px] flex-col overflow-hidden",
              "rounded-[8px] border border-line bg-raised shadow-[var(--shadow-overlay)]",
            )}
          >
            {/* ------------------------------------------------ input row */}
            <div className="flex items-center gap-2.5 border-b border-line px-4">
              {pending ? (
                <Loader2 className="size-4 shrink-0 animate-spin text-ink-muted" />
              ) : (
                <Sparkles className="size-4 shrink-0 text-ink-muted" strokeWidth={2} />
              )}
              <input
                ref={inputRef}
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && void ask(question)}
                placeholder="Ask anything about your business…"
                maxLength={300}
                className={cn(
                  "h-14 min-w-0 flex-1 bg-transparent text-[15px] text-ink",
                  "placeholder:text-ink-subtle focus:outline-none",
                )}
              />
              <kbd className="hidden shrink-0 items-center gap-1 rounded-[4px] border border-line px-1.5 py-0.5 text-[11px] text-ink-subtle sm:flex">
                <CornerDownLeft className="size-3" /> Enter
              </kbd>
            </div>

            {/* ---------------------------------------------------- body */}
            <div className="min-h-0 flex-1 overflow-y-auto">
              {!result && !pending && !error ? (
                <Suggestions onPick={(q) => void ask(q)} />
              ) : null}

              {pending ? (
                <p className="px-4 py-6 text-[13px] text-ink-muted">
                  Reading your data…
                </p>
              ) : null}

              {error ? (
                <div className="flex items-start gap-2 px-4 py-5 text-[13px] text-critical">
                  <AlertCircle className="mt-0.5 size-4 shrink-0" />
                  <span>{error}</span>
                </div>
              ) : null}

              {result ? <Result result={result} /> : null}
            </div>
          </div>
        </div>,
        document.body,
      )}
    </>
  );
}

/* ------------------------------------------------------------------ parts */

function Suggestions({ onPick }: { onPick: (q: string) => void }) {
  return (
    <div className="px-2 py-2">
      <div className="px-2 pb-1 pt-1 text-[11px] font-medium uppercase tracking-wider text-ink-subtle">
        Try
      </div>
      {SUGGESTIONS.map((s) => (
        <button
          key={s}
          type="button"
          onClick={() => onPick(s)}
          className={cn(
            "block w-full rounded-[4px] px-2 py-2 text-left text-[13px] text-ink-muted",
            "transition-colors duration-150 hover:bg-surface hover:text-ink",
          )}
        >
          {s}
        </button>
      ))}
    </div>
  );
}

function Result({ result }: { result: AskAnswer }) {
  const [showSql, setShowSql] = useState(false);

  return (
    <div className="space-y-4 px-4 py-4">
      <p className="text-[15px] leading-relaxed text-ink">{result.answer}</p>

      {result.rows.length > 0 ? (
        <div className="overflow-x-auto rounded-[6px] border border-line">
          <table className="w-full border-collapse text-[12px]">
            <thead>
              <tr className="border-b border-line bg-surface">
                {result.columns.map((c) => (
                  <th
                    key={c}
                    className="whitespace-nowrap px-3 py-2 text-left font-medium text-ink-muted"
                  >
                    {c.replace(/_/g, " ")}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {result.rows.map((row, i) => (
                <tr key={i} className="border-b border-line last:border-0">
                  {result.columns.map((c) => (
                    <td
                      key={c}
                      className="whitespace-nowrap px-3 py-2 text-ink tabular-nums"
                    >
                      {format(row[c])}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}

      {/* The receipt. Anyone can check the answer against the query. */}
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-ink-subtle">
        <span className="tabular-nums">
          {result.row_count} row{result.row_count === 1 ? "" : "s"}
        </span>
        <span>·</span>
        <span className="tabular-nums">{result.elapsed_ms} ms</span>
        {result.sql ? (
          <>
            <span>·</span>
            <button
              type="button"
              onClick={() => setShowSql((v) => !v)}
              className="underline underline-offset-2 transition-colors duration-150 hover:text-ink"
            >
              {showSql ? "hide query" : "show the query it ran"}
            </button>
          </>
        ) : null}
      </div>

      {showSql && result.sql ? (
        <pre className="overflow-x-auto rounded-[6px] border border-line bg-surface p-3 font-mono text-[11px] leading-relaxed text-ink-muted">
          {result.sql}
        </pre>
      ) : null}
    </div>
  );
}

function AskTrigger({ onClick }: { onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "flex w-full items-center gap-2 rounded-[6px] border border-line bg-raised px-2.5 py-2",
        "text-left text-[12px] text-ink-subtle transition-colors duration-150",
        "hover:border-line-strong hover:text-ink-muted",
      )}
    >
      <Sparkles className="size-3.5 shrink-0" strokeWidth={2} />
      <span className="flex-1 truncate">Ask your business…</span>
      <kbd className="shrink-0 font-mono text-[11px]">⌘K</kbd>
    </button>
  );
}

/** Dates as dates, money with separators, nulls as an em dash rather than "null". */
function format(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "boolean") return value ? "yes" : "no";
  if (typeof value === "number") {
    return Number.isInteger(value)
      ? value.toLocaleString("en-IN")
      : value.toLocaleString("en-IN", { maximumFractionDigits: 2 });
  }
  const text = String(value);
  const asDate = /^\d{4}-\d{2}-\d{2}([T ]|$)/.test(text) ? new Date(text) : null;
  if (asDate && !Number.isNaN(asDate.getTime())) {
    return asDate.toLocaleDateString("en-IN", {
      day: "numeric",
      month: "short",
      year: "numeric",
    });
  }
  return text;
}
