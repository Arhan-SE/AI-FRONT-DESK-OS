/**
 * Rendering for one Ask answer — shared by the Cmd-K bar and the AI Manager
 * page, so a row of data looks the same wherever it's asked from.
 */

import { useState } from "react";
import type { AskAnswer } from "@/lib/api";

export function AskResult({ result }: { result: AskAnswer }) {
  const [showSql, setShowSql] = useState(false);

  return (
    <div className="space-y-4">
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
                      {formatAskValue(row[c])}
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

/** Dates as dates, money with separators, nulls as an em dash rather than "null". */
export function formatAskValue(value: unknown): string {
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
