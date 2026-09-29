# Phase Implementation Status

Last updated: 2026-09-27
Updated by: Antigravity (AI assistant)

This file tracks what has been done, what is in progress, and what is pending.
Update this after completing each phase or sub-task.

---

## Phase 1: Tree-sitter AST Engine
**Status: NOT STARTED**
**Priority: CRITICAL PATH**

### Tasks
- [ ] Install tree-sitter packages (add to requirements.txt)
- [ ] Create mcp_server/analyzers/adapters/ directory
- [ ] Create base_adapter.py (abstract interface)
- [ ] Create java_adapter.py (PRIMARY — do this first)
- [ ] Create python_adapter.py
- [ ] Create javascript_adapter.py
- [ ] Create typescript_adapter.py
- [ ] Create regex_fallback.py (wraps existing regex patterns from dead_code.py and dependency.py)
- [ ] Create ast_engine.py (dispatcher that picks correct adapter by file extension)
- [ ] Add new MCP tool: get_ast_symbols(file_path)
- [ ] Add new MCP tool: get_call_graph(file_path)
- [ ] Test on user's Java codebase
- [ ] Update HANDOFF.md phase status

### Notes
- Primary language is Java. Java adapter must be production quality.
- If tree_sitter import fails, fall back silently to regex_fallback.py
- Use tree-sitter>=0.21.0 (important: API changed significantly at 0.20)

---

## Phase 2: Dead Code v2 + Test Output Filter
**Status: NOT STARTED**
**Requires: Phase 1**

### Tasks
#### 2a — Dead code upgrade
- [ ] Rewrite dead_code.py to use AST call-graph from ast_engine.py
- [ ] Implement four confidence tiers: CONFIRMED / HIGH / MEDIUM / HEURISTIC
- [ ] Ensure backward compatibility (get_dead_code() tool still works, just better results)
- [ ] Test on Java codebase

#### 2b — Test output filter
- [ ] Create new MCP tool: run_and_filter_tests(test_command: str)
- [ ] Implement pattern stripping for: pytest, junit, maven, gradle, jest, mocha
- [ ] Return token savings percentage
- RESOLVED: Build tool is **Gradle (system install)**. Test command: `gradle test`
  Pass-line patterns to strip: `r"\d+ tests completed"`, `r"BUILD SUCCESSFUL"`, `r"Tests run: \d+.*Failures: 0"`


---

## Phase 3: Test Intelligence Engine
**Status: NOT STARTED**
**Requires: Phase 1, Phase 2**

### Tasks
- [ ] Create mcp_server/analyzers/test_intelligence.py
- [ ] Implement get_changed_symbols() using AST diff
- [ ] Implement test-to-symbol mapping using call graph
- [ ] Implement confidence scoring algorithm (6 levels, see HANDOFF.md)
- [ ] Add MCP tool: get_changed_symbols(base_ref, head_ref)
- [ ] Add MCP tool: recommend_tests(file_path, base_ref)
- [ ] Add MCP tool: run_recommended_tests(file_path, base_ref, dry_run)

---

## Phase 4: Atlassian Integration
**Status: COMPLETED**
**Tested against: Data Center / Server (Jira, Confluence, Bitbucket)**

### Configured Environment
- `JIRA_BASE_URL`: `https://ies-iesd-jira.ies.mentorg.com` (PAT auth)
- `CONFLUENCE_BASE_URL`: `https://ies-iesd-conf.ies.mentorg.com` (PAT auth)
- `BITBUCKET_BASE_URL`: `https://ies-iesd-bitbucket.ies.mentorg.com` (HTTP Access Token auth)

### Completed Tasks
- [x] Create `mcp_server/integrations/atlassian/` directory
- [x] Create `client.py` (Base HTTP client supporting Bearer PATs and Cloud Basic auth)
- [x] Create `jira_integration.py` (Issue lookup & creation)
- [x] Create `confluence_integration.py` (Search & page retrieval/publication)
- [x] Create `bitbucket_integration.py` (PR context & PR annotation)
- [x] Create `test_connection.py` (Verified 3/3 connections successfully!)
- [x] Add MCP tool: `get_jira_issues_for_file(file_path)`
- [x] Add MCP tool: `create_jira_issue(summary, description, issue_type)`
- [x] Add MCP tool: `get_confluence_page(topic)`
- [x] Add MCP tool: `get_pr_context(pr_id)`
- [x] Add MCP tool: `annotate_pr(pr_id, comment_markdown)`
- [x] Documented setup in `docs/atlassian_setup.md`


---

## Phase 5: Neo4j Knowledge Graph
**Status: DEFERRED — fully documented in docs/neo4j_design.md**

No implementation until user decides to proceed.

---

## Phase 6: Coverity Integration
**Status: WAITING FOR FILE PATH**

### Pending from user
- [ ] Path to Coverity JSON file on disk

### Tasks (once file path provided)
- [ ] Create mcp_server/analyzers/coverity_analyzer.py
- [ ] Parse Coverity JSON format (cov-format-errors --json-output-v8)
- [ ] Implement composite risk score (Coverity impact + git churn)
- [ ] Add MCP tool: get_coverity_findings(file_path)
- [ ] Add MCP tool: get_coverity_summary()
- [ ] Add MCP tool: get_high_risk_coverity()
- [ ] Add Coverity panel to dashboard (index.html + app.js)
- [ ] Document in coverity_setup.md
