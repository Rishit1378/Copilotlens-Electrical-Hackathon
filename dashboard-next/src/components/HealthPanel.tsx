"use client";

import React from "react";
import { CheckCircleIcon, ExclamationCircleIcon, ChartBarIcon } from "@heroicons/react/24/outline";

interface HealthMarker {
  desc?: string;
  detail?: string | number;
  impact?: number;
}

interface HealthFile {
  path?: string;
  score?: number;
  grade?: string;
  lines?: number;
  markers?: HealthMarker[];
}

interface HealthPanelProps {
  health: {
    worst_files?: HealthFile[];
    best_files?: HealthFile[];
  };
}

export function HealthPanel({ health }: HealthPanelProps) {
  const worst = health.worst_files || [];
  const best = health.best_files || [];
  const files = worst.length ? worst : best;

  if (!files.length) {
    return (
      <div className="subtle-card p-8 text-center text-[var(--text-secondary)] text-sm font-medium">
        No scored files available.
      </div>
    );
  }

  return (
    <div className="subtle-card p-6 space-y-5">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <ChartBarIcon className="w-5 h-5 text-[#0071e3]" />
            <h2 className="text-lg font-semibold tracking-[-0.04em] text-[var(--text-primary)]">
              Deterministic code quality
            </h2>
          </div>
          <p className="mt-1 text-sm text-[var(--text-secondary)]">
            Files are scored 0–100 using static quality rules. Lower scores should be reviewed first.
          </p>
        </div>
        <span className="apple-chip rounded-full px-3 py-1.5 text-xs font-semibold text-[var(--text-secondary)]">
          {files.length} files surfaced
        </span>
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        {files.map((f, idx) => {
          const score = f.score ?? 0;
          const grade = f.grade ?? "?";
          const markers = f.markers || [];
          const bad = markers.filter((m) => (m.impact ?? 0) < 0);
          const good = markers.filter((m) => (m.impact ?? 0) > 0);

          const isCritical = score < 50;
          const isWarning = score >= 50 && score < 70;

          const cardBg = isCritical
            ? "border-[#ef4444]/20 bg-[#fff5f5] hover:border-[#ef4444]/40"
            : isWarning
            ? "border-[#f59e0b]/20 bg-[#fffbeb] hover:border-[#f59e0b]/40"
            : "border-[#0071e3]/15 bg-[#f8fbff] hover:border-[#0071e3]/35";

          const barColor = isCritical
            ? "bg-gradient-to-r from-[#ef4444] to-[#f97316]"
            : isWarning
            ? "bg-gradient-to-r from-[#f59e0b] to-[#f97316]"
            : score >= 85
            ? "bg-gradient-to-r from-[#10b981] to-[#34d399]"
            : "bg-gradient-to-r from-[#0071e3] to-[#60a5fa]";

          return (
            <div
              key={idx}
              className={`group rounded-3xl border p-4 shadow-[0_16px_44px_rgba(15,23,42,0.05)] transition-all hover:-translate-y-1 hover:shadow-[0_24px_60px_rgba(15,23,42,0.08)] ${cardBg}`}
            >
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0 space-y-1">
                  <div className="truncate text-sm font-semibold tracking-[-0.03em] text-[var(--text-primary)]" title={f.path}>
                    {f.path}
                  </div>
                  <div className="text-xs text-[var(--text-secondary)]">
                    {f.lines || 0} total lines
                  </div>
                </div>

                <div className="flex shrink-0 items-center gap-2">
                  <span className="text-lg font-semibold tracking-[-0.04em] text-[var(--text-primary)]">
                    {score}
                  </span>
                  <span className="rounded-full bg-white px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.18em] text-[var(--text-secondary)] shadow-sm">
                    {grade}
                  </span>
                </div>
              </div>

              <div className="h-2 w-full overflow-hidden rounded-full bg-white/80">
                <div
                  className={`h-full rounded-full transition-all duration-500 ${barColor}`}
                  style={{ width: `${score}%` }}
                />
              </div>

              <div className="space-y-2 pt-1 text-xs">
                {bad.slice(0, 2).map((m: HealthMarker, mIdx: number) => (
                  <div key={mIdx} className="flex items-center gap-2 text-[#dc2626]">
                    <ExclamationCircleIcon className="w-4 h-4 shrink-0" />
                    <span className="truncate font-medium">
                      {m.desc} ({m.detail || m.impact})
                    </span>
                  </div>
                ))}
                {good.slice(0, 1).map((m: HealthMarker, mIdx: number) => (
                  <div key={mIdx} className="flex items-center gap-2 text-[#059669]">
                    <CheckCircleIcon className="w-4 h-4 shrink-0" />
                    <span className="truncate font-medium">{m.desc}</span>
                  </div>
                ))}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
