"use client";

import React from "react";
import { TrashIcon, Square2StackIcon, CheckIcon } from "@heroicons/react/24/outline";

interface DeadCodeItem {
  symbol?: string;
  type?: string;
  path?: string;
  line?: number;
  confidence?: string;
}

interface DeadCodePanelProps {
  deadCode: DeadCodeItem[];
}

export function DeadCodePanel({ deadCode }: DeadCodePanelProps) {
  const [copiedIdx, setCopiedIdx] = React.useState<number | null>(null);

  if (!deadCode.length) {
    return (
      <div className="subtle-card p-8 text-center text-[var(--text-secondary)] text-sm font-medium">
        Zero dead code detected. Codebase is clean.
      </div>
    );
  }

  const copyRefactor = (item: DeadCodeItem, idx: number) => {
    const prompt = `Refactor and safely remove unused ${item.type || "symbol"} "${item.symbol}" in ${item.path}`;
    navigator.clipboard.writeText(prompt);
    setCopiedIdx(idx);
    setTimeout(() => setCopiedIdx(null), 2500);
  };

  return (
    <div className="subtle-card p-6 space-y-5">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <TrashIcon className="w-5 h-5 text-[#ef4444]" />
            <h2 className="text-lg font-semibold tracking-[-0.04em] text-[var(--text-primary)]">
              Dead code candidates
            </h2>
          </div>
          <p className="mt-1 text-sm text-[var(--text-secondary)]">
            Functions, classes, and variables defined but never referenced — safe cleanup targets.
          </p>
        </div>
        <span className="apple-chip rounded-full px-3 py-1.5 text-xs font-semibold text-[var(--text-secondary)]">
          {deadCode.length} Candidates
        </span>
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        {deadCode.map((item, idx) => (
          <div
            key={idx}
            className="flex items-center justify-between gap-3 rounded-3xl border border-[rgba(15,23,42,0.08)] bg-white/80 p-4 shadow-[0_14px_40px_rgba(15,23,42,0.05)] transition-all hover:-translate-y-0.5 hover:border-[#0071e3]/20 hover:shadow-[0_20px_50px_rgba(15,23,42,0.08)]"
          >
            <div className="min-w-0 flex-1 space-y-1">
              <div className="flex items-center gap-2">
                <span className="truncate text-sm font-semibold tracking-[-0.03em] text-[var(--text-primary)]">
                  {item.symbol}
                </span>
                <span className="rounded-full bg-[#eff6ff] px-2.5 py-0.5 text-[10px] font-semibold uppercase tracking-[0.18em] text-[#0071e3]">
                  {item.type || "symbol"}
                </span>
              </div>
              <div className="truncate text-xs text-[var(--text-secondary)]" title={item.path}>
                {item.path}:{item.line || 1}
              </div>
            </div>

            <div className="flex items-center gap-2">
              <span className="rounded-full bg-[rgba(15,23,42,0.05)] px-2.5 py-0.5 text-[10px] font-semibold uppercase tracking-[0.18em] text-[var(--text-secondary)]">
                {item.confidence || "HIGH"}
              </span>
              <button
                onClick={() => copyRefactor(item, idx)}
                className="rounded-full border border-[rgba(15,23,42,0.08)] bg-white p-2 text-[var(--text-secondary)] transition-all hover:-translate-y-0.5 hover:text-[#0071e3] hover:shadow-sm"
                title="Copy Copilot prompt for this dead code"
              >
                {copiedIdx === idx ? (
                  <CheckIcon className="w-4 h-4 text-[#10b981]" />
                ) : (
                  <Square2StackIcon className="w-4 h-4" />
                )}
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
