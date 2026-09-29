# CopilotLens MCP — Complete Feature Matrix & Architectural Guide 🔍

> **CopilotLens** is an enterprise-grade Model Context Protocol (MCP) server that empowers GitHub Copilot (Agent Mode) and developers with deep, structural codebase intelligence, static application security testing (Coverity SAST), health scoring, hotspot detection, dependency graphs, smart test recommendation, and policy synchronization.

---

## 📋 Table of Contents
1. [IntelliJ Native PSI Semantic Engine](#1-intellij-native-psi-semantic-engine)
2. [Neo4j Enterprise Code Graph Navigator](#2-neo4j-enterprise-code-graph-navigator)
3. [Coverity Scan & SAST Rules Engine](#3-coverity-scan--sast-rules-engine)
4. [Capital Logic (CLogic) & DRC Validator](#4-capital-logic-clogic--drc-validator)
5. [Cross-Platform Enterprise Context Scraper & Atlassian Integrations](#5-cross-platform-enterprise-context-scraper--atlassian-integrations)
6. [Deterministic Code Health Scorer](#6-deterministic-code-health-scorer)
7. [Git History, Churn & Hotspot Heatmap Analyzer](#7-git-history-churn--hotspot-heatmap-analyzer)
8. [Multi-Language AST Adapters & Dead Code Elimination](#8-multi-language-ast-adapters--dead-code-elimination)
9. [Dependency Intelligence & Knowledge Graph Engine](#9-dependency-intelligence--knowledge-graph-engine)
10. [Blast Radius & 100x Token Savings Calculator](#10-blast-radius--100x-token-savings-calculator)
11. [Smart Test Recommendation & Test Log Distiller](#11-smart-test-recommendation--test-log-distiller)
12. [Policy Repository & Copilot Conventions Continuous Sync](#12-policy-repository--copilot-conventions-continuous-sync)
13. [Interactive Visual Dashboards](#13-interactive-visual-dashboards)
14. [Complete MCP Tools Reference (79 Active Tools)](#14-complete-mcp-tools-reference-79-active-tools)
15. [Quick Start & Setup Guide](#15-quick-start--setup-guide)

---

## 1. IntelliJ Native PSI Semantic Engine

### Overview
Integrates directly with IntelliJ IDEA's **Program Structure Interface (PSI)** via the PSI Tools bridge (JSON-RPC over HTTP on `localhost:3000`/`:3001` with fallback to `psi_tools_cli.ps1`). It gives Copilot compiler-accurate, type-resolved semantic knowledge that static regex parsers cannot match.

### Key Capabilities
- **Class Structure Extraction**: Fully parses Java classes, field types, annotations, modifiers, and method signatures.
- **Exact Method Bodies**: Extracts precise source implementations for any method without reading entire monolithic files into context.
- **Find Usages & Call Graphs**: Traverses caller and callee hierarchies resolved by the IntelliJ compiler index.
- **Type Hierarchies**: Evaluates deep inheritance trees, sub-classes, super-classes, and interface implementations.
- **Real-Time Inspections**: Surfaces IntelliJ compiler warnings, syntax errors, and IDE inspection diagnostics directly to Copilot.

### Exposed MCP Tools
- `psi_health_check()`: Verifies connectivity to the IntelliJ PSI HTTP daemon.
- `psi_get_class_structure(class_name, file_path)`: Returns parsed fields, methods, constructors, and annotations.
- `psi_get_method_body(class_name, method_name, signature)`: Extracts target method implementation.
- `psi_find_usages(class_name, member_name, scope)`: Compiler-accurate usage references.
- `psi_get_call_graph(class_name, method_name, direction, depth)`: Call hierarchy (callers/callees).
- `psi_explore_class_dependencies(class_name)`: Direct semantic class imports and dependencies.
- `psi_get_type_hierarchy(class_name, direction)`: Subclasses, superclasses, and interfaces.
- `psi_symbol_search(query, symbol_type, max_results)`: Fast semantic symbol lookup across the IDE index.
- `psi_get_file_inspections(file_path, severity)`: Real-time IntelliJ diagnostic warnings and inspection errors.

---

## 2. Neo4j Enterprise Code Graph Navigator

### Overview
Connects to an enterprise Neo4j Code Graph instance (`neo4j_analyzer.py`), exposing 27 graph navigation and topological analysis actions over Bolt.

### Key Capabilities
- **Deep Class & Method Navigation**: Queries class nodes, interfaces, annotations, enums, and nested structures.
- **Graph Expansion (Out/In/Both)**: Explores multi-hop dependency networks around classes and tests.
- **Topological Centrality (PageRank & Betweenness)**: Computes structural hubs, architectural bottlenecks, and critical path classes.
- **Test-to-Production Coverage Mapping**: Discovers uncovered methods, related test infrastructure, and similar tested classes.
- **Arbitrary Cypher Execution**: Enables Copilot to construct and execute custom read-only Cypher queries for complex architectural investigations.

### Exposed MCP Tools (27 Tools)
- `neo4j_find_class`, `neo4j_get_class`, `neo4j_get_interface`, `neo4j_get_class_methods`, `neo4j_get_test_class`, `neo4j_find_by_filepath`
- `neo4j_expand_out`, `neo4j_expand_in`, `neo4j_expand_both`
- `neo4j_get_class_hierarchy`, `neo4j_get_related_tests`
- `neo4j_expand_test_out`, `neo4j_expand_test_in`, `neo4j_expand_test_both`
- `neo4j_get_uncovered_methods`, `neo4j_get_test_infrastructure`, `neo4j_find_similar_tested_classes`, `neo4j_get_package_coverage`
- `neo4j_graph_intelligence`, `neo4j_pagerank`, `neo4j_betweenness`, `neo4j_run_cypher`
- `neo4j_filter_by_field`, `neo4j_filter_by_annotation`, `neo4j_search_methods`, `neo4j_lookup_enum`, `neo4j_lookup_nested_classes`

---

## 3. Coverity Scan & SAST Rules Engine

### Overview
Integrates **Coverity Static Application Security Testing (SAST)** rule checks into CopilotLens. It parses, scans, stores, and exposes Coverity rule failures, CIDs, line numbers, severity levels, trace events, and Copilot remediation advice.

### Key Capabilities
- **JSON Storage & Persistence**: Saves scan findings into `coverity_findings.json` in the workspace root.
- **Coverity Format Compatibility**: Parses standard Coverity CLI exports (`cov-format-errors --json-output-v8`), Coverity Desktop output, and custom JSON rule reports.
- **Supported Checker Rules**: `RESOURCE_LEAK`, `NULL_RETURNS`, `FORWARD_NULL`, `UNINIT`, `OVERRUN`, `TAINTED_DATA`, `USE_AFTER_FREE`, `INTEGER_OVERFLOW`, `DEADCODE`.
- **Automated Copilot Fix Prompts**: Every defect includes a custom Copilot prompt explaining how to refactor and resolve the issue.
- **Rule Compliance Score (0–100%)**: Computes an aggregate security compliance grade based on High, Medium, and Low severity defects.

### Exposed MCP Tools
- `get_coverity_findings(file_path, severity)`: Get Coverity CIDs, failing rules, line numbers, and remediation guidance.
- `get_coverity_summary()`: Get overall Coverity security compliance score, defect breakdown by severity/checker, and affected files count.
- `import_coverity_json(json_content_or_path)`: Import external Coverity JSON reports into the workspace.
- `run_coverity_scan()`: Run static rule analysis across workspace files and write to `coverity_findings.json`.

---

## 4. Capital Logic (CLogic) & DRC Validator

### Overview
Domain-specific analysis engine for Siemens Capital Logic (CLogic) electrical harness designs and Caplet plugins.

### Key Capabilities
- **Capital XML Analyzer**: Parses Capital XML design schemas, devices, connectors, pins, nets, and properties.
- **Caplet Logic Action Generator**: Scaffolds complete Java Caplet Action classes, XML plugin descriptor declarations, and JUnit test fixtures.
- **Design Rule Check (DRC) Validator**: Runs heuristic design checks (unconnected pins, floating nets, missing wire gauges, duplicate component designators).
- **Live CLogic Session Inspector**: Inspects active CLogic / CManager runtime sessions and real-time design mutations.

### Exposed MCP Tools
- `analyze_xml_design(xml_input, detail)`: Full structural breakdown of a Capital XML design file.
- `generate_logic_action(action_name, target_object, package_name)`: Scaffolds Caplet Java code, XML configuration, and JUnit tests.
- `validate_design_drc(xml_input)`: Runs heuristic Capital Design Rule Checks.
- `inspect_live_clogic_session(target_xml_or_session)`: Inspects live or snapshot CLogic electrical session state.

---

## 5. Cross-Platform Enterprise Context Scraper & Atlassian Integrations

### Overview
Connects to Jira, Confluence, and Bitbucket Server / Data Center instances to extract cross-platform context, filter it using BM25 relevance scoring, and store it in a local SQLite cache.

### Key Capabilities
- **BM25 Semantic Relevance Ranking**: Eliminates noise by evaluating term frequency, document length, and inverse document frequency across scraped artifacts.
- **SQLite Context Database**: Persists scraped context into `.copilotlens_context.db` for instant retrieval across sessions.
- **Atlassian REST Clients**: Full support for Bearer Personal Access Tokens (PAT) and Cloud Basic authentication.
- **Automated PR Annotation**: Directly annotates pull requests with blast radius, health scores, and recommended tests.

### Exposed MCP Tools
- `scrape_extended_context(topic, max_results_per_source)`: Scrapes Jira, Confluence, and Bitbucket matching a topic, scores with BM25, and caches to DB.
- `get_cached_context(topic)`: Retrieves stored context from the local SQLite database.
- `get_jira_issues_for_file(file_path)`: Finds Jira issues mentioning or linked to a file.
- `create_jira_issue(summary, description, issue_type)`: Creates a Jira bug, task, or improvement.
- `update_jira_issue(issue_key, append_description, new_summary)`: Modifies existing Jira tickets.
- `get_confluence_page(topic)`: Searches and retrieves Confluence documentation.
- `update_confluence_page(title_or_id, prepend_html, append_html)`: Appends or prepends documentation.
- `get_pr_context(pr_id)`: Fetches Bitbucket PR metadata and modified files.
- `annotate_pr(pr_id, comment_markdown)`: Posts review comments to Bitbucket PRs.
- `get_recent_prs(limit)`: Lists recent active pull requests.

---

## 6. Deterministic Code Health Scorer

### Overview
Evaluates any source file on a **0 to 100 score** and letter grade (**A, B, C, D, F**) using non-LLM, deterministic rules across 15+ programming languages.

### Key Capabilities
- **13 Weighted Quality Markers**: `file_too_large` (-20), `very_large_file` (-10), `too_many_todos` (-10), `no_comments` (-10), `deeply_nested` (-15), `long_functions` (-15), `high_complexity` (-15), `magic_numbers` (-5), `coverity_rule_failure` (-25), `good_comment_ratio` (+10), `short_file` (+5), `has_tests` (+10), `consistent_style` (+5).

### Exposed MCP Tools
- `get_file_health(file_path)`: Score a specific file and return actionable Copilot refactoring advice.
- `get_codebase_summary()`: Aggregate health summary across all codebase files.

---

## 7. Git History, Churn & Hotspot Heatmap Analyzer

### Overview
Analyzes git repository commits, author activity, churn frequency, and module ownership to flag high-risk areas.

### Key Capabilities
- **Hotspots Detection**: Combines commit churn with low health scores.
- **Adaptive Co-Change Coupling Pairs**: Identifies files that frequently change together in commits with adaptive thresholding.
- **Module Ownership & Bus Factor**: Aggregates git blame data per module to identify single-contributor risks (bus factor = 1).
- **Git Archaeology ("Why")**: Traces commit rationale and message history behind any file.

### Exposed MCP Tools
- `get_hotspots(limit)`: Top N high-churn / risky files requiring extra care.
- `get_co_change_pairs()`: Files that frequently change together in commits.
- `get_module_owners()`: Module ownership breakdown aggregated by git commit authors.
- `get_why(file_path)`: Explains why a file evolved to its current state from git history.

---

## 8. Multi-Language AST Adapters & Dead Code Elimination

### Overview
Abstract Syntax Tree analysis across Java, Python, JavaScript, and TypeScript to identify confirmed dead code and unused symbols.

### Key Capabilities
- **Two-Tier Classification**: `CONFIRMED_ISSUE` (zero internal callers) vs `HEURISTIC_CANDIDATE`.
- **Symbol Extraction**: Analyzes methods, fields, classes, imports, and exports.

### Exposed MCP Tools
- `get_dead_code()`: Returns sorted candidates for dead code cleanup.

---

## 9. Dependency Intelligence & Knowledge Graph Engine

### Overview
Parses import statements across modules to build a structural dependency graph with circular import detection.

### Key Capabilities
- **Hub File & Orphan Detection**: Identifies architectural dependencies and isolated modules.
- **Circular Dependency Analysis**: Detects circular import loops that degrade build stability.

### Exposed MCP Tools
- `get_dependency_graph()`: Complete import dependency node and edge graph.
- `get_file_dependencies(file_path)`: Direct inbound and outbound dependencies for a specific file.
- `get_named_imports(file_path)`: Explicit named imports parsed from source.
- `query_codebase_graph(target_node, depth)`: Explores localized multi-hop subgraphs.

---

## 10. Blast Radius & 100x Token Savings Calculator

### Overview
Calculates the historical and architectural "ripple effect" of modifying a target file.

### Key Capabilities
- **Minimal Review Context Set**: Selects only the essential 3-5 connected files needed when modifying a file, avoiding dumping whole directories into Copilot context.
- **100x Token Savings**: Prevents LLM context window overflow and speeds up Copilot response times.

### Exposed MCP Tool
- `get_blast_radius(file_path)`: Evaluates direct dependencies, co-changes, and affected test suites.

---

## 11. Smart Test Recommendation & Test Log Distiller

### Overview
Recommends the minimal test suite to run after modifying specific files and cleans test failure logs.

### Key Capabilities
- **AST Diff & Test Mapping**: Uses changed symbols to identify relevant unit and integration tests.
- **Test Output Distillation**: Trims verbose test runner logs (Gradle, Maven, pytest, Jest), achieving **60–90% token reduction**.

### Exposed MCP Tools
- `analyze_changed_symbols(base_ref, head_ref)`: Discovers functions and classes modified in a git range.
- `recommend_tests(file_path, base_ref)`: Recommends the minimal test suite to validate changes.
- `distill_test_output(raw_output, framework)`: Compresses verbose test failure logs.
- `run_recommended_tests(file_path, base_ref, dry_run)`: Executes or simulates the recommended test run.

---

## 12. Policy Repository & Copilot Conventions Continuous Sync

### Overview
Learns developer rules and architectural conventions from chat interactions and persists them to `.github/copilot-instructions.md`.

### Key Capabilities
- **Automatic Rule Extraction**: Detects corrections (e.g., "never modify this file", "always use standard logging") and auto-promotes high-confidence policies.
- **Manual Policy Review**: Developers can review, approve, or reject extracted rules.
- **Instructions Sync**: Synchronizes approved rules directly into `.github/copilot-instructions.md`.

### Exposed MCP Tools
- `remember_rule(rule_text, category, severity, rationale)`: Explicitly register a new codebase convention.
- `analyze_copilot_interaction(user_prompt, copilot_response, was_accepted)`: Auto-extracts conventions from chat turns.
- `get_project_rules(status, category)`: Lists active and pending policy rules.
- `review_policy_rule(rule_id, approved)`: Approves or rejects a candidate rule.
- `generate_copilot_instructions()`: Writes approved rules to `.github/copilot-instructions.md`.
- `get_copilot_context(file_path)`: Contextual policy instructions for a file.

---

## 13. Interactive Visual Dashboards

### Overview
CopilotLens includes built-in visual web dashboards served locally at **http://localhost:8765**:
- **Vanilla Web Dashboard (`dashboard/`)**: Lightweight HTML5/CSS3/JS app using Cytoscape.js for interactive knowledge graph rendering.
- **Next.js Dashboard (`dashboard-next/`)**: Modern React & Next.js dashboard bundle.

### Key Dashboard Views
- **🛡️ Coverity Scan Tab**: Filterable table of CIDs, severity badges, and 1-click Copilot fix prompts.
- **🕸️ Visual Knowledge Graph**: Interactive force-directed map of codebase hubs, circular dependencies, and risk hotspots.
- **🌐 Neo4j Graph Navigator**: Direct graph query input with schema exploration.
- **📜 Policy & Conventions**: Approved and pending rule management modal.
- **🧪 Smart Tests & Distiller**: Recommended test runner with token savings metrics.
- **🏥 Code Health & Hotspots**: Score distribution and churn heatmap with adaptive co-changes.

---

## 14. Complete MCP Tools Reference (79 Active Tools)

| Tool Name | Domain | Description |
| :--- | :--- | :--- |
| `psi_health_check` | IntelliJ PSI | Health check for the IntelliJ PSI tools service |
| `psi_get_class_structure` | IntelliJ PSI | Get detailed structure of a Java class (methods, fields, annotations) |
| `psi_get_method_body` | IntelliJ PSI | Get the exact implementation of a specific method |
| `psi_find_usages` | IntelliJ PSI | Find all compiler-resolved usages of a class or member |
| `psi_get_call_graph` | IntelliJ PSI | Get the incoming or outgoing call graph for a method |
| `psi_explore_class_dependencies` | IntelliJ PSI | Explore semantic dependencies of a class |
| `psi_get_type_hierarchy` | IntelliJ PSI | Get subclasses, superclasses, and interface implementations |
| `psi_symbol_search` | IntelliJ PSI | Search for symbols in the IntelliJ compiler index |
| `psi_get_file_inspections` | IntelliJ PSI | Get real-time IDE compiler warnings and inspections |
| `neo4j_find_class` | Neo4j Graph | Find class node and its metadata by name |
| `neo4j_get_class` | Neo4j Graph | Get full class details from Neo4j |
| `neo4j_get_interface` | Neo4j Graph | Get interface node details and implementations |
| `neo4j_get_class_methods` | Neo4j Graph | List methods belonging to a class |
| `neo4j_get_test_class` | Neo4j Graph | Get test class details and mapped targets |
| `neo4j_find_by_filepath` | Neo4j Graph | Find graph nodes matching a file path |
| `neo4j_expand_out` | Neo4j Graph | Expand outgoing relationships from a node |
| `neo4j_expand_in` | Neo4j Graph | Expand incoming relationships to a node |
| `neo4j_expand_both` | Neo4j Graph | Expand bidirectional connections |
| `neo4j_get_class_hierarchy` | Neo4j Graph | Get inheritance hierarchy from the graph |
| `neo4j_get_related_tests` | Neo4j Graph | Find all tests covering a production class |
| `neo4j_expand_test_out` | Neo4j Graph | Expand outgoing relationships from a test class |
| `neo4j_expand_test_in` | Neo4j Graph | Expand incoming relationships to a test class |
| `neo4j_expand_test_both` | Neo4j Graph | Expand bidirectional test connections |
| `neo4j_get_uncovered_methods` | Neo4j Graph | Identify methods with zero covering tests |
| `neo4j_get_test_infrastructure` | Neo4j Graph | Get base test classes and fixtures |
| `neo4j_find_similar_tested_classes` | Neo4j Graph | Find similar classes with existing test suites |
| `neo4j_get_package_coverage` | Neo4j Graph | Package-level test coverage metrics |
| `neo4j_graph_intelligence` | Neo4j Graph | Structural health and graph topology overview |
| `neo4j_pagerank` | Neo4j Graph | PageRank centrality score for classes |
| `neo4j_betweenness` | Neo4j Graph | Betweenness centrality (architectural bottlenecks) |
| `neo4j_run_cypher` | Neo4j Graph | Execute a read-only Cypher query |
| `neo4j_filter_by_field` | Neo4j Graph | Filter classes by field type or name |
| `neo4j_filter_by_annotation` | Neo4j Graph | Filter classes by annotation |
| `neo4j_search_methods` | Neo4j Graph | Search methods across the graph |
| `neo4j_lookup_enum` | Neo4j Graph | Look up enum definitions and constants |
| `neo4j_lookup_nested_classes` | Neo4j Graph | Look up inner and nested classes |
| `get_coverity_findings` | Coverity SAST | Get Coverity SAST rule violations and Copilot fix advice |
| `get_coverity_summary` | Coverity SAST | Get SAST compliance score (%) and defect counts |
| `import_coverity_json` | Coverity SAST | Import Coverity CLI JSON export (`cov-format-errors`) |
| `run_coverity_scan` | Coverity SAST | Run static rule scan and save to `coverity_findings.json` |
| `analyze_xml_design` | CLogic / DRC | Analyze a Capital XML design file or scenario |
| `generate_logic_action` | CLogic / DRC | Scaffold a Java Caplet Action, XML config & JUnit test |
| `validate_design_drc` | CLogic / DRC | Run heuristic Capital Design Rule Checks |
| `inspect_live_clogic_session` | CLogic / DRC | Inspect live CLogic/CManager session state |
| `scrape_extended_context` | Context Scraper | Scrape Jira, Confluence & PRs with BM25 ranking to SQLite |
| `get_cached_context` | Context Scraper | Retrieve cached semantic context from SQLite DB |
| `get_jira_issues_for_file` | Atlassian | Search Jira for issues linked to a source file |
| `create_jira_issue` | Atlassian | Create a Jira Bug, Task, or Improvement |
| `update_jira_issue` | Atlassian | Append description or update summary of a Jira issue |
| `get_confluence_page` | Atlassian | Find and retrieve a Confluence page |
| `update_confluence_page` | Atlassian | Prepend or append HTML content to a Confluence page |
| `get_pr_context` | Atlassian | Get Bitbucket PR metadata and modified files |
| `annotate_pr` | Atlassian | Post a Markdown review comment on a Bitbucket PR |
| `get_recent_prs` | Atlassian | List recent active pull requests |
| `get_file_health` | Code Health | 0–100 health score, grade, markers, and refactoring advice |
| `get_codebase_summary` | Code Health | Overall codebase health distribution and worst files |
| `get_hotspots` | Git History | Top high-churn, risky files requiring extra care |
| `get_co_change_pairs` | Git History | Files that frequently change together in commits |
| `get_module_owners` | Git History | Module ownership breakdown aggregated from git blame |
| `get_why` | Git History | Git archaeology explaining why code changed |
| `get_dead_code` | Dead Code | Unused function and class symbol candidates for cleanup |
| `get_dependency_graph` | Dependencies | Complete import dependency map and circular dependencies |
| `get_file_dependencies` | Dependencies | Inbound and outbound dependencies for a file |
| `get_named_imports` | Dependencies | Explicit named imports parsed from a source file |
| `get_blast_radius` | Blast Radius | Change ripple effect across imports, co-changes, and tests |
| `search_codebase` | Search | High-speed regex and text search across the repository |
| `find_symbol_usages` | Search | Find symbol references across workspace files |
| `analyze_changed_symbols` | Smart Tests | Changed functions and classes between git refs |
| `recommend_tests` | Smart Tests | Minimal test suite recommendation for changed files |
| `distill_test_output` | Smart Tests | Compress verbose test runner logs (60–90% token reduction) |
| `run_recommended_tests` | Smart Tests | Run or simulate recommended tests |
| `remember_rule` | Policy Repo | Remember an architectural rule or developer convention |
| `analyze_copilot_interaction`| Policy Repo | Extract conventions from Copilot chat corrections |
| `get_project_rules` | Policy Repo | Retrieve active and candidate policy rules |
| `review_policy_rule` | Policy Repo | Approve or reject a candidate policy rule |
| `generate_copilot_instructions`| Policy Repo | Sync approved rules to `.github/copilot-instructions.md` |
| `get_copilot_context` | Policy Repo | Retrieve relevant rules for a specific file |
| `get_dashboard_url` | Dashboard | Return local browser dashboard URL |
| `query_codebase_graph` | Knowledge Graph | Localized multi-hop contextual subgraph traversal |

---

## 15. Quick Start & Setup Guide

### 1. Requirements
- Python 3.9+
- Git CLI
- (Optional) IntelliJ IDEA with PSI Tools plugin for semantic analysis
- (Optional) Neo4j 5.x for enterprise code graph traversal

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
      ],
      "env": {
        "COPILOTLENS_PORT": "8765"
      }
    }
  }
}
```
