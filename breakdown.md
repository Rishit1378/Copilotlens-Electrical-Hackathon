# CopilotLens — Project Breakdown

> *"Your Idea, Your Impact"* — Siemens Hackathon

---

## What Is CopilotLens?

CopilotLens is a **codebase intelligence layer** that plugs directly into **GitHub Copilot's Agent mode in IntelliJ**. It gives Copilot the deep, structural, and historical knowledge about a codebase that only a senior engineer would normally have — surfaced instantly through natural language or a local visual dashboard.

It works as an **MCP (Model Context Protocol) server**: a lightweight Python process that runs locally, indexes your repository, and exposes a suite of analytical tools that Copilot can call during a conversation.

---

## The Problem It Solves

GitHub Copilot is one of the most powerful developer tools available, but it has a critical blind spot: **It operates with no memory of your codebase's history, health, or structure.**

When a developer asks Copilot *"how should I refactor this module?"*, Copilot doesn't know:

| What Copilot Doesn't Know | Why It Matters |
|---|---|
| This file has been modified 47 times in 90 days | High churn = high defect probability |
| This function is never called anywhere | It's dead code — safe to delete |
| 3 other modules import this file | Any change has a wide blast radius |
| Only one person has ever touched this file | Bus factor = 1, ask them before changing |
| The file scores 15/100 on health metrics | It's fragile — needs tests before touching |
| These two files are always changed together | Hidden logical coupling (e.g., Android vs iOS hook) |

The result: developers get **generic suggestions** from a tool that doesn't understand their specific codebase. They accept changes that introduce risk. Senior engineers still have to manually review everything.

---

## The Solution: 14 Intelligence Tools

CopilotLens bridges this gap. It runs a background analysis on your repository and exposes **14 intelligence tools** that Copilot can call during Agent mode conversations:

### 🏥 Codebase Health & Structure
1. `get_file_health(path)`: Scores a file 0–100 using 12 markers (nesting, size, complexity, TODOs, comments, etc.).
2. `get_codebase_summary()`: Returns overall codebase grade, distribution, and lists of worst/best files.
3. `get_dependency_graph()`: Extracts file-level import map, identifying hub files, circular dependencies, and orphans.
4. `get_file_dependencies(path)`: Calculates the direct imports and blast radius for a specific file.
5. `get_named_imports(path)`: Parses symbol-level imports (e.g., `{ useState, useEffect }`) rather than just file-level imports.

### 🧹 Code Cleanup & Search
6. `get_dead_code()`: Detects functions and classes defined in the codebase but never referenced.
7. `search_codebase(query)`: Searches across all files with context lines and line numbers using text, regex, or symbols.
8. `find_symbol_usages(symbol)`: Locates where a function/class is defined and all places it is called.

### 👥 Git Archaeology & History
9. `get_hotspots(n)`: Retrieves the top N high-churn, high-risk files from git history.
10. `get_module_owners()`: Computes commit ownership and flags files with a low bus factor (bus factor = 1).
11. `get_why(path)`: Analyzes commit messages and inline decision comments (HACK, TODO, WORKAROUND) to explain the *why* behind code.
12. `get_co_change_pairs()`: Identifies files that always change together (revealing hidden coupling).

### ⚡ Token Savings & Blast Radius
13. `get_blast_radius(file_path)`: **[NEW]** Calculates the minimal review set (direct imports + co-change files + tests) and estimates token savings vs full-repo scans (e.g., 99% / 100x token reduction).

### 📋 Integration
14. `generate_copilot_instructions()`: Auto-writes a `.github/copilot-instructions.md` file to pre-load Copilot with this metadata.

---

## The Visual Dashboard

Alongside the MCP tools, CopilotLens serves a **local web dashboard** at `http://localhost:8765` showing:

1. **Health Overview & Distribution**: Visual graphs showing how many files fall into excellent, good, fair, or critical categories.
2. **Tabbed Analytics**:
   - **🔥 Hotspots**: Ranked list of riskiest files.
   - **🏥 Health**: Specific details on why files score poorly.
   - **🧹 Dead Code**: Clear targets for cleanup.
   - **🔗 Dependencies**: Hubs, orphans, and circular chains.
   - **🔄 Co-Changes**: Visualizing hidden logical coupling.
   - **👥 Ownership**: Contributor lists and bus factor warnings.
3. **Copilot Prompt Templates**: One-click quick prompts to copy pre-formatted questions directly into GitHub Copilot Agent Mode.

---

## 🏢 Enterprise Readiness: Bitbucket & Massive Repositories

### Works with Bitbucket / Any Git Provider
CopilotLens relies **100% on local Git operations** via native CLI commands. 
- It does **not** rely on GitHub API endpoints for data retrieval.
- Works identically on **Bitbucket Server, Bitbucket Cloud, GitLab, and Azure DevOps**.
- Requires **zero external API tokens or internet connection**, adhering strictly to corporate security & IP policies.

### Scaling to Massive Codebases (10,000+ files)
- **On-Demand Single-File Queries**: Specific queries (like `get_why(file)` or `get_file_health(file)`) operate strictly on the target file in **~30ms**.
- **Performance Caps**: Scans cap initial background analysis (e.g. top 200 files by churn, max 500 files for reference graphs) so RAM and CPU stay low.
- **Disk Caching (`.copilotlens_cache.json`)**: Computed analysis is cached locally. Re-fetches take **< 1ms**.

---

## Real Results — Demonstrated on `enatega/food-delivery-multivendor`

We ran CopilotLens against a real open-source codebase containing **2,348 JS/TS/TSX files**:

*   **Overall Health Score**: **74/100 — Grade B**
*   **Worst-scored files**: `super-admin-layout/app-bar/index.tsx` (score **30/100** due to nesting, magic numbers, and file size).
*   **Top Hotspot**: `enatega-multivendor-app/src/apollo/queries.js` (9 commits, the GraphQL query file).
*   **Top Co-Change Pair**: `useCreateAccount.android.js` and `useCreateAccount.ios.js` changed together **8 times** (HIGH coupling).
*   **Symbol-Level Imports**: Discovered `Restaurant.js` imports 33 named symbols directly from libraries and helper files.

---

## How It Maps to the Hackathon Requirements

### Hackathon Theme: *Your Idea, Your Impact*

| Requirement | How CopilotLens Delivers |
|---|---|
| **AI Agents & Workflow Automation** | Exposes MCP tools so Copilot can act as a fully autonomous agent, gathering code intelligence before writing suggestions. |
| **Internal Developer Tools** | Designed specifically to improve developer productivity and make codebase context accessible directly within IntelliJ. |
| **Process & Productivity Enhancements** | Drastically reduces refactoring risk assessment, onboarding time, and code review overhead. |
| **Cost Saving Techniques** | Prevents bad AI suggestions that break code, and limits context token waste by targeting files intelligently. |
| **Automation of Repetitive Tasks** | Auto-generates `.github/copilot-instructions.md` configuration files. |
| **UI/UX Improvements** | Modern, premium dark-mode dashboard with real-time updates and an embedded chat playground. |

### Evaluation Criteria

| Criterion | Our Score | Evidence |
|---|---|---|
| **Relevance to Business Case** | ✅ Strong | Enhances AI developer velocity and reduces defect rates in large, legacy systems. |
| **Practicality** | ✅ Strong | Works out of the box on any git repo. Runs locally with zero dependencies on external APIs. |
| **Innovation** | ✅ Strong | Implements the Model Context Protocol (MCP) to supply metadata to Copilot Agent Mode. |
| **Technical Soundness** | ✅ Strong | Combines regex parsing, git logs, and AST heuristics with a fast cache layer. |
| **Demo Clarity** | ✅ Strong | Pinned simulator chat allows judges to ask questions and see live, structured responses instantly. |
