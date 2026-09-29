# CoPilotLens — Change Summary (update.md)

> **Purpose:** Reference for anyone merging these changes into their branch.
> **Base commit:** `04d370c` (master — "Merge remote-tracking branch 'upstream/main'")
> **Date:** 2026-09-28

---

## ⚠️ Read First — Do NOT push `.env`

`.env` is untracked and contains **personal Atlassian credentials** (PATs/tokens).
It is **not** listed in `.gitignore`. Before committing:

```powershell
Add-Content .gitignore "`n# Local secrets`n.env"
git rm --cached .env 2>$null
```

Each developer must create their own `.env` (see [Configuration](#configuration--environment-variables)).

---

## At a Glance

| Status | Path | Summary |
|---|---|---|
| Modified | `mcp_server/server.py` | +225 lines: 12 new MCP tools (Atlassian + Capital XML/CLogic) |
| New | `mcp_server/integrations/atlassian/` | Jira / Confluence / Bitbucket REST clients |
| New | `mcp_server/analyzers/xml_analyzer.py` | Capital XML design & scenario analyzer |
| New | `mcp_server/analyzers/drc_validator.py` | Heuristic Capital Design Rule Checks |
| New | `mcp_server/analyzers/logic_action_generator.py` | Java Caplet Action + config + JUnit generator |
| New | `mcp_server/analyzers/clogic_session_analyzer.py` | Live CLogic/CManager session poller |
| New | `test_xml_analyzer.py` | Tests for `XmlAnalyzer` |
| New | `test_clogic_session_analyzer.py` | Tests for `CLogicSessionAnalyzer` |
| New | `.github/copilot/mcp.json` | Copilot MCP server registration |
| New | `docs/*.md` | Setup & design docs (Atlassian, Coverity, Neo4j, phase status) |
| New | `HANDOFF.md` | Master project handoff / context document |
| New (local only) | `.env` | **Secrets — do not commit** |

No changes to `requirements.txt`. All new code uses only the Python standard library
(`urllib`, `xml.etree`, `threading`, etc.), so there are **no new dependencies**.

---

## 1. `mcp_server/server.py` (modified, +225 lines)

### New imports
```python
from analyzers.xml_analyzer import XmlAnalyzer
from analyzers.logic_action_generator import LogicActionGenerator
from analyzers.drc_validator import DrcValidator
from analyzers.clogic_session_analyzer import CLogicSessionAnalyzer

# Imported inside a guarded block, so the server still starts if the integrations are missing
from integrations.atlassian.jira import jira_manager
from integrations.atlassian.confluence import confluence_manager
from integrations.atlassian.bitbucket import bitbucket_manager
```

### New MCP tools (`@mcp.tool()`)

**Atlassian: Jira**
| Tool | Signature | Description |
|---|---|---|
| `get_jira_issues_for_file` | `(file_path)` | Search Jira for open defects/tasks linked to a source file |
| `create_jira_issue` | `(summary, description, issue_type="Bug")` | Create a Bug/Task/Improvement |
| `update_jira_issue` | `(issue_key, append_description=None, new_summary=None)` | Append to the description and/or rename an issue |

**Atlassian: Confluence**
| Tool | Signature | Description |
|---|---|---|
| `get_confluence_page` | `(topic)` | Find a page by title/search text, or fetch it directly by numeric page ID |
| `update_confluence_page` | `(title_or_id, prepend_html=None, append_html=None)` | Add HTML to the top or bottom of a page |

**Atlassian: Bitbucket**
| Tool | Signature | Description |
|---|---|---|
| `get_pr_context` | `(pr_id)` | PR metadata: modified files, author, target branch |
| `annotate_pr` | `(pr_id, comment_markdown)` | Post a Markdown review comment on a PR |
| `get_recent_prs` | `(limit=5)` | List recent PRs (title, state, author, branches, URL) |

**Capital / CLogic domain**
| Tool | Signature | Description |
|---|---|---|
| `analyze_xml_design` | `(xml_input, detail="summary")` | Full structured report on a Capital XML file or string |
| `generate_logic_action` | `(action_name, target_object="DEVICE_CONNECTOR", package_name="chs.caplets.logic.actions")` | Generate a Java Caplet Action, XML config and JUnit test scaffold |
| `validate_design_drc` | `(xml_input)` | Run heuristic DRC checks on design XML |
| `inspect_live_clogic_session` | `(target_xml_or_session=None)` | Live or one-off CLogic design-state inspection |

Existing tools are **unchanged**.

---

## 2. `mcp_server/integrations/atlassian/` (new package)

| File | Role |
|---|---|
| `__init__.py` | Package marker |
| `client.py` | `AtlassianClient` base HTTP client (stdlib `urllib`). Auto-loads `.env` on import. Supports **Data Center/Server** (Bearer PAT) and **Cloud** (Basic auth with email + API token). |
| `jira.py` | `jira_manager`: issue search, create and update |
| `confluence.py` | `confluence_manager`: CQL search, fetch by ID, prepend/append content (increments the page version) |
| `bitbucket.py` | `bitbucket_manager`: PR list, PR context and PR comments |
| `test_connection.py` | Stand-alone script to check connectivity/credentials for each service |

`.env` lookup order: `<repo root>/.env`, then `<cwd>/.env`. Values already set in the real
environment take precedence.

---

## 3. New analyzers (`mcp_server/analyzers/`)

### `xml_analyzer.py`: `XmlAnalyzer` (~630 lines)
- Parses Capital XML exports (project exports, design actions, schematics). Namespace-agnostic.
- Separates **domain objects** (device, connector, backshell, pin, cavity, wire, multicore, splice,
  bundle, and so on) from **infrastructure tags** (glyphs, prefentries, diagram settings, and so on).
- Extracts instances, key attributes (`partnumber`, `libraryref`, `pintype`, `issealed`, …),
  containment, and ID references (attributes ending in `ref`, `target`, `owner`, `parent`, `baseid`).
- Builds logical-design hierarchy snapshots and pairs before/after changes.
- Optionally links objects to handling code through the search engine.
- `detail="summary"` (compact, sampled to 25) or `"full"`.

### `drc_validator.py`: `DrcValidator` (~110 lines)
Heuristic preflight checks. **This is not native Capital DRC.**
1. CheckCavityComponent: missing or unassigned cavity seals/plugs
2. CheckDanglingBundle: bundles with no node connections
3. CheckFitsCavity: wire gauge vs. cavity size
4. CapTopoCheckMulticorePathConsistency
5. CapTopoCheckRuleMinSpliceSeparation

Accepts an absolute path, a path relative to the repo, or an inline XML string.

### `logic_action_generator.py`: `LogicActionGenerator` (~125 lines)
Generates:
- A Java class extending `chs.caf.cafmain.actions.AbstractAction`
- A `config.xml` action definition snippet
- A JUnit component test scaffold

### `clogic_session_analyzer.py`: `CLogicSessionAnalyzer` (~420 lines)
- Background **thread** that polls CLogic session XML and CLogic/CManager logs (default every 2 s).
- Keeps up to 200 recent add/change/remove events.
- Reports placed objects, change events, next-step suggestions and a QA reproduction checklist.
- Can reuse `XmlAnalyzer` and `DrcValidator`.
- Best-effort file/log polling. It does not use a native CLogic event hook.

---

## 4. Tests (repo root)

| File | Covers |
|---|---|
| `test_xml_analyzer.py` | `XmlAnalyzer` parsing, inventory, hierarchy and references |
| `test_clogic_session_analyzer.py` | `CLogicSessionAnalyzer` snapshot and change detection |

Run the tests:
```powershell
python -m pytest test_xml_analyzer.py test_clogic_session_analyzer.py -v
```

---

## 5. Config & docs

| File | Description |
|---|---|
| `.github/copilot/mcp.json` | Registers the `copilotlens` MCP server (`python C:/CoPilotLens/mcp_server/server.py --repo ${workspaceFolder}`, `COPILOTLENS_PORT=8765`). **Contains a hard-coded `C:/CoPilotLens` path. Change it to match your local path.** |
| `docs/atlassian_setup.md` | How to create PATs/tokens and configure `.env` |
| `docs/coverity_setup.md` | Coverity integration setup |
| `docs/neo4j_design.md` | Proposed Neo4j graph model design |
| `docs/phase_status.md` | Roadmap / phase completion status |
| `HANDOFF.md` | Master context document: layout, architecture, tools, next steps |

---

## Configuration / Environment Variables

Create `.env` in the repo root. Only set the variables you need:

```ini
# --- Data Center / Server (Bearer PAT) ---
JIRA_BASE_URL=https://<your-jira-host>
JIRA_PAT=
CONFLUENCE_BASE_URL=https://<your-confluence-host>
CONFLUENCE_PAT=
BITBUCKET_BASE_URL=https://<your-bitbucket-host>
BITBUCKET_TOKEN=
BITBUCKET_PROJECT_KEY=IESD
BITBUCKET_REPO_SLUG=iesd-26

# --- Cloud alternative (Basic auth) ---
# ATLASSIAN_BASE_URL=https://<org>.atlassian.net
# ATLASSIAN_EMAIL=
# ATLASSIAN_API_TOKEN=
# BITBUCKET_USERNAME=
# BITBUCKET_APP_PASSWORD=
# BITBUCKET_WORKSPACE=
# BITBUCKET_REPO=

# --- Optional: CLogic live session monitoring ---
# CLOGIC_SESSION_DIR=
# CLOGIC_SESSION_XML=
# CLOGIC_LOG_PATH=
# CMANAGER_LOG_PATH=

# --- Existing ---
# COPILOTLENS_REPO=
# COPILOTLENS_PORT=8765
```

---

## Integration Steps for Other Branches

1. Pull or merge the branch.
2. **`mcp_server/server.py` is the only modified file**, so it is the only possible merge conflict.
   The changes are additions: new imports at the top and new `@mcp.tool()` functions. Keep both sides.
3. All other changes are **new files**. They will not conflict unless the same paths exist on your branch.
4. Create your own `.env` (template above). It is never shared.
5. Update the path in `.github/copilot/mcp.json` if your clone is not at `C:/CoPilotLens`.
6. Restart the MCP server or IDE so Copilot picks up the new tools.
7. Optional: check the Atlassian setup with
   `python mcp_server/integrations/atlassian/test_connection.py`.
8. Run the tests (section 4).

---

## Suggested Commit

```powershell
Add-Content .gitignore "`n# Local secrets`n.env"
git add .gitignore mcp_server/ .github/ docs/ HANDOFF.md update.md test_xml_analyzer.py test_clogic_session_analyzer.py
git status   # confirm .env is NOT staged
git commit -m "Add Atlassian (Jira/Confluence/Bitbucket) integrations and Capital XML/DRC/CLogic analyzers as MCP tools"
```

