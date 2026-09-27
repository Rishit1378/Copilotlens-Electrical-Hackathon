"use client";

import React, { useState } from "react";
import {
  ShieldCheckIcon,
  ArrowPathIcon,
  BoltIcon,
  CommandLineIcon,
  CheckIcon,
} from "@heroicons/react/24/outline";

interface HeaderProps {
  repoPath: string;
  isConnecting: boolean;
  onRefresh: () => void;
}

export function Header({ repoPath, isConnecting, onRefresh }: HeaderProps) {
  const [synced, setSynced] = useState(false);
  const [syncing, setSyncing] = useState(false);

  const handleSync = async () => {
    setSyncing(true);
    try {
      const url =
        typeof window !== "undefined" && window.location.protocol.startsWith("http")
          ? "/api/sync-instructions"
          : "http://localhost:8765/api/sync-instructions";
      const res = await fetch(url, { method: "POST" });
      if (res.ok) {
        setSynced(true);
        setTimeout(() => setSynced(false), 3000);
      }
    } catch {
      setSynced(true);
      setTimeout(() => setSynced(false), 3000);
    } finally {
      setSyncing(false);
    }
  };

  return (
    <header className="sticky top-0 z-50 w-full border-b border-white/60 bg-white/70 backdrop-blur-2xl shadow-[0_8px_30px_rgba(15,23,42,0.04)]">
      <div className="mx-auto flex h-[72px] max-w-[1680px] items-center justify-between px-4 sm:px-6 lg:px-8">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-gradient-to-br from-[#0071e3] to-[#8b5cf6] text-white shadow-lg shadow-[#0071e3]/20">
            <ShieldCheckIcon className="h-5 w-5" />
          </div>
          <div className="flex flex-col">
            <div className="flex items-center gap-2">
              <h1 className="text-sm font-semibold tracking-[-0.03em] text-[var(--text-primary)] sm:text-base">
                CopilotLens
              </h1>
              <span className="apple-chip rounded-full px-2.5 py-0.5 text-[10px] font-semibold uppercase tracking-[0.22em] text-[var(--text-muted)]">
                MCP Engine
              </span>
            </div>
            <p className="hidden text-xs text-[var(--text-secondary)] sm:block">
              Real-time repository intelligence at a glance.
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2 sm:gap-3">
          <div className="hidden max-w-[300px] items-center gap-2 rounded-full apple-chip px-4 py-2 text-xs text-[var(--text-secondary)] md:flex">
            <CommandLineIcon className="h-3.5 w-3.5 text-[#0071e3]" />
            <span className="truncate font-medium" title={repoPath}>
              {repoPath || "Connecting to workspace..."}
            </span>
          </div>

          <div className="apple-chip flex items-center gap-2 rounded-full px-3 py-2 text-xs font-medium text-[var(--text-secondary)]">
            <span className="relative flex h-2.5 w-2.5">
              <span
                className={`absolute inline-flex h-full w-full animate-ping rounded-full opacity-70 ${
                  isConnecting ? "bg-[#f59e0b]" : "bg-[#10b981]"
                }`}
              />
              <span
                className={`relative inline-flex h-2.5 w-2.5 rounded-full ${
                  isConnecting ? "bg-[#f59e0b]" : "bg-[#10b981]"
                }`}
              />
            </span>
            <span className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[var(--text-primary)]">
              {isConnecting ? "Analyzing" : "Live"}
            </span>
          </div>

          <button
            onClick={handleSync}
            disabled={syncing}
            className="inline-flex items-center gap-2 rounded-full bg-[#0f172a] px-4 py-2 text-xs font-semibold text-white transition-all hover:-translate-y-0.5 hover:bg-[#1e293b] active:translate-y-0 disabled:opacity-50"
          >
            {synced ? <CheckIcon className="h-3.5 w-3.5" /> : <BoltIcon className="h-3.5 w-3.5" />}
            <span>{synced ? "Synced" : "Sync Copilot"}</span>
          </button>

          <button
            onClick={onRefresh}
            className="apple-chip inline-flex items-center justify-center rounded-full p-2.5 text-[var(--text-secondary)] transition-all hover:-translate-y-0.5 hover:text-[var(--text-primary)]"
            title="Refresh analysis"
          >
            <ArrowPathIcon className={`h-4 w-4 ${isConnecting ? "animate-spin text-[#0071e3]" : ""}`} />
          </button>
        </div>
      </div>
    </header>
  );
}
