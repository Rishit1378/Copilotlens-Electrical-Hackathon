"use client";

import React, { useState } from "react";
import { SparklesIcon, Square2StackIcon, CheckIcon } from "@heroicons/react/24/outline";

export function CopilotDrawer() {
  const [copiedPrompt, setCopiedPrompt] = useState<string | null>(null);

  const prompts = [
    { label: "🔥 Show hotspots", prompt: "What are the top hotspots in this codebase and why are they risky?", recommended: true },
    { label: "⚡ Blast Radius & Savings", prompt: "Calculate the blast radius and minimal review set for mcp_server/server.py" },
    { label: "🏥 Refactor Plan", prompt: "Generate a safe refactoring plan for the lowest-scored file in this codebase" },
    { label: "🧹 Dead Code Cleanup", prompt: "Find all dead code candidates and suggest which ones to remove first" },
    { label: "🔄 Co-change Pairs", prompt: "What are the co-change pairs with high coupling in this repo?" },
    { label: "📋 Gen Instructions", prompt: "Generate the copilot-instructions.md file for this repository" },
  ];

  const handleCopy = (promptText: string) => {
    navigator.clipboard.writeText(promptText);
    setCopiedPrompt(promptText);
    setTimeout(() => setCopiedPrompt(null), 2500);
  };

  return (
    <div className="fixed bottom-4 left-1/2 z-40 w-[min(96vw,1180px)] -translate-x-1/2 px-3 sm:px-0">
      <div className="rounded-[28px] border border-white/70 bg-white/80 px-4 py-4 shadow-[0_22px_70px_rgba(15,23,42,0.14)] backdrop-blur-2xl sm:px-5">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.22em] text-[var(--text-secondary)] shrink-0">
            <div className="flex h-8 w-8 items-center justify-center rounded-2xl bg-gradient-to-br from-[#0071e3] to-[#8b5cf6] text-white shadow-lg shadow-[#0071e3]/20">
              <SparklesIcon className="w-4 h-4" />
            </div>
            <span>Copilot prompts</span>
          </div>

          <div className="flex items-center gap-2 overflow-x-auto pb-0.5 scrollbar-none">
            {prompts.map((p) => {
              const isRec = p.recommended;
              return (
                <button
                  key={p.label}
                  onClick={() => handleCopy(p.prompt)}
                  className={`inline-flex shrink-0 items-center gap-2 rounded-full px-4 py-2 text-xs font-semibold transition-all active:scale-95 ${
                    isRec
                      ? "bg-[#0f172a] text-white shadow-lg shadow-slate-900/10 hover:-translate-y-0.5"
                      : "border border-[rgba(15,23,42,0.08)] bg-white text-[var(--text-primary)] hover:-translate-y-0.5 hover:border-[#0071e3]/20 hover:text-[#0071e3]"
                  }`}
                >
                  <span>{p.label}</span>
                  {copiedPrompt === p.prompt ? (
                    <CheckIcon className={`w-3.5 h-3.5 ${isRec ? "text-white" : "text-[#10b981]"}`} />
                  ) : (
                    <Square2StackIcon className={`w-3.5 h-3.5 ${isRec ? "text-white/80" : "text-[var(--text-muted)]"}`} />
                  )}
                </button>
              );
            })}
          </div>

          <div className="hidden text-xs text-[var(--text-secondary)] lg:block">
            Click any prompt to copy it instantly into your clipboard.
          </div>
        </div>
      </div>
    </div>
  );
}
