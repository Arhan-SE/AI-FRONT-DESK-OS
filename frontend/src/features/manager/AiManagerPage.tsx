/**
 * The AI Business Manager — a full page for the same read-only Ask endpoint
 * behind the Cmd-K bar, for a longer working session rather than one
 * question at a time. A thread, not a modal: history is sent with every
 * question so "who owes me money" then "chase him" resolves correctly.
 *
 * It answers from the live database and never acts on it — no button here
 * sends a message or changes a record. That is a deliberate boundary, not a
 * missing feature: every answer is checkable against the SQL it ran.
 */

import { useEffect, useRef, useState } from "react";
import { Page } from "@/components/AppShell";
import { Panel } from "@/components/ui/primitives";
import { AskResult } from "@/components/AskResult";
import { api, ApiError, type AskAnswer } from "@/lib/api";
import { cn } from "@/lib/cn";
import { Sparkles, ArrowUp, Loader2, AlertCircle, Bot } from "lucide-react";

const SUGGESTIONS = [
  "Who owes me money right now?",
  "How much did I collect this month?",
  "Which customers haven't been serviced in 3 months?",
  "Who is my busiest technician?",
  "What did the AI cost me so far?",
  "How many leads are hot right now?",
];

// The backend caps history at 8 turns — enough for a follow-up or two to
// resolve, not enough for the prompt to grow without bound over a long session.
const MAX_HISTORY = 8;

interface Turn {
  id: string;
  question: string;
  result: AskAnswer | null;
  error: string | null;
  pending: boolean;
}

export function AiManagerPage() {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [turns]);

  const ask = async (question: string) => {
    const trimmed = question.trim();
    if (trimmed.length < 3) return;

    const id = crypto.randomUUID();
    setInput("");
    setTurns((prev) => [...prev, { id, question: trimmed, result: null, error: null, pending: true }]);

    // Every prior Q and A, oldest-first, capped to what the server accepts.
    const history = turns
      .filter((t) => t.result)
      .flatMap((t) => [
        { role: "user" as const, content: t.question },
        { role: "assistant" as const, content: t.result!.answer },
      ])
      .slice(-MAX_HISTORY);

    try {
      const result = await api.ask(trimmed, history);
      setTurns((prev) => prev.map((t) => (t.id === id ? { ...t, result, pending: false } : t)));
    } catch (e) {
      const message = e instanceof ApiError ? e.message : "Something went wrong. Try again.";
      setTurns((prev) => prev.map((t) => (t.id === id ? { ...t, error: message, pending: false } : t)));
    }
  };

  return (
    <Page
      title="AI Business Manager"
      description="Ask anything about your business — it reads the live database and shows the query behind every answer"
    >
      <div className="flex h-[calc(100dvh-172px)] flex-col">
        <Panel className="flex min-h-0 flex-1 flex-col">
          <div className="min-h-0 flex-1 overflow-y-auto px-5 py-5">
            {turns.length === 0 ? (
              <div className="flex h-full flex-col items-center justify-center text-center">
                <Bot className="mb-3 size-8 text-ink-subtle" strokeWidth={1.5} />
                <p className="t-label mb-4 max-w-[360px]">
                  Ask about jobs, customers, invoices, payments, campaigns, reviews, or
                  what the AI has cost — in plain English.
                </p>
                <div className="flex flex-wrap justify-center gap-1.5">
                  {SUGGESTIONS.map((s) => (
                    <button
                      key={s}
                      type="button"
                      onClick={() => void ask(s)}
                      className={cn(
                        "rounded-full border border-line px-3 py-1.5 text-[12px] text-ink-muted",
                        "transition-colors duration-150 hover:border-line-strong hover:text-ink",
                      )}
                    >
                      {s}
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              <div className="space-y-6">
                {turns.map((t) => (
                  <div key={t.id} className="space-y-3">
                    <div className="flex items-start gap-2.5">
                      <span className="mt-0.5 flex size-6 shrink-0 items-center justify-center rounded-full bg-raised text-[11px] font-medium">
                        You
                      </span>
                      <p className="mt-1 text-[14px] text-ink">{t.question}</p>
                    </div>
                    <div className="flex items-start gap-2.5">
                      <span className="mt-0.5 flex size-6 shrink-0 items-center justify-center rounded-full bg-ink text-raised">
                        <Sparkles className="size-3.5" strokeWidth={2} />
                      </span>
                      <div className="min-w-0 flex-1 pt-0.5">
                        {t.pending ? (
                          <p className="flex items-center gap-2 text-[13px] text-ink-muted">
                            <Loader2 className="size-3.5 animate-spin" />
                            Reading your data…
                          </p>
                        ) : t.error ? (
                          <div className="flex items-start gap-2 text-[13px] text-critical">
                            <AlertCircle className="mt-0.5 size-4 shrink-0" />
                            <span>{t.error}</span>
                          </div>
                        ) : t.result ? (
                          <AskResult result={t.result} />
                        ) : null}
                      </div>
                    </div>
                  </div>
                ))}
                <div ref={endRef} />
              </div>
            )}
          </div>

          <div className="flex items-center gap-2.5 border-t border-line px-4 py-3">
            <Sparkles className="size-4 shrink-0 text-ink-muted" strokeWidth={2} />
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && void ask(input)}
              placeholder="Ask a follow-up…"
              maxLength={300}
              className="h-9 min-w-0 flex-1 bg-transparent text-[14px] text-ink placeholder:text-ink-subtle focus:outline-none"
            />
            <button
              type="button"
              onClick={() => void ask(input)}
              disabled={input.trim().length < 3}
              className={cn(
                "flex size-7 shrink-0 items-center justify-center rounded-full transition-colors duration-150",
                input.trim().length < 3
                  ? "bg-raised text-ink-subtle"
                  : "bg-ink text-raised hover:opacity-90",
              )}
            >
              <ArrowUp className="size-4" strokeWidth={2.25} />
            </button>
          </div>
        </Panel>
      </div>
    </Page>
  );
}
