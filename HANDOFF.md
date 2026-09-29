# CoPilotLens v2.0 — Master Handoff Document
<!-- 
  PURPOSE: This document lets any AI model or developer pick up this project
  at any point and continue without losing context. Keep it updated as work progresses.
  Last updated: 2026-09-27
-->

## What This Project Is

CoPilotLens is a **Model Context Protocol (MCP) server** written in Python that runs locally
alongside any Java/JS/Python repository. It exposes codebase intelligence — health scores,
hotspots, dead code, dependency graphs, Jira integration, and test recommendations — directly
into GitHub Copilot's Agent mode inside IntelliJ IDEA (or VS Code).

The MCP server is at `mcp_server/server.py` and registers tools using `FastMCP`.
GitHub Copilot calls these tools autonomously during Agent conversations.

---

## Repository Layout

```
c:\CoPilotLens\
├── mcp_server/
│   ├── server.py                    <- MCP server entry point. All @mcp.tool() definitions live here.
│   ├── requirements.txt             <- Python deps (currently: mcp, gitpython, click)
│   └── analyzers/
│       ├── git_analyzer.py          <- git log: churn, hotspots, co-change, ownership
│       ├── code_health.py           <- Rule-based health scoring 0-100 (regex/line-count)
│       ├── dependency.py            <- Regex import graph (Python/Java/JS/TS/Go/C#)
│       ├── dead_code.py             <- Heuristic dead code via word-count (needs AST upgrade)
│       ├── why_analyzer.py          <- Git archaeology: explains why code changed
│       ├── search_analyzer.py       <- Full-text codebase search
│       ├── blast_radius.py          <- Blast radius calculator (dep graph + co-change)
│       └── cache.py                 <- JSON file cache (.copilotlens_cache.json in repo root)
├── dashboard/
│   ├── index.html                   <- Single-page web dashboard (served at localhost:8765)
│   ├── style.css                    <- Dark mode premium CSS
│   └── app.js                       <- Dashboard JS: charts, API calls to /api/data
├── dashboard-next/                  <- (Next.js version, not primary)
├── intellij_setup/mcp.json          <- IntelliJ MCP config template
├── .github/copilot/mcp.json         <- VS Code / GitHub Copilot MCP config
├── setup.md                         <- End-user installation guide (IntelliJ focus)
├── README.md                        <- Project overview
├── run_dashboard.py                 <- Standalone dashboard runner (no IDE needed)
├── HANDOFF.md                       <- THIS FILE — keep updated as work progresses
└── docs/
    ├── atlassian_setup.md           <- How to get Jira/Confluence/Bitbucket credentials
    ├── coverity_setup.md            <- How to point at Coverity JSON output
    ├── neo4j_design.md              <- Deferred: Neo4j graph design (documented, not implemented)
    └── phase_status.md              <- Current implementation status per phase
```

---

## Current State (v2.0 - What Already Works)

### Analyzers (20 Total Analyzers in `mcp_server/analyzers/` & `integrations/`)
1. `PsiToolsAnalyzer` (`psi_analyzer.py`): IntelliJ IDEA native PSI semantic engine (symbols, method bodies, call graphs, type hierarchy, inspections).
2. `Neo4jAnalyzer` (`neo4j_analyzer.py`): 27 actions over Neo4j Bolt graph (classes, tests, coverage, PageRank, betweenness, Cypher).
3. `CoverityAnalyzer` (`coverity_analyzer.py`): SAST security rule scanner, finding persistence, and automated fix prompts.
4. `CLogicSessionAnalyzer` (`clogic_session_analyzer.py`): Live Capital Logic / CManager session poller and state inspector.
5. `XmlAnalyzer` (`xml_analyzer.py`): Capital XML design and scenario analyzer.
6. `DrcValidator` (`drc_validator.py`): Heuristic Capital Design Rule Checks (DRC).
7. `LogicActionGenerator` (`logic_action_generator.py`): Java Caplet Action + config + JUnit generator.
8. `ContextScraper` (`context_scraper.py`): BM25 semantic ranker & SQLite context database for Jira/Confluence/Bitbucket.
9. `GitAnalyzer` (`git_analyzer.py`): Git log churn, hotspots, adaptive co-changes, module ownership (git blame).
10. `CodeHealthScorer` (`code_health.py`): 13 deterministic markers, 0–100 score & grades.
11. `DependencyAnalyzer` (`dependency.py`): Import graph, hub files, circular dependencies.
12. `DeadCodeDetector` & `ASTDeadCodeDetector` (`dead_code.py`, `dead_code_ast.py`): Confirmed unused functions/classes.
13. `WhyAnalyzer` (`why_analyzer.py`): Git archaeology & commit rationale.
14. `CodebaseSearch` (`search_analyzer.py`): High-speed regex, symbol search.
15. `BlastRadiusAnalyzer` (`blast_radius.py`): 100x token savings ripple effect calculator.
16. `PolicyRepository` & `CopilotInteractionAnalyzer` (`policy_repo.py`): Auto-learning conventions & instructions sync.
17. `SmartTestAnalyzer` (`smart_test_analyzer.py`): AST diff changed symbols, test recommendation & log distiller.
18. `CodebaseKnowledgeGraph` (`codebase_graph.py`): Multi-hop in-memory contextual graph.
19. `AnalysisCache` (`cache.py`): Incremental `.copilotlens_cache.json` caching.
20. `Atlassian Integrations` (`jira.py`, `confluence.py`, `bitbucket.py`): Enterprise REST clients for Data Center/Server and Cloud.

### Active MCP Tools (79 total defined in `mcp_server/server.py`)
- **IntelliJ PSI Engine (9)**: `psi_health_check`, `psi_get_class_structure`, `psi_get_method_body`, `psi_find_usages`, `psi_get_call_graph`, `psi_explore_class_dependencies`, `psi_get_type_hierarchy`, `psi_symbol_search`, `psi_get_file_inspections`
- **Neo4j Code Graph (27)**: `neo4j_find_class`, `neo4j_get_class`, `neo4j_get_interface`, `neo4j_get_class_methods`, `neo4j_get_test_class`, `neo4j_find_by_filepath`, `neo4j_expand_out`, `neo4j_expand_in`, `neo4j_expand_both`, `neo4j_get_class_hierarchy`, `neo4j_get_related_tests`, `neo4j_expand_test_out`, `neo4j_expand_test_in`, `neo4j_expand_test_both`, `neo4j_get_uncovered_methods`, `neo4j_get_test_infrastructure`, `neo4j_find_similar_tested_classes`, `neo4j_get_package_coverage`, `neo4j_graph_intelligence`, `neo4j_pagerank`, `neo4j_betweenness`, `neo4j_run_cypher`, `neo4j_filter_by_field`, `neo4j_filter_by_annotation`, `neo4j_search_methods`, `neo4j_lookup_enum`, `neo4j_lookup_nested_classes`
- **Coverity SAST (4)**: `get_coverity_findings`, `get_coverity_summary`, `import_coverity_json`, `run_coverity_scan`
- **Capital Logic & DRC (4)**: `analyze_xml_design`, `generate_logic_action`, `validate_design_drc`, `inspect_live_clogic_session`
- **Context Scraper & Atlassian (10)**: `scrape_extended_context`, `get_cached_context`, `get_jira_issues_for_file`, `create_jira_issue`, `update_jira_issue`, `get_confluence_page`, `update_confluence_page`, `get_pr_context`, `annotate_pr`, `get_recent_prs`
- **Code Health & Git (6)**: `get_file_health`, `get_codebase_summary`, `get_hotspots`, `get_co_change_pairs`, `get_module_owners`, `get_why`
- **Dead Code & Dependencies (5)**: `get_dead_code`, `get_dependency_graph`, `get_file_dependencies`, `get_named_imports`, `get_blast_radius`
- **Search (2)**: `search_codebase`, `find_symbol_usages`
- **Smart Tests & Distiller (4)**: `analyze_changed_symbols`, `recommend_tests`, `distill_test_output`, `run_recommended_tests`
- **Policy Repository & Rules (6)**: `remember_rule`, `analyze_copilot_interaction`, `get_project_rules`, `review_policy_rule`, `generate_copilot_instructions`, `get_copilot_context`
- **Dashboard & Subgraphs (2)**: `get_dashboard_url`, `query_codebase_graph`

---


## v2.0 Phase Status

### Phase 1: Tree-sitter AST Engine [NOT STARTED]
**Priority: CRITICAL PATH — all other phases depend on this**

Primary language: **Java** (user's codebase is primarily Java)
Secondary: Python, JS, TypeScript

Files to create:
```
mcp_server/analyzers/
  ast_engine.py              <- Dispatcher: picks adapter by file extension
  adapters/
    __init__.py
    base_adapter.py          <- Abstract interface all adapters must implement
    java_adapter.py          <- Primary — tree-sitter-java
    python_adapter.py
    javascript_adapter.py
    typescript_adapter.py
    regex_fallback.py        <- Wraps existing dead_code.py/dependency.py regex patterns
```

All adapters implement this interface (defined in base_adapter.py):
```python
class LanguageAdapter:
    def get_definitions(self, source: str) -> list[dict]
    # Returns: [{name, type, line_start, line_end, is_public, annotations}]

    def get_imports(self, source: str) -> list[dict]
    # Returns: [{module, symbols: [], is_static, line}]

    def get_call_sites(self, source: str) -> list[dict]
    # Returns: [{caller, callee, line, is_test_call}]

    def get_test_functions(self, source: str) -> list[dict]
    # Java: @Test (JUnit 4/5), @ParameterizedTest
    # Python: test_* prefix, unittest.TestCase
    # JS/TS: it(), test(), describe() (Jest/Mocha)

    def get_changed_symbols(self, old_src: str, new_src: str) -> list[str]
    # Returns names of functions/classes whose signature or body changed
```

New pip deps to add to requirements.txt:
```
tree-sitter>=0.21.0
tree-sitter-python>=0.21.0
tree-sitter-javascript>=0.21.0
tree-sitter-typescript>=0.21.0
tree-sitter-java>=0.21.0
```

FALLBACK RULE: If `import tree_sitter` fails or language is unsupported, silently fall
back to regex_fallback.py. Never crash the server.

---

### Phase 2: Dead Code v2 + Test Output Filter [NOT STARTED]
**Requires: Phase 1**

#### 2a — Dead code upgrade (rewrite dead_code.py to use AST)

Replace word-count with AST call-graph traversal. New confidence tiers:
- `CONFIRMED`: symbol never appears in any call graph node across all files
- `HIGH`: symbol is public/exported but no call-sites found anywhere
- `MEDIUM`: symbol appears in call graph only within its own file
- `HEURISTIC`: symbol referenced via string literal (reflection risk — do not auto-delete)

#### 2b — New MCP tool: run_and_filter_tests(test_command: str)

1. Runs the user's test command via subprocess.run(shell=True, capture_output=True)
2. Parses stdout/stderr for test framework output
3. Strips all passing-test lines using framework-specific patterns
4. Returns only failure traces + summary + token savings stats

Pass-line patterns to strip (for major frameworks):
```python
PASS_PATTERNS = {
    "pytest":  [r"PASSED", r"passed", r"\.{1,}"],
    "junit":   [r"Tests run:.*Failures: 0", r"BUILD SUCCESS", r"OK \(\d+ test"],
    "maven":   [r"\[INFO\] Tests run:.*FAILURE: 0", r"\[INFO\] BUILD SUCCESS"],
    "gradle":  [r"\d+ tests completed"],
    "jest":    [r"PASS "],
    "mocha":   [r"passing"],
}
```

RESOLVED: Build tool is **Gradle** (system-installed, run as `gradle test`). NOT `./gradlew`.
Test command for Java projects: `gradle test`
For filtering: use junit/gradle pass-line patterns.

---

### Phase 3: Test Intelligence Engine [NOT STARTED]
**Requires: Phase 1 and Phase 2**

New file: mcp_server/analyzers/test_intelligence.py

New MCP tools:
- `get_changed_symbols(base_ref, head_ref)` — AST diff of two git refs
- `recommend_tests(file_path, base_ref="HEAD~1")` — ranked test list with confidence scores
- `run_recommended_tests(file_path, base_ref, dry_run=True)` — optionally run them

Confidence scoring algorithm:
1. 1.0 — Test file directly imports the changed file
2. 0.9 — Test calls a function that was changed (direct call-site match)
3. 0.7 — Test calls a function that calls the changed function (1-hop transitive)
4. 0.5 — Test is in the same package/module as the changed file
5. 0.3 — Historical co-failure (this test failed last N times this file changed, from git log)
6. Bonus +0.1 — Test was recently modified alongside the file

---

### Phase 4: Atlassian Integration [COMPLETED]
**Status: COMPLETED & VERIFIED (Data Center / Server)**

Directory: `mcp_server/integrations/atlassian/`
- `client.py` — Supports Bearer PATs (Data Center) & Basic Auth (Cloud)
- `jira_integration.py` — Jira issue search and creation
- `confluence_integration.py` — Confluence search, page retrieval, and publication
- `bitbucket_integration.py` — Bitbucket PR context and automated annotations
- `test_connection.py` — Verified connection to Jira, Confluence, and Bitbucket!

Exposed MCP tools:
- `get_jira_issues_for_file(file_path)` — Jira defects linked to a file
- `create_jira_issue(summary, description, issue_type)` — create defect from a finding
- `get_confluence_page(topic)` — retrieve knowledge base page content
- `get_pr_context(pr_id)` — Bitbucket PR blast radius analysis
- `annotate_pr(pr_id, comment_markdown)` — post CoPilotLens analysis as PR comment


---

### Phase 5: Neo4j Knowledge Graph [DOCUMENTED ONLY — NOT IMPLEMENTING]
**User decision: defer. Design captured in docs/neo4j_design.md**

What it would add:
- Persistent graph: File -> Symbol -> Test -> JiraIssue -> Author -> Dependency
- Cypher queries for: regression risk, transitive blast radius, author expertise, arch drift
- New MCP tools: query_code_graph(), get_regression_risk(), get_dependency_risks()
- Needs: Neo4j instance + neo4j>=5.0.0 pip package

---

### Phase 6: Coverity Integration [FILE PATH NEEDED]
**Requires: Phase 1**

New file: mcp_server/analyzers/coverity_analyzer.py

Input format: JSON from Coverity cov-format-errors --json-output-v8
Config: COVERITY_REPORT_PATH=/path/to/coverity_report.json

Expected JSON structure:
```json
{
  "issues": [
    {
      "mergeKey": "abc123",
      "checkerName": "NULL_RETURNS",
      "subcategory": "null_return",
      "type": "Error",
      "impact": "High",
      "file": "src/com/example/MyClass.java",
      "line": 142,
      "description": "...",
      "events": [...]
    }
  ]
}
```

New MCP tools:
- `get_coverity_findings(file_path)` — defects in one file
- `get_coverity_summary()` — all findings ranked by composite risk (churn + severity)
- `get_high_risk_coverity()` — Coverity defects that are also in git hotspot files

---

## Open Questions (Must Resolve Before Starting Relevant Phase)

| # | Question | Blocks | Answered? |
|---|---|---|---|
| 1 | Maven or Gradle? | Phase 2b, Phase 3 | YES — **Gradle (system install: `gradle test`, NOT `./gradlew`)** |
| 2 | Path to Coverity JSON file on disk | Phase 6 | NO |
| 3 | Atlassian base URL (https://yourco.atlassian.net) | Phase 4 | NO |
| 4 | Atlassian login email | Phase 4 | NO |
| 5 | Jira project key (e.g. PROJ from issue PROJ-123) | Phase 4 | NO |
| 6 | Confluence space key (from URL /wiki/spaces/KEY/) | Phase 4 | NO |
| 7 | Bitbucket type and URL | Phase 4 | YES — **Bitbucket Server (self-hosted). Base URL: `https://ies-iesd-bitbucket.ies.mentorg.com`. Project key: `IESD`. Repo: `iesd-26`. Uses Bitbucket Server REST API v1.** |

---

## Implementation Rules (Never Break These)

1. Never delete existing functionality. Regex analyzers become regex_fallback.py. All existing MCP tools must keep working.
2. All secrets via environment variables only. No hardcoded tokens/URLs anywhere.
3. Graceful degradation always. If Tree-sitter fails -> use regex. If Jira unreachable -> return error JSON. Never crash the MCP server.
4. Every new MCP tool needs a docstring explaining what it does, when to use it, and what args mean. Copilot reads these to decide when to call them.
5. Cache all expensive operations. Use the existing AnalysisCache in cache.py.
6. Java is the primary language — Java adapter must be production-quality. Others can be best-effort.
7. Test output filter must save 60-90% tokens. Validate with a real test run before marking Phase 2b done.
8. Windows compatibility required. User is on Windows/PowerShell. Use Path() from pathlib everywhere, never raw string paths.

---

## Environment / Runtime

- Python 3.9+ required
- User is on Windows (PowerShell)
- MCP server communicates via stdio (FastMCP handles MCP protocol)
- Dashboard served at http://localhost:8765 by a background HTTPServer thread in server.py
- Cache stored in .copilotlens_cache.json in the analyzed repo root
- Current requirements.txt: mcp>=1.0.0, gitpython>=3.1.40, click>=8.1.7

---

## How to Continue If You Are a New AI Model

1. Read this file (HANDOFF.md) completely first
2. Read mcp_server/server.py lines 1-97 for the server architecture
3. Read mcp_server/analyzers/dead_code.py to understand what Phase 2 replaces
4. Check the Open Questions table — resolve any unanswered items before starting the relevant phase
5. Start with Phase 1 (ast_engine.py + java_adapter.py) — it unblocks everything else
6. After each phase, update the Phase Status section in this file and docs/phase_status.md
7. Read docs/atlassian_setup.md before touching Phase 4
8. Read docs/coverity_setup.md before touching Phase 6
