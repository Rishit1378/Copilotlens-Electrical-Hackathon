# CopilotLens 🔍
### Codebase Intelligence, Semantic PSI, SAST Security & Knowledge Graph Layer for GitHub Copilot

> *"What if GitHub Copilot knew everything a senior architect, security auditor, and domain expert knows about your codebase — before it even suggested a change?"*

**CopilotLens** is an enterprise Model Context Protocol (MCP) server that empowers GitHub Copilot's Agent mode with deep structural, semantic, and domain knowledge: **Coverity SAST static security scanning**, **IntelliJ Native PSI semantic code intelligence**, **Neo4j Enterprise Code Graph navigation**, **Capital Logic (CLogic) and DRC rules validation**, **Atlassian Jira/Confluence/Bitbucket integrations**, **BM25 semantic context scraping**, deterministic code health scoring, AST dead code elimination, and auto-learning policy repository synchronization.

📖 **For detailed feature breakdown and architecture details, see [FEATURES.md](FEATURES.md)**.

---

## ✨ Highlights

- ⚡ **IntelliJ Native PSI Semantic Engine**: Direct integration with IntelliJ IDEA's Program Structure Interface via JSON-RPC / CLI (`psi_*`), enabling deep symbol search, call graphs, type hierarchies, method override trees, and real-time inspections.
- 🛡️ **Coverity SAST Security Scanner**: Detects `RESOURCE_LEAK`, `NULL_RETURNS`, `UNINIT`, `OVERRUN`, `TAINTED_DATA`, `USE_AFTER_FREE` defects, imports standard Coverity JSON reports, and generates automated Copilot remediation prompts.
- 🌐 **Neo4j Enterprise Code Graph Navigator**: 27 deep graph tools querying class hierarchies, dependency expansions, PageRank/betweenness centralities, test-to-code coverage mappings, and arbitrary Cypher execution.
- 🔌 **Capital Logic (CLogic) & DRC Validator**: Real-time session watcher and XML design analyzer with automated Caplet Java action scaffolding and heuristic Design Rule Checks (DRC).
- 🧠 **BM25 Semantic Enterprise Context Scraper**: Scrapes Jira issues, Confluence documentation, and Bitbucket PRs matching any topic or keyword, ranks them with BM25 semantic scoring, and persists them into an SQLite database.
- 🏥 **Deterministic Code Health Scorer**: 0–100 quality score and A–F letter grades based on 13 weighted quality markers across 15+ programming languages.
- 🔥 **Git Churn & Hotspots Analysis**: Highlights high-risk files (high churn + low health), adaptive co-change coupling pairs, and git blame module ownership.
- 🧹 **AST Dead Code Detection**: Discovers confirmed unused functions and classes with zero callers across the codebase.
- 🔗 **Dependency Intelligence & Visual Graph**: Structural import map identifying hub files, circular imports, and orphan modules rendered with Cytoscape.js.
- 🧪 **Smart Test Selection & Log Distiller**: Recommends minimal test suites based on changed symbols and compresses verbose test failure logs by 60–90%.
- 📜 **Policy Repository & Continuous Learning**: Remembers developer rules, auto-analyzes Copilot chat corrections, and syncs conventions to `.github/copilot-instructions.md`.
- 📊 **Real-Time Visual Dashboard**: Served locally at `http://localhost:8765` featuring Cytoscape / Vis.js graph navigation, Coverity SAST panel, policy management, and Neo4j query controls.

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
      ],
      "env": {
        "COPILOTLENS_PORT": "8765"
      }
    }
  }
}
```

---

## 🛠️ MCP Tools Overview (79 Active Tools)

CopilotLens provides **79 MCP tools** organized into modular domain suites:

| Domain / Category | Tool Count | Core Capabilities & Key Tools |
| :--- | :---: | :--- |
| **IntelliJ PSI Engine** | 9 | `psi_get_class_structure`, `psi_get_call_graph`, `psi_find_usages`, `psi_get_type_hierarchy`, `psi_symbol_search`, `psi_get_file_inspections`, `psi_health_check` |
| **Neo4j Code Graph** | 27 | `neo4j_find_class`, `neo4j_get_class_hierarchy`, `neo4j_expand_both`, `neo4j_get_related_tests`, `neo4j_pagerank`, `neo4j_run_cypher`, `neo4j_graph_intelligence` |
| **Coverity SAST Security** | 4 | `get_coverity_findings`, `get_coverity_summary`, `import_coverity_json`, `run_coverity_scan` |
| **Capital Logic (CLogic) & DRC** | 4 | `analyze_xml_design`, `generate_logic_action`, `validate_design_drc`, `inspect_live_clogic_session` |
| **Atlassian & Context Scraper** | 10 | `scrape_extended_context`, `get_cached_context`, `get_jira_issues_for_file`, `create_jira_issue`, `get_confluence_page`, `annotate_pr`, `get_recent_prs` |
| **Code Health, Git & Hotspots** | 6 | `get_file_health`, `get_codebase_summary`, `get_hotspots`, `get_co_change_pairs`, `get_module_owners`, `get_why` |
| **AST Dead Code & Dependencies** | 5 | `get_dead_code`, `get_dependency_graph`, `get_file_dependencies`, `get_named_imports`, `get_blast_radius` |
| **Search & Discovery** | 2 | `search_codebase`, `find_symbol_usages` |
| **Smart Tests & Log Distiller** | 4 | `analyze_changed_symbols`, `recommend_tests`, `distill_test_output`, `run_recommended_tests` |
| **Policy & Conventions Sync** | 6 | `remember_rule`, `analyze_copilot_interaction`, `get_project_rules`, `review_policy_rule`, `generate_copilot_instructions`, `get_copilot_context` |
| **Visual Dashboard & Graph** | 2 | `get_dashboard_url`, `query_codebase_graph` |

---

## 📄 Documentation

- [FEATURES.md](FEATURES.md) — Comprehensive technical feature breakdown & 79 MCP tools catalog.
- [setup.md](setup.md) — Step-by-step installation and environment configuration guide.
- [docs/atlassian_setup.md](docs/atlassian_setup.md) — Jira, Confluence, and Bitbucket connection guide.
- [docs/coverity_setup.md](docs/coverity_setup.md) — Coverity SAST JSON export and integration guide.
- [docs/neo4j_design.md](docs/neo4j_design.md) — Neo4j enterprise knowledge graph architecture and schema.

---

## 📄 License
MIT License. Developed for GitHub Copilot Agent Mode.

