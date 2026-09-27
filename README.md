# CopilotLens 🔍
### Codebase Intelligence & SAST Security Layer for GitHub Copilot

> *"What if GitHub Copilot knew everything a senior engineer and security architect knows about your codebase — before it even suggested a change?"*

**CopilotLens** is an Model Context Protocol (MCP) server that gives GitHub Copilot's Agent mode deep, structural knowledge about any codebase: **Coverity SAST static analysis rule checks**, health scores, hotspot heatmaps, AST dead code detection, dependency graphs, smart test recommendation, and policy synchronization — all surfaced directly into your Copilot conversations and local dashboard.

📖 **For detailed feature breakdown and architecture details, see [FEATURES.md](FEATURES.md)**.

---

## ✨ Highlights

- 🛡️ **Coverity SAST Security Scanner**: Detects `RESOURCE_LEAK`, `NULL_RETURNS`, `UNINIT`, `OVERRUN`, `TAINTED_DATA`, `USE_AFTER_FREE` defects, persists findings to `coverity_findings.json`, and provides automated Copilot fix prompts.
- 🏥 **Deterministic Code Health Scorer**: 0–100 quality score and A–F letter grades based on 13 weighted quality markers across 15+ programming languages.
- 🔥 **Git Churn & Hotspots Analysis**: Highlights high-risk files (high churn + low health) and co-change coupling pairs.
- 🧹 **AST Dead Code Detection**: Discovers confirmed unused functions/classes with zero callers.
- 🔗 **Dependency Intelligence & Visual Graph**: Structural import map identifying hub files, circular imports, and orphan modules.
- 🧪 **Smart Test Selection & Log Distiller**: Recommends minimal test suites and compresses failure logs by 60–90%.
- ⚡ **Blast Radius & 100x Token Savings**: Calculates change ripple effects to feed Copilot minimal review contexts.
- 📜 **Policy Repository Sync**: Converts chat corrections into `.github/copilot-instructions.md` rules.
- 📊 **Real-Time Visual Dashboard**: Served locally at `http://localhost:8765`.

---

## 🚀 Quick Start

### 1. Install Dependencies
```bash
pip install mcp gitpython
```

### 2. Run the MCP Server on Any Repository
```bash
python mcp_server/server.py --repo /path/to/your/project
```

### 3. Run Dashboard Only
```bash
python run_dashboard.py --repo /path/to/your/project
```
Open your browser to: **http://localhost:8765**

---

## 🖥️ IntelliJ IDEA & VS Code GitHub Copilot Setup

Configure the MCP server in your IDE Copilot configuration (`~/.config/github-copilot/intellij/mcp.json` or VS Code MCP settings):

```json
{
  "servers": {
    "copilotlens": {
      "command": "python",
      "args": [
        "/path/to/CopilotLens-MCP-main/mcp_server/server.py",
        "--repo",
        "${workspaceFolder}"
      ]
    }
  }
}
```

---

## 🛠️ MCP Tools Overview

| Tool Name | Feature |
| :--- | :--- |
| `get_coverity_findings` | Get Coverity SAST rule violations, line numbers, and Copilot fix advice |
| `get_coverity_summary` | Get SAST rule compliance score (%) and defect counts |
| `import_coverity_json` | Import Coverity CLI JSON export (`cov-format-errors`) |
| `run_coverity_scan` | Run static rule scan and save to `coverity_findings.json` |
| `get_file_health` | Get health score (0–100), letter grade, and markers for a file |
| `get_codebase_summary` | Aggregate codebase health score distribution |
| `get_hotspots` | List top high-churn, risky files |
| `get_module_owners` | Module ownership breakdown aggregated from git blame |
| `get_dead_code` | List unused functions/classes for cleanup |
| `get_dependency_graph` | Complete import graph & circular dependencies |
| `get_file_dependencies` | Inbound and outbound dependencies for a file |
| `generate_copilot_instructions` | Sync policy rules to `.github/copilot-instructions.md` |
| `get_dashboard_url` | Get browser dashboard URL |

---

## 📄 Documentation

- [FEATURES.md](FEATURES.md) — Comprehensive technical feature breakdown & architecture guide.
- [setup.md](setup.md) — Step-by-step installation and environment configuration guide.

---

## 📄 License
MIT License. Developed for GitHub Copilot Agent Mode.
