# CopilotLens MCP — Complete Feature Matrix & Architectural Guide 🔍

> **CopilotLens** is an enterprise-grade Model Context Protocol (MCP) server that empowers GitHub Copilot (Agent Mode) and developers with deep, structural codebase intelligence, static application security testing (Coverity SAST), health scoring, hotspot detection, dependency graphs, smart test recommendation, and policy synchronization.

---

## 📋 Table of Contents
1. [Coverity Scan & SAST Rules Engine](#1-coverity-scan--sast-rules-engine)
2. [Deterministic Code Health Scorer](#2-deterministic-code-health-scorer)
3. [Git History & Hotspot Heatmap Analyzer](#3-git-history--hotspot-heatmap-analyzer)
4. [Multi-Language AST Adapters & Symbol Extraction](#4-multi-language-ast-adapters--symbol-extraction)
5. [AST-Based Dead Code & Unused Symbol Detector](#5-ast-based-dead-code--unused-symbol-detector)
6. [Dependency Intelligence & Graph Engine](#6-dependency-intelligence--graph-engine)
7. [Multi-Hop Codebase Knowledge Graph](#7-multi-hop-codebase-knowledge-graph)
8. [Blast Radius & Token Savings Calculator](#8-blast-radius--token-savings-calculator)
9. [Smart Test Recommendation & Trace Distiller](#9-smart-test-recommendation--trace-distiller)
10. [Policy Repository & Copilot Conventions Sync](#10-policy-repository--copilot-conventions-sync)
11. [Natural Language "Why" Codebase Engine](#11-natural-language-why-codebase-engine)
12. [Fast Codebase Search Engine](#12-fast-codebase-search-engine)
13. [Interactive Visual Dashboards](#13-interactive-visual-dashboards)
14. [Complete MCP Tools Reference](#14-complete-mcp-tools-reference)
15. [Quick Start & Setup Guide](#15-quick-start--setup-guide)

---

## 1. Coverity Scan & SAST Rules Engine

### Overview
Integrates **Coverity Static Application Security Testing (SAST)** rule checks into CopilotLens. It parses, scans, stores, and exposes Coverity rule failures, CIDs, line numbers, severity levels, trace events, and Copilot remediation advice.

### Key Capabilities
- **JSON Storage & Persistence**: Saves scan findings into `coverity_findings.json` in the workspace root.
- **Coverity Format Compatibility**: Parses standard Coverity CLI exports (`cov-format-errors --json-output-v8`), Coverity Desktop output, and custom JSON rule reports.
- **Supported Checker Rules**:
  - `RESOURCE_LEAK`: Unclosed file streams, sockets, DB connections.
  - `NULL_RETURNS`: Dereferencing function returns without null guards.
  - `FORWARD_NULL`: Explicit null pointer dereferences.
  - `UNINIT`: Variables declared without initialization.
  - `OVERRUN`: Array or buffer index out-of-bounds access.
  - `TAINTED_DATA`: Unsanitized external inputs into dynamic evaluators or commands.
  - `USE_AFTER_FREE`: Memory access after pointer free.
  - `INTEGER_OVERFLOW`: Numeric calculations without overflow guards.
  - `DEADCODE`: Unreachable logic branches.
- **Automated Copilot Fix Prompts**: Every defect includes a custom Copilot prompt explaining how to refactor and resolve the issue.
- **Rule Compliance Score (0–100%)**: Computes an aggregate security compliance grade based on High, Medium, and Low severity defects.

### Exposed MCP Tools
- `get_coverity_findings(file_path, severity)`: Get Coverity CIDs, failing rules, line numbers, and remediation guidance.
- `get_coverity_summary()`: Get overall Coverity security compliance score, defect breakdown by severity/checker, and affected files count.
- `import_coverity_json(json_content_or_path)`: Import external Coverity JSON reports into the workspace.
- `run_coverity_scan()`: Run static rule analysis across workspace files and write to `coverity_findings.json`.

---

## 2. Deterministic Code Health Scorer

### Overview
Evaluates any codebase source file on a **0 to 100 score** and letter grade (**A, B, C, D, F**) using non-LLM, deterministic rules.

### Key Capabilities
- **13 Weighted Quality Markers**:
  - `file_too_large` (-20 pts): Exceeds 500 lines of code.
  - `very_large_file` (-10 pts): Exceeds 300 lines of code.
  - `too_many_todos` (-10 pts): More than 5 TODO/FIXME/HACK comments.
  - `no_comments` (-10 pts): Zero documentation or comment lines.
  - `deeply_nested` (-15 pts): Nesting depth exceeding 4 indent levels.
  - `long_functions` (-15 pts): Functions exceeding 50 lines.
  - `high_complexity` (-15 pts): High cyclomatic branching complexity.
  - `magic_numbers` (-5 pts): Hardcoded literal constants.
  - `coverity_rule_failure` (-25 pts): Active Coverity SAST rule violations.
  - `good_comment_ratio` (+10 pts): Documentation ratio > 10%.
  - `short_file` (+5 pts): Concise, focused module.
  - `has_tests` (+10 pts): Test/spec module.
  - `consistent_style` (+5 pts): Consistent formatting.
- **Multi-Language Support**: Python, Java, JavaScript, TypeScript, JSX, TSX, C#, Go, C/C++, Kotlin, Swift, Scala, PHP, Ruby.

### Exposed MCP Tools
- `get_file_health(file_path)`: Score a specific file and return actionable Copilot refactoring advice.
- `get_codebase_summary()`: Aggregate health summary across all codebase files.

---

## 3. Git History & Hotspot Heatmap Analyzer

### Overview
Analyzes git repository commits, author activity, churn frequency, and module ownership to flag high-risk areas.

### Key Capabilities
- **Hotspots Detection**: Combines high commit churn with low file health scores to highlight high-risk files.
- **Co-Change Coupling Pairs**: Identifies files that frequently change together in commits, exposing hidden architectural coupling even when explicit imports are missing.
- **Module Ownership & Bus Factor**: Aggregates git blame data per module to identify single-contributor risks (bus factor = 1).

### Exposed MCP Tools
- `get_hotspots(limit)`: Top N high-churn / risky files requiring extra care.
- `get_module_owners()`: Module ownership breakdown aggregated by git commit authors.

---

## 4. Multi-Language AST Adapters & Symbol Extraction

### Overview
Provides concrete AST (Abstract Syntax Tree) adapters leveraging Python's native `ast` module and `Tree-sitter` for JavaScript, TypeScript, and Java.

### Key Capabilities
- **Symbol Extraction**: Extracts functions, methods, classes, global variables, imports, and exports.
- **Visibility Classification**: Categorizes symbols into `public`, `private`, or `protected`.
- **Signature & Location**: Captures exact line numbers, parameters, and decorators/annotations.

---

## 5. AST-Based Dead Code & Unused Symbol Detector

### Overview
Discovers unused functions, methods, and classes by comparing declared AST symbols against invocation sites across all repository files.

### Key Capabilities
- **Two-Tier Classification**:
  - `CONFIRMED_ISSUE`: Private helper functions/methods declared with zero references anywhere in the codebase.
  - `HEURISTIC_CANDIDATE`: Public/exported symbols with no internal calls (may be external API endpoints).
- **Cleanup Advice**: Gives Copilot precise instructions on how to safely prune dead code without breaking contracts.

### Exposed MCP Tool
- `get_dead_code()`: Returns sorted candidates for dead code cleanup.

---

## 6. Dependency Intelligence & Graph Engine

### Overview
Parses import statements across Python, JS/TS, and Java modules to build a structural dependency map.

### Key Capabilities
- **Hub File Detection**: Identifies central modules imported by many other files.
- **Orphan File Detection**: Identifies isolated files with no inbound or outbound dependencies.
- **Circular Dependency Analysis**: Detects circular import loops that degrade build stability and code modularity.

### Exposed MCP Tools
- `get_dependency_graph()`: Complete import dependency node and edge graph.
- `get_file_dependencies(file_path)`: Direct inbound and outbound dependencies for a specific file.

---

## 7. Multi-Hop Codebase Knowledge Graph

### Overview
Synthesizes structural dependencies, AST symbols, git history metrics, and policy conventions into an in-memory graph.

### Key Capabilities
- **Multi-Hop Traversal**: Traverses node connections (File -> Symbol -> Dependent File -> Commit Churn).
- **Connected Subgraph Querying**: Fetches localized contextual subgraphs surrounding any target file.

---

## 8. Blast Radius & Token Savings Calculator

### Overview
Calculates the historical and architectural "ripple effect" of modifying a target file.

### Key Capabilities
- **Minimal Review Context Set**: Selects only the essential 3-5 connected files needed when modifying a file, avoiding dumping whole directories into Copilot context.
- **Up to 100x Token Savings**: Prevents LLM context window overflow and speeds up Copilot response times.

---

## 9. Smart Test Recommendation & Trace Distiller

### Overview
Recommends the minimal test suite to run after modifying specific files and cleans test failure logs.

### Key Capabilities
- **Minimal Test Selection**: Uses AST imports and dependency graphs to pick relevant test files.
- **Diagnostics Failure Distiller**: Trims verbose test runner logs and stack traces, achieving **60–90% token reduction** on test failure outputs sent to Copilot.

---

## 10. Policy Repository & Copilot Conventions Sync

### Overview
Remembers developer corrections and architectural conventions learned during Copilot chat sessions.

### Key Capabilities
- **Rule Extraction**: Automatically detects rules (e.g., "Do not modify server.py directly", "Use standard logging").
- **Instructions Sync**: Synchronizes approved policy rules directly into `.github/copilot-instructions.md`.

### Exposed MCP Tool
- `generate_copilot_instructions()`: Generate or update `.github/copilot-instructions.md`.

---

## 11. Natural Language "Why" Codebase Engine

### Overview
Answers architectural questions regarding code quality, risk metrics, and dependency relationships.

---

## 12. Fast Codebase Search Engine

### Overview
High-speed regex, symbol, and text search engine tailored for quick codebase navigation.

---

## 13. Interactive Visual Dashboards

### Overview
CopilotLens includes two built-in visual web dashboards served locally at **http://localhost:8765**:

1. **Vanilla Web Dashboard (`dashboard/`)**: Lightweight HTML5, CSS3, and JavaScript app using Cytoscape.js for interactive knowledge graph rendering.
2. **Next.js Dashboard (`dashboard-next/`)**: Modern React & Next.js dashboard bundle.

### Key Dashboard Views
- **🛡️ Coverity Scan Tab**: Filterable table of CIDs, severity badges, and 1-click Copilot fix prompts.
- **🕸️ Visual Knowledge Graph**: Interactive force-directed map of codebase hubs, circular dependencies, and risk hotspots.
- **📜 Policy & Conventions**: Approved and pending rule management.
- **🧪 Smart Tests & Distiller**: Recommended test runner with token savings metrics.
- **🏥 Code Health & Hotspots**: Score distribution and churn heatmap.

---

## 14. Complete MCP Tools Reference

| MCP Tool Name | Description | Key Inputs |
| :--- | :--- | :--- |
| `get_coverity_findings` | Get Coverity SAST rule violations, CIDs, line numbers & Copilot fix advice | `file_path`, `severity` |
| `get_coverity_summary` | Get overall Coverity security compliance score (0–100%) and defect counts | None |
| `import_coverity_json` | Import Coverity CLI JSON export (`cov-format-errors`) or JSON string | `json_content_or_path` |
| `run_coverity_scan` | Run static rule analysis scan and update `coverity_findings.json` | None |
| `get_file_health` | Get 0–100 score, grade, markers, and refactoring advice for a file | `file_path` |
| `get_codebase_summary` | Aggregate codebase health score distribution and worst files | None |
| `get_hotspots` | List top high-churn, risky files requiring extra review | `limit` |
| `get_module_owners` | Module ownership breakdown aggregated from git blame | None |
| `get_dead_code` | List unused function and class symbol candidates for cleanup | None |
| `get_dependency_graph` | Complete import dependency map (nodes, edges, circular deps) | None |
| `get_file_dependencies` | Direct inbound and outbound dependencies for a target file | `file_path` |
| `generate_copilot_instructions` | Sync policy repository rules into `.github/copilot-instructions.md` | None |
| `get_dashboard_url` | Return URL to the visual browser dashboard (`http://localhost:8765`) | None |

---

## 15. Quick Start & Setup Guide

### 1. Requirements
- Python 3.9+
- Git

### 2. Install Dependencies
```bash
pip install mcp gitpython
```

### 3. Run Server on Any Repository
```bash
python mcp_server/server.py --repo /path/to/your/project
```

### 4. Run Dashboard Only
```bash
python run_dashboard.py --repo /path/to/your/project
```
Open **http://localhost:8765** in your browser.

### 5. Configure in IntelliJ / VS Code GitHub Copilot MCP
Add to your Copilot MCP settings file (`~/.config/github-copilot/intellij/mcp.json`):

```json
{
  "servers": {
    "copilotlens": {
      "command": "python",
      "args": [
        "/absolute/path/to/CopilotLens-MCP-main/mcp_server/server.py",
        "--repo",
        "${workspaceFolder}"
      ]
    }
  }
}
```
