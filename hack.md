# 🚀 Hackathon: Your Idea, Your Impact

## Event Overview

**Tagline:** *Your Idea, Your Impact*

**Goal:** Demonstrate practical impact and a working demo — not production-ready software.
**Scope:** Realistic, demo-ready.

---

## Focus Areas (Suggested Topics)

- AI Agents and Workflow Automation
- UI/UX Improvements
- Cost Saving Tools or Techniques
- Process or Productivity Enhancements
- Internal Developer Tools
- Automation of Repetitive Tasks

---

## Evaluation Criteria

| Criterion | Description |
|---|---|
| Relevance to Business Case | Does it solve a real problem? |
| Practicality | Is it implementable? |
| Innovation | Is the approach novel? |
| Technical Soundness | Is the implementation well thought out? |
| Demo Clarity | Is the demo easy to understand and compelling? |
| Effective use of Copilot AI | Does it leverage GitHub Copilot meaningfully? |

> 💡 Not about polished production-grade code — about **smart, valuable thinking**.

---

## Deliverables

- ✅ A working prototype
- ✅ A demo
- ✅ An AI agent / automation concept / UI-UX solution / proof of concept
- ✅ A concise presentation

---

## Our Project: CopilotLens for IntelliJ

### Concept

**CopilotLens** — Codebase Intelligence Layer for GitHub Copilot in IntelliJ.

Inspired by [RepoWise](https://github.com/repowise-dev/repowise), but purpose-built for **IntelliJ + GitHub Copilot** via an MCP server.

### Problem We Solve

GitHub Copilot is powerful, but it operates **blind** — it doesn't know:
- Which files are high-risk/hotspots (frequently changed, bug-prone)
- Which code is dead/unused
- The *why* behind architectural decisions
- How modules relate to each other (dependency graph)
- Who owns what (bus factor risk)

This leads to:
- Copilot suggesting changes in risky files without awareness
- Developers accepting suggestions without historical context
- Wasted tokens on irrelevant context

### Our Solution

An **MCP server** that indexes your codebase and exposes rich intelligence directly into **GitHub Copilot's agent mode in IntelliJ**. Copilot can then ask:

- "What's the health score of this file?"
- "Show me hotspots before I refactor"
- "Who owns this module?"
- "Are there any dead code candidates here?"
- "What architectural decisions affect this area?"

Plus a **live dashboard web UI** that visualizes the codebase intelligence in real-time.

### Key Innovation Over RepoWise

1. **IntelliJ-first** — designed specifically for JetBrains IDE + Copilot Agent mode
2. **Copilot-aware prompting** — pre-built Copilot prompt templates that leverage our MCP tools
3. **Real-time risk overlay** — when Copilot suggests a change, we surface the health/risk context
4. **AGENTS.md generation** — auto-generates Copilot workspace instructions based on codebase analysis
5. **Demo-optimized** — a beautiful dashboard that makes the value immediately visible to judges

---

## Tech Stack

| Component | Technology |
|---|---|
| MCP Server | Python (FastMCP / mcp library) |
| Code Analysis | Tree-sitter, GitPython, AST parsing |
| Dashboard UI | HTML/CSS/JS (Vanilla, premium design) |
| IntelliJ Integration | MCP config in `mcp.json` for Copilot |
| Presentation | Interactive HTML slide deck |

---

## Architecture

```
┌─────────────────────────────────────────┐
│           IntelliJ IDEA                 │
│  ┌──────────────────────────────────┐   │
│  │  GitHub Copilot (Agent Mode)     │   │
│  │  + MCP Tools from CopilotLens   │   │
│  └──────────┬───────────────────────┘   │
└─────────────┼───────────────────────────┘
              │ MCP Protocol (stdio/HTTP)
              ▼
┌─────────────────────────────────────────┐
│        CopilotLens MCP Server           │
│                                         │
│  • get_file_health(path)                │
│  • get_hotspots(n)                      │
│  • get_dependency_graph(module)         │
│  • get_dead_code_candidates()           │
│  • get_module_owners()                  │
│  • get_architectural_decisions()        │
│  • generate_copilot_instructions()      │
└──────────────┬──────────────────────────┘
               │
    ┌──────────▼──────────┐
    │  Intelligence Cache  │
    │  (JSON / SQLite)     │
    └──────────┬──────────┘
               │
    ┌──────────▼──────────┐
    │  Codebase Analyzers  │
    │  • Git history       │
    │  • Dependency graph  │
    │  • Code health       │
    │  • Dead code detect  │
    └─────────────────────┘
```

---

## Demo Flow (for Judges)

1. **Open dashboard** → show codebase health overview, hotspots, dead code
2. **Open IntelliJ** → show Copilot Agent mode with CopilotLens tools enabled
3. **Ask Copilot** a natural language question leveraging our MCP tools
4. **Show generated AGENTS.md** → Copilot now has deep context about the codebase
5. **Compare before/after** → Copilot suggestions with vs without CopilotLens context

---

## Files in This Project

```
/
├── hack.md                    # This file — hackathon reference
├── mcp_server/
│   ├── server.py              # Main MCP server
│   ├── analyzers/
│   │   ├── git_analyzer.py    # Git history analytics
│   │   ├── code_health.py     # Code health scoring
│   │   ├── dependency.py      # Dependency graph
│   │   └── dead_code.py       # Dead code detection
│   └── requirements.txt
├── dashboard/
│   ├── index.html             # Main dashboard UI
│   ├── style.css
│   └── app.js
├── demo/
│   ├── presentation.html      # Slide deck
│   └── sample_project/       # Sample repo for demo
└── intellij_setup/
    └── mcp.json               # IntelliJ MCP configuration
```

---

## Notes & Decisions

- Keep the MCP server simple but functional for the demo — not production hardened
- Dashboard should be visually stunning (judges will see it on screen)
- Use a real (but small) codebase for the demo to make it credible
- The "wow moment" is Copilot answering questions it could never answer before
