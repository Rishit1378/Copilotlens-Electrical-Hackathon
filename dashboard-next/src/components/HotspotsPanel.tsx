"use client";

import React from "react";
import { FireIcon, UserIcon } from "@heroicons/react/24/outline";

interface HotspotItem {
  path?: string;
  authors?: string[];
  churn?: number;
  commit_count?: number;
  risk_level?: string;
}

interface HotspotsPanelProps {
  hotspots: HotspotItem[];
}

export function HotspotsPanel({ hotspots }: HotspotsPanelProps) {
  if (!hotspots.length) {
    return (
      <div className="subtle-card h-[520px] p-8 text-center text-[var(--text-secondary)] text-sm font-medium flex items-center justify-center">
        No git hotspots detected. Ensure repo has commit history.
      </div>
    );
  }

  const riskBadge: Record<string, string> = {
    CRITICAL: "bg-[#fff5f5] text-[#dc2626] border-[#fecaca]",
    HIGH: "bg-[#fff7ed] text-[#ea580c] border-[#fed7aa]",
    MEDIUM: "bg-[#eff6ff] text-[#1d4ed8] border-[#bfdbfe]",
    LOW: "bg-white text-[#64748b] border-[rgba(15,23,42,0.08)]",
  };

  return (
    <div className="subtle-card h-[520px] p-6 flex flex-col gap-5">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <FireIcon className="w-5 h-5 text-[#ea580c]" />
            <h2 className="text-lg font-semibold tracking-[-0.04em] text-[var(--text-primary)]">
              Git churn hotspots
            </h2>
          </div>
          <p className="text-sm text-[var(--text-secondary)]">
            Files modified most frequently — the highest defect-risk areas.
          </p>
        </div>
        <span className="apple-chip inline-flex items-center rounded-full px-3 py-1.5 text-xs font-semibold text-[var(--text-secondary)]">
          Top {hotspots.length} files
        </span>
      </div>

      <div className="flex-1 min-h-0 overflow-y-auto pr-1 space-y-3 scrollbar-thin">
        {hotspots.map((item, idx) => (
          <div
            key={`${item.path ?? "hotspot"}-${idx}`}
            className="flex items-center gap-3 rounded-3xl border border-[rgba(15,23,42,0.06)] bg-white/75 p-4 transition-all hover:-translate-y-0.5 hover:border-[#1d4ed8]/20 hover:shadow-[0_18px_50px_rgba(15,23,42,0.08)]"
          >
            <span className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-2xl bg-[#eff6ff] text-sm font-semibold text-[#1d4ed8] shadow-sm">
              #{idx + 1}
            </span>
            <div className="min-w-0 flex-1">
              <div className="truncate text-sm font-semibold tracking-[-0.03em] text-[var(--text-primary)]" title={item.path}>
                {item.path}
              </div>
              <div className="mt-1 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-[var(--text-secondary)]">
                <span className="flex items-center gap-1.5">
                  <UserIcon className="w-3.5 h-3.5 text-[#1d4ed8]" />
                  {item.authors?.slice(0, 2).join(", ") || "Unknown"}
                </span>
                <span>Churn {item.churn || 0} lines</span>
              </div>
            </div>
            <div className="flex shrink-0 items-center gap-3">
              <div className="text-right">
                <span className="block text-sm font-semibold text-[var(--text-primary)]">
                  {item.commit_count || 0}
                </span>
                <span className="text-[10px] uppercase tracking-[0.18em] text-[var(--text-muted)]">
                  commits
                </span>
              </div>
              <span
                className={`rounded-full border px-3 py-1 text-[10px] font-semibold uppercase tracking-[0.18em] ${
                  riskBadge[item.risk_level || "LOW"] || riskBadge.LOW
                }`}
              >
                {item.risk_level || "LOW"}
              </span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
