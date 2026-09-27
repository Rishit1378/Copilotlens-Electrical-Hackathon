"use client";

import React from "react";
import { BoltIcon, ShieldCheckIcon, LinkIcon, BeakerIcon, Squares2X2Icon } from "@heroicons/react/24/outline";

interface BlastRadiusSavings {
  token_reduction_multiplier?: string;
  reduction_percentage?: string;
  summary?: string;
}

interface BlastRadiusBreakdown {
  direct_dependents?: string[];
  co_change_partners?: string[];
  associated_tests?: string[];
}

interface BlastRadiusItem {
  targets?: string[];
  blast_radius_breakdown?: BlastRadiusBreakdown;
  token_savings?: BlastRadiusSavings;
  total_files_in_review_set?: number;
  total_repo_files?: number;
}

interface BlastRadiusPanelProps {
  blastData: BlastRadiusItem[];
}

export function BlastRadiusPanel({ blastData }: BlastRadiusPanelProps) {
  if (!blastData || !blastData.length) {
    return (
      <div className="subtle-card p-8 text-center text-[var(--text-secondary)] text-sm font-medium">
        Calculating blast radius context sets...
      </div>
    );
  }

  return (
    <div className="subtle-card p-6 space-y-5">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <BoltIcon className="w-5 h-5 text-[#0071e3]" />
            <h2 className="text-lg font-semibold tracking-[-0.04em] text-[var(--text-primary)]">
              Blast radius & token savings simulator
            </h2>
          </div>
          <p className="mt-1 text-sm text-[var(--text-secondary)]">
            Minimal review context sets for target files — reducing Copilot token waste by up to 100x.
          </p>
        </div>
        <span className="apple-chip rounded-full px-3 py-1.5 text-xs font-semibold text-[var(--text-secondary)]">
          {blastData.length} targets
        </span>
      </div>

      <div className="space-y-4">
        {blastData.map((item, idx) => {
          const target = (item.targets || [])[0] || "Target File";
          const bd = item.blast_radius_breakdown || {};
          const dependents = bd.direct_dependents || [];
          const coChanges = bd.co_change_partners || [];
          const tests = bd.associated_tests || [];
          const savings = item.token_savings || {};

          return (
            <div
              key={idx}
              className="space-y-4 rounded-3xl border border-[rgba(15,23,42,0.08)] bg-white/80 p-4 shadow-[0_14px_40px_rgba(15,23,42,0.05)] transition-all hover:-translate-y-0.5 hover:border-[#0071e3]/20 hover:shadow-[0_20px_50px_rgba(15,23,42,0.08)]"
            >
              <div className="flex flex-col gap-2 border-b border-[rgba(15,23,42,0.08)] pb-3 sm:flex-row sm:items-center sm:justify-between">
                <div className="flex items-center gap-2">
                  <span className="rounded-full bg-[#eff6ff] px-3 py-1 text-[10px] font-semibold uppercase tracking-[0.18em] text-[#0071e3]">
                    Target
                  </span>
                  <span className="truncate text-sm font-semibold tracking-[-0.03em] text-[var(--text-primary)]">
                    {target}
                  </span>
                </div>
                <span className="inline-flex items-center gap-1.5 rounded-full bg-[#f8fbff] px-3 py-1 text-xs font-semibold text-[#0071e3] shadow-sm">
                  <BoltIcon className="w-3.5 h-3.5" />
                  {savings.token_reduction_multiplier || "100x"} token savings ({savings.reduction_percentage || "95%"})
                </span>
              </div>

              <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
                <div className="space-y-2 rounded-2xl border border-[rgba(15,23,42,0.08)] bg-white p-3.5">
                  <div className="flex items-center gap-1.5 text-xs font-semibold text-[var(--text-primary)]">
                    <LinkIcon className="w-3.5 h-3.5 text-[#0071e3]" /> Dependents ({dependents.length})
                  </div>
                  <div className="max-h-24 space-y-1 overflow-y-auto text-xs text-[var(--text-secondary)]">
                    {dependents.length ? (
                      dependents.map((f: string, dIdx: number) => (
                        <div key={dIdx} className="truncate" title={f}>
                          • {f.split("/").pop()}
                        </div>
                      ))
                    ) : (
                      <div className="text-[var(--text-muted)]">None detected</div>
                    )}
                  </div>
                </div>

                <div className="space-y-2 rounded-2xl border border-[rgba(15,23,42,0.08)] bg-white p-3.5">
                  <div className="flex items-center gap-1.5 text-xs font-semibold text-[var(--text-primary)]">
                    <Squares2X2Icon className="w-3.5 h-3.5 text-[#8b5cf6]" /> Co-change files ({coChanges.length})
                  </div>
                  <div className="max-h-24 space-y-1 overflow-y-auto text-xs text-[var(--text-secondary)]">
                    {coChanges.length ? (
                      coChanges.map((f: string, cIdx: number) => (
                        <div key={cIdx} className="truncate" title={f}>
                          • {f.split("/").pop()}
                        </div>
                      ))
                    ) : (
                      <div className="text-[var(--text-muted)]">None detected</div>
                    )}
                  </div>
                </div>

                <div className="space-y-2 rounded-2xl border border-[rgba(15,23,42,0.08)] bg-white p-3.5">
                  <div className="flex items-center gap-1.5 text-xs font-semibold text-[var(--text-primary)]">
                    <BeakerIcon className="w-3.5 h-3.5 text-[#10b981]" /> Tests ({tests.length})
                  </div>
                  <div className="max-h-24 space-y-1 overflow-y-auto text-xs text-[var(--text-secondary)]">
                    {tests.length ? (
                      tests.map((f: string, tIdx: number) => (
                        <div key={tIdx} className="truncate" title={f}>
                          • {f.split("/").pop()}
                        </div>
                      ))
                    ) : (
                      <div className="text-[var(--text-muted)]">None detected</div>
                    )}
                  </div>
                </div>
              </div>

              <div className="flex items-center gap-2 rounded-2xl border border-[#bfdbfe] bg-[#eff6ff] p-3 text-sm text-[var(--text-primary)]">
                <ShieldCheckIcon className="w-4 h-4 shrink-0 text-[#0071e3]" />
                <span>
                  {savings.summary ||
                    `Minimal Review Set: ${item.total_files_in_review_set || 1} files instead of ${item.total_repo_files || 200} full repository files.`}
                </span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
