"use client";

import React, { useEffect, useState, useCallback } from "react";
import { Header } from "../components/Header";
import { MetricsHero } from "../components/MetricsHero";
import { Neo4jCanvas } from "../components/Neo4jCanvas";
import { HotspotsPanel } from "../components/HotspotsPanel";
import { HealthPanel } from "../components/HealthPanel";
import { DeadCodePanel } from "../components/DeadCodePanel";
import { CoChangePanel } from "../components/CoChangePanel";
import { BlastRadiusPanel } from "../components/BlastRadiusPanel";
import { CopilotDrawer } from "../components/CopilotDrawer";
import {
  ChartBarIcon,
  TrashIcon,
  ArrowPathIcon,
  BoltIcon,
} from "@heroicons/react/24/outline";

type SidebarTab = "health" | "deadcode" | "cochange" | "blastradius";

type HealthFile = {
  path?: string;
  score?: number;
  grade?: string;
  lines?: number;
  markers?: Array<{
    desc?: string;
    detail?: string | number;
    impact?: number;
  }>;
};

type HealthSummary = {
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
  worst_files?: HealthFile[];
  best_files?: HealthFile[];
};

type DashboardData = {
  repo_path?: string;
  health?: HealthSummary;
  repo_summary?: {
    total_commits?: number;
    active_contributors_90d?: unknown[];
  };
  dependency_graph?: {
    nodes?: Array<{
      id: string;
      label?: string;
      is_circular?: boolean;
      is_hub?: boolean;
      imported_by_count?: number;
      imports_count?: number;
      centrality?: number;
    }>;
    edges?: Array<{
      source: string;
      target: string;
    }>;
    circular?: string[][];
  };
  hotspots?: Array<{
    path?: string;
    authors?: string[];
    churn?: number;
    commit_count?: number;
    risk_level?: string;
  }>;
  dead_code?: Array<{
    symbol?: string;
    type?: string;
    path?: string;
    line?: number;
    confidence?: string;
  }>;
  co_change_pairs?: Array<{
    file_a?: string;
    file_b?: string;
    co_change_count?: number;
    coupling_strength?: string;
  }>;
  blast_radius?: Array<Record<string, unknown>>;
  status?: string;
};

export default function DashboardPage() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [sidebarTab, setSidebarTab] = useState<SidebarTab>("health");

  const fetchData = useCallback(async () => {
    try {
      const url =
        typeof window !== "undefined" && window.location.protocol.startsWith("http")
          ? "/api/data"
          : "http://localhost:8765/api/data";
      const res = await fetch(url);
      if (!res.ok) throw new Error("API Offline");
      const json = (await res.json()) as DashboardData;

      if (json.status === "loading") {
        setLoading(true);
        return;
      }

      setData(json);
      setLoading(false);
    } catch {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const initialLoad = window.setTimeout(() => {
      void fetchData();
    }, 0);
    const interval = setInterval(fetchData, 15000);
    return () => {
      window.clearTimeout(initialLoad);
      clearInterval(interval);
    };
  }, [fetchData]);

  const sidebarTabs: Array<{ id: SidebarTab; label: string; icon: React.ComponentType<{ className?: string }> }> = [
    { id: "health", label: "Code Quality", icon: ChartBarIcon },
    { id: "deadcode", label: "Dead Code", icon: TrashIcon },
    { id: "cochange", label: "Co-Changes", icon: ArrowPathIcon },
    { id: "blastradius", label: "Blast Radius", icon: BoltIcon },
  ];

  const health = data?.health || {};
  const repoSummary = data?.repo_summary || {};
  const hotspots = data?.hotspots || [];
  const dependencyGraph = data?.dependency_graph || {};
  const deadCode = data?.dead_code || [];
  const coChangePairs = data?.co_change_pairs || [];
  const blastRadius = data?.blast_radius || [];

  const repoStats = [
    {
      label: "Scored files",
      value: `${health?.total_files ?? 0}`,
      meta: health?.grade ? `Grade ${health.grade}` : "Waiting for analysis",
    },
    {
      label: "Hotspots",
      value: `${hotspots.length}`,
      meta: hotspots.length ? "Active churn zones" : "No churn detected yet",
    },
    {
      label: "Review sets",
      value: `${blastRadius.length}`,
      meta: blastRadius.length ? "Minimal context ready" : "Calculating",
    },
  ];

  return (
    <div className="relative min-h-screen overflow-hidden flex flex-col pb-28 selection:bg-[#0071e3]/20 selection:text-[#0f172a]">
      <div className="pointer-events-none absolute inset-0 soft-grid opacity-50" />
      <div className="pointer-events-none absolute -top-24 left-[-12%] h-80 w-80 rounded-full bg-[#0071e3]/12 blur-3xl" />
      <div className="pointer-events-none absolute top-36 right-[-8%] h-96 w-96 rounded-full bg-[#8b5cf6]/10 blur-3xl" />

      <Header
        repoPath={data?.repo_path || "C:\\CoPilotLens\\"}
        isConnecting={loading}
        onRefresh={fetchData}
      />

      <main className="relative z-10 w-full max-w-[1680px] mx-auto px-4 sm:px-6 lg:px-8 pt-6 lg:pt-8 space-y-6 flex-1">
        <section className="subtle-card overflow-hidden px-6 py-6 sm:px-8 lg:px-10">
          <div className="flex flex-col gap-6 lg:flex-row lg:items-end lg:justify-between">
            <div className="max-w-3xl space-y-4">
              <div className="flex flex-wrap items-center gap-2">
                <span className="apple-chip inline-flex items-center gap-2 rounded-full px-3 py-1 text-xs font-semibold text-[var(--text-secondary)]">
                  <span className={`h-2 w-2 rounded-full ${loading ? "bg-[#f59e0b] animate-pulse" : "bg-[#10b981]"}`} />
                  {loading ? "Refreshing live analysis" : "Live repository intelligence"}
                </span>
                <span className="apple-chip inline-flex items-center rounded-full px-3 py-1 text-xs font-semibold text-[#0071e3]">
                  {data?.repo_path ? "Connected" : "Connecting to workspace"}
                </span>
              </div>

              <div className="space-y-3">
                <p className="text-xs font-semibold uppercase tracking-[0.28em] text-[var(--text-muted)]">
                  CopilotLens command center
                </p>
                <h1 className="text-4xl sm:text-5xl lg:text-6xl font-semibold tracking-[-0.055em] text-[var(--text-primary)]">
                  Elegant code intelligence,
                  <span className="block bg-gradient-to-r from-[#0071e3] via-[#2997ff] to-[#8b5cf6] bg-clip-text text-transparent">
                    designed for deep focus.
                  </span>
                </h1>
                <p className="max-w-2xl text-sm sm:text-base leading-7 text-[var(--text-secondary)]">
                  Explore code health, churn hotspots, dependency flow, and safe refactoring context in a calm, high-signal interface inspired by the clarity of Apple’s product design.
                </p>
              </div>

              <div className="flex flex-wrap gap-3 text-xs text-[var(--text-secondary)]">
                <span className="apple-chip rounded-full px-3 py-1.5 font-medium">
                  Repository: {data?.repo_path || "C:\\CoPilotLens\\"}
                </span>
                <span className="apple-chip rounded-full px-3 py-1.5 font-medium">
                  {repoSummary?.total_commits ?? 0} commits tracked
                </span>
                <span className="apple-chip rounded-full px-3 py-1.5 font-medium">
                  {repoSummary?.active_contributors_90d?.length ?? 0} active contributors
                </span>
              </div>
            </div>

            <div className="grid w-full gap-3 sm:grid-cols-3 lg:w-[30rem]">
              {repoStats.map((item) => (
                <div key={item.label} className="subtle-card px-4 py-4">
                  <div className="text-[11px] font-semibold uppercase tracking-[0.24em] text-[var(--text-muted)]">
                    {item.label}
                  </div>
                  <div className="mt-3 text-3xl font-semibold tracking-[-0.05em] text-[var(--text-primary)]">
                    {item.value}
                  </div>
                  <div className="mt-1 text-xs text-[var(--text-secondary)]">
                    {item.meta}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* Metrics Hero Bar */}
        <MetricsHero
          health={health}
          repoSummary={repoSummary}
        />

        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
          <div className="lg:col-span-7 space-y-6">
            <Neo4jCanvas
              depGraph={dependencyGraph}
              hotspots={hotspots}
            />

            <HotspotsPanel hotspots={hotspots} />
          </div>

          <div className="lg:col-span-5 space-y-5 lg:sticky lg:top-24 self-start">
            <div className="flex items-center gap-1.5 p-1.5 rounded-2xl apple-chip overflow-x-auto">
              {sidebarTabs.map((tab) => {
                const Icon = tab.icon;
                const isActive = sidebarTab === tab.id;
                return (
                  <button
                    key={tab.id}
                    onClick={() => setSidebarTab(tab.id)}
                    className={`flex items-center gap-2 px-4 py-2.5 rounded-full text-xs font-semibold transition-all shrink-0 ${
                      isActive
                        ? "bg-[#0f172a] text-white shadow-lg shadow-slate-900/15"
                        : "text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-white/70"
                    }`}
                  >
                    <Icon className={`w-4 h-4 ${isActive ? "text-white" : "text-[#64748b]"}`} />
                    <span>{tab.label}</span>
                  </button>
                );
              })}
            </div>

            {sidebarTab === "health" && <HealthPanel health={health} />}
            {sidebarTab === "deadcode" && <DeadCodePanel deadCode={deadCode} />}
            {sidebarTab === "cochange" && <CoChangePanel coChangePairs={coChangePairs} />}
            {sidebarTab === "blastradius" && <BlastRadiusPanel blastData={blastRadius} />}
          </div>
        </div>

        <section className="subtle-card px-6 py-5 flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.24em] text-[var(--text-muted)]">
              Command surface
            </p>
            <h2 className="mt-2 text-lg font-semibold tracking-[-0.04em] text-[var(--text-primary)]">
              Copy ready-made Copilot prompts, jump into a refactor, or inspect high-risk areas.
            </h2>
          </div>
          <div className="text-sm text-[var(--text-secondary)] max-w-2xl">
            The dashboard is tuned for quick scanning, elegant depth, and fast action—so the highest-value code intelligence is always one click away.
          </div>
        </section>
      </main>

      <CopilotDrawer />
    </div>
  );
}
