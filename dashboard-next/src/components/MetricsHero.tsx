"use client";

import React from "react";

interface MetricsHeroProps {
  health: {
    avg_score?: number;
    grade?: string;
    total_files?: number;
    distribution?: {
      critical?: number;
      poor?: number;
      fair?: number;
      good?: number;
      excellent?: number;
    };
  };
  repoSummary: {
    total_commits?: number;
    active_contributors_90d?: unknown[];
  };
}

export function MetricsHero({ health, repoSummary }: MetricsHeroProps) {
  const score = health.avg_score ?? 0;
  const grade = health.grade ?? "?";
  const dist = health.distribution ?? {};
  const totalFiles = health.total_files ?? 0;
  const commits = repoSummary.total_commits ?? 0;
  const contributors = repoSummary.active_contributors_90d?.length ?? 0;

  const ringColor =
    score >= 85 ? "#10b981" : score >= 70 ? "#0071e3" : score >= 50 ? "#f59e0b" : "#ef4444";

  return (
    <div className="grid grid-cols-1 gap-5 xl:grid-cols-3">
      <div className="subtle-card xl:col-span-2 overflow-hidden p-6 sm:p-7">
        <div className="flex flex-col gap-6 xl:flex-row xl:items-center xl:justify-between">
          <div className="flex items-center gap-6">
            <div className="relative flex shrink-0 items-center justify-center">
              <svg className="h-28 w-28 -rotate-90 sm:h-32 sm:w-32">
                <circle
                  cx="64"
                  cy="64"
                  r="50"
                  stroke="rgba(15,23,42,0.08)"
                  strokeWidth="8"
                  fill="transparent"
                />
                <circle
                  cx="64"
                  cy="64"
                  r="50"
                  stroke={ringColor}
                  strokeWidth="8"
                  strokeDasharray={314}
                  strokeDashoffset={314 - (314 * score) / 100}
                  strokeLinecap="round"
                  fill="transparent"
                  className="transition-all duration-1000 ease-out"
                />
              </svg>
              <div className="absolute flex flex-col items-center justify-center text-center">
                <span className="text-3xl font-semibold tracking-[-0.06em] text-[var(--text-primary)]">
                  {score}
                </span>
                <span className="mt-0.5 text-[10px] font-semibold uppercase tracking-[0.24em] text-[var(--text-muted)]">
                  Health
                </span>
              </div>
            </div>

            <div className="space-y-3">
              <div className="flex flex-wrap items-center gap-2">
                <span className="apple-chip rounded-full px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.22em] text-[var(--text-muted)]">
                  Codebase health index
                </span>
                <span className="rounded-full bg-[#0f172a] px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.18em] text-white">
                  Grade {grade}
                </span>
              </div>
              <h2 className="text-2xl font-semibold tracking-[-0.05em] text-[var(--text-primary)] sm:text-3xl">
                {dist.critical ? "A few high-priority files need attention." : "Your codebase is in strong shape."}
              </h2>
              <p className="max-w-xl text-sm leading-7 text-[var(--text-secondary)]">
                {dist.critical
                  ? `${dist.critical} file${dist.critical === 1 ? "" : "s"} are currently in a critical state and should be reviewed first.`
                  : "The repository is broadly healthy, with balanced distribution and stable maintainability signals."}
              </p>
            </div>
          </div>

          <div className="grid gap-3 sm:grid-cols-2 xl:w-[22rem]">
            <div className="rounded-3xl border border-white/70 bg-white/70 p-4 shadow-[0_12px_40px_rgba(15,23,42,0.05)]">
              <div className="text-[11px] font-semibold uppercase tracking-[0.22em] text-[var(--text-muted)]">
                Files scored
              </div>
              <div className="mt-3 text-3xl font-semibold tracking-[-0.05em] text-[var(--text-primary)]">
                {totalFiles}
              </div>
              <div className="mt-1 text-xs text-[var(--text-secondary)]">
                Deterministic checks across the repository.
              </div>
            </div>

            <div className="rounded-3xl border border-white/70 bg-white/70 p-4 shadow-[0_12px_40px_rgba(15,23,42,0.05)]">
              <div className="text-[11px] font-semibold uppercase tracking-[0.22em] text-[var(--text-muted)]">
                Commit signal
              </div>
              <div className="mt-3 text-3xl font-semibold tracking-[-0.05em] text-[var(--text-primary)]">
                {commits}
              </div>
              <div className="mt-1 text-xs text-[var(--text-secondary)]">
                {contributors} active contributors in the last 90 days.
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="subtle-card p-6 sm:p-7">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-base font-semibold tracking-[-0.04em] text-[var(--text-primary)]">
              Distribution breakdown
            </h3>
            <p className="mt-1 text-xs text-[var(--text-secondary)]">
              Health bands across the repository.
            </p>
          </div>
          <span className="apple-chip rounded-full px-3 py-1 text-[11px] font-semibold text-[var(--text-secondary)]">
            {totalFiles} total
          </span>
        </div>

        <div className="mt-5 space-y-3">
          {[
            { label: "Critical (<30)", count: dist.critical ?? 0, color: "from-[#ef4444] to-[#f97316]" },
            { label: "Poor (30-49)", count: dist.poor ?? 0, color: "from-[#f97316] to-[#f59e0b]" },
            { label: "Fair (50-69)", count: dist.fair ?? 0, color: "from-[#f59e0b] to-[#84cc16]" },
            { label: "Good (70-84)", count: dist.good ?? 0, color: "from-[#0071e3] to-[#60a5fa]" },
            { label: "Excellent (85+)", count: dist.excellent ?? 0, color: "from-[#10b981] to-[#34d399]" },
          ].map((item) => {
            const pct = totalFiles > 0 ? Math.round((item.count / totalFiles) * 100) : 0;
            return (
              <div key={item.label} className="space-y-1.5">
                <div className="flex items-center justify-between text-xs">
                  <span className="font-medium text-[var(--text-secondary)]">{item.label}</span>
                  <span className="font-semibold text-[var(--text-primary)]">{item.count}</span>
                </div>
                <div className="h-2 overflow-hidden rounded-full bg-[rgba(15,23,42,0.06)]">
                  <div
                    className={`h-full rounded-full bg-gradient-to-r ${item.color} transition-all duration-500`}
                    style={{ width: `${pct}%` }}
                  />
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
