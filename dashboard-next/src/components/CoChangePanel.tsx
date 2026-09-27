"use client";

import React from "react";
import { ArrowPathIcon } from "@heroicons/react/24/outline";

interface CoChangePair {
  file_a?: string;
  file_b?: string;
  co_change_count?: number;
  coupling_strength?: string;
}

interface CoChangePanelProps {
  coChangePairs: CoChangePair[];
}

export function CoChangePanel({ coChangePairs }: CoChangePanelProps) {
  if (!coChangePairs || !coChangePairs.length) {
    return (
      <div className="subtle-card p-8 text-center text-[var(--text-secondary)] text-sm font-medium">
        No co-change pairs detected in git history.
      </div>
    );
  }

  const strengthBadge: Record<string, string> = {
    HIGH: "bg-[#fff5f5] text-[#dc2626] border-[#fecaca]",
    MEDIUM: "bg-[#eff6ff] text-[#0071e3] border-[#bfdbfe]",
    LOW: "bg-white text-[#64748b] border-[rgba(15,23,42,0.08)]",
  };

  return (
    <div className="subtle-card p-6 space-y-5">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <ArrowPathIcon className="w-5 h-5 text-[#0071e3]" />
            <h2 className="text-lg font-semibold tracking-[-0.04em] text-[var(--text-primary)]">
              Hidden git co-change coupling
            </h2>
          </div>
          <p className="mt-1 text-sm text-[var(--text-secondary)]">
            File pairs consistently modified together — behavioral coupling without direct imports.
          </p>
        </div>
        <span className="apple-chip rounded-full px-3 py-1.5 text-xs font-semibold text-[var(--text-secondary)]">
          {coChangePairs.length} Pairs
        </span>
      </div>

      <div className="space-y-3.5">
        {coChangePairs.map((pair, idx) => {
          const strength = pair.coupling_strength ?? "LOW";
          return (
            <div
              key={idx}
              className="flex flex-col gap-3 rounded-3xl border border-[rgba(15,23,42,0.08)] bg-white/80 p-4 shadow-[0_14px_40px_rgba(15,23,42,0.05)] transition-all hover:-translate-y-0.5 hover:border-[#0071e3]/20 hover:shadow-[0_20px_50px_rgba(15,23,42,0.08)] sm:flex-row sm:items-center sm:justify-between"
            >
              <div className="flex min-w-0 flex-1 flex-col gap-2 text-sm sm:flex-row sm:items-center">
                <span className="truncate font-semibold tracking-[-0.03em] text-[var(--text-primary)]" title={pair.file_a}>
                  {pair.file_a}
                </span>
                <span className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[#0071e3]">
                  ↔ co-changed
                </span>
                <span className="truncate font-semibold tracking-[-0.03em] text-[var(--text-primary)]" title={pair.file_b}>
                  {pair.file_b}
                </span>
              </div>

              <div className="flex shrink-0 items-center gap-3">
                <div className="text-right">
                  <span className="block text-sm font-semibold text-[var(--text-primary)]">
                    {pair.co_change_count}
                  </span>
                  <span className="text-[10px] uppercase tracking-[0.18em] text-[var(--text-muted)]">
                    commits
                  </span>
                </div>
                <span
                  className={`rounded-full border px-3 py-1 text-[10px] font-semibold uppercase tracking-[0.18em] ${
                    strengthBadge[strength] || strengthBadge.LOW
                  }`}
                >
                  {strength}
                </span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
