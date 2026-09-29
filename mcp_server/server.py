"""
CopilotLens MCP Server
======================
Exposes codebase intelligence as MCP tools for GitHub Copilot (Agent Mode).

Usage:
    python server.py --repo /path/to/your/project

MCP Tools exposed:
    - get_file_health      : Score a specific file (0-100)
    - get_hotspots         : Top N high-churn / risky files
    - get_codebase_summary : Overall health overview
    - get_dead_code        : Unused functions/classes
    - get_dependency_graph : Import dependency map
    - get_file_dependencies: Dependencies for a specific file
    - get_module_owners    : Who owns each module (git blame aggregated)
    - generate_copilot_instructions : Generate copilot-instructions.md
    - get_dashboard_url    : URL to the visual dashboard

Dashboard:
    Served at http://localhost:8765
"""

import argparse
import json
import os
import sys
import threading
import time
from typing import Any, Dict, List, Optional
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

# Add parent dir to path so we can import analyzers
sys.path.insert(0, str(Path(__file__).parent))

try:
    from mcp.server.fastmcp import FastMCP
except ModuleNotFoundError:
    from mcp.server.mcpserver import MCPServer as FastMCP
from analyzers.git_analyzer import GitAnalyzer
from analyzers.code_health import CodeHealthScorer
from analyzers.dependency import DependencyAnalyzer
from analyzers.dead_code import DeadCodeDetector
from analyzers.dead_code_ast import ASTDeadCodeDetector
from analyzers.cache import AnalysisCache
from analyzers.why_analyzer import WhyAnalyzer
from analyzers.search_analyzer import CodebaseSearch
from analyzers.blast_radius import BlastRadiusAnalyzer
from analyzers.policy_repo import PolicyRepository, CopilotInteractionAnalyzer
from analyzers.smart_test_analyzer import SmartTestAnalyzer
from analyzers.codebase_graph import CodebaseKnowledgeGraph
from analyzers.coverity_analyzer import CoverityAnalyzer
from analyzers.neo4j_analyzer import Neo4jAnalyzer
from analyzers.xml_analyzer import XmlAnalyzer
from analyzers.logic_action_generator import LogicActionGenerator
from analyzers.drc_validator import DrcValidator
from analyzers.clogic_session_analyzer import CLogicSessionAnalyzer
from analyzers.context_scraper import ContextScraper
from analyzers.psi_analyzer import PsiToolsAnalyzer

# Atlassian Integrations
try:
    from integrations.atlassian.jira import jira_manager
    from integrations.atlassian.confluence import confluence_manager
    from integrations.atlassian.bitbucket import bitbucket_manager
    ATLASSIAN_AVAILABLE = True
except Exception:
    ATLASSIAN_AVAILABLE = False

# ─── Argument Parsing ──────────────────────────────────────────────────────────

def get_repo_path() -> str:
    """Get repo path from CLI args or environment variable."""
    path = None
    if "--repo" in sys.argv:
        idx = sys.argv.index("--repo")
        if idx + 1 < len(sys.argv):
            path = sys.argv[idx + 1]
    
    # If the IDE failed to expand the VS Code-style variable, or it's missing, use a fallback
    if not path or path == "${workspaceFolder}":
        path = os.environ.get("COPILOTLENS_REPO")
        
    if not path or path == "${workspaceFolder}":
        # Fallback to the repository root (parent of the mcp_server directory)
        path = str(Path(__file__).parent.parent.absolute())
        
    return path


REPO_PATH = get_repo_path()
DASHBOARD_PORT = int(os.environ.get("COPILOTLENS_PORT", "8765"))

# ─── Initialize Analyzers ──────────────────────────────────────────────────────

cache = AnalysisCache(REPO_PATH)
git_analyzer = GitAnalyzer(REPO_PATH)
health_scorer = CodeHealthScorer(REPO_PATH)
dep_analyzer = DependencyAnalyzer(REPO_PATH)
dead_code_detector = DeadCodeDetector(REPO_PATH)
ast_dead_code_detector = ASTDeadCodeDetector(REPO_PATH)
why_analyzer = WhyAnalyzer(REPO_PATH)
search_engine = CodebaseSearch(REPO_PATH)
blast_analyzer = BlastRadiusAnalyzer(REPO_PATH, dep_analyzer, git_analyzer)
policy_repo = PolicyRepository(REPO_PATH)
interaction_analyzer = CopilotInteractionAnalyzer(REPO_PATH)
smart_test_analyzer = SmartTestAnalyzer(REPO_PATH)
knowledge_graph = CodebaseKnowledgeGraph(REPO_PATH)
coverity_analyzer = CoverityAnalyzer(REPO_PATH)
neo4j_analyzer = Neo4jAnalyzer()
xml_analyzer = XmlAnalyzer(REPO_PATH, search_engine=search_engine)
action_generator = LogicActionGenerator(REPO_PATH)
drc_validator = DrcValidator(REPO_PATH)
clogic_session_analyzer = CLogicSessionAnalyzer(REPO_PATH, xml_analyzer=xml_analyzer, drc_validator=drc_validator)
clogic_session_analyzer.start_monitoring()
context_scraper = ContextScraper(REPO_PATH)
psi_analyzer = PsiToolsAnalyzer()

# ─── MCP Server ────────────────────────────────────────────────────────────────

mcp = FastMCP(
    name="CopilotLens",
    instructions=f"""
You have access to CopilotLens — a codebase intelligence layer for the repository at: {REPO_PATH}

Use these tools to:
- Understand code health BEFORE suggesting refactors
- Identify risky/hotspot files that need extra care
- Check who owns a module before suggesting changes
- Find dead code that can be safely removed (AST-level verification)
- Understand architectural dependencies before restructuring
- Learn and enforce project-specific conventions via the policy system
- Navigate the Capital Neo4j code graph or IntelliJ PSI semantic tree to find relevant classes and call graphs
- Query Capital Logic (CLogic) live design sessions, DRC rule checks, and XML actions
- Scrape extensive cross-platform context across Jira tickets, Confluence pages, and Bitbucket PRs
- Leverage native IntelliJ PSI tools (port 3000/3001) for class structure, call graphs, usages, and inspections

IMPORTANT WORKFLOW RULES:
1. Always call get_file_health() before suggesting changes to a specific file.
2. Always call get_hotspots() when asked about risky or problematic areas of the codebase.
3. Always call get_copilot_context(file_path) at the start of any coding task to load approved project rules.
4. When a developer says "Do not...", "Never...", "Always use...", "Remember this rule:", or corrects your output,
   call analyze_copilot_interaction(interaction_text, auto_approve_high_confidence=True) to extract, store, and approve the rule into the policy repository.
5. When a developer says "remember this rule" or gives an explicit directive, call remember_rule(rule=..., auto_approve=True) to store and activate it immediately.
6. Use get_project_rules() to list all stored conventions at any time.
7. Use review_policy_rule(rule_id, action) to approve/reject/edit rules on developer request.
8. When asked about class relationships, dependencies, or architectural context for Java code,
   use psi_get_class_structure(), psi_find_usages(), or psi_get_call_graph() for real-time IDE fidelity, or neo4j_find_class() / neo4j_expand_both().
9. When inspecting CLogic sessions or Capital XML designs, use get_clogic_session_status() and validate_drc_rule().
10. When extensive background context is needed, call scrape_enterprise_context(keyword).
"""
)


@mcp.tool()
def get_file_health(file_path: str) -> str:
    """
    Get the health score and breakdown for a specific file.
    Returns a score from 0 (critical) to 100 (excellent) with detailed markers explaining the score.
    Use this BEFORE suggesting refactoring or changes to any file.
    
    Args:
        file_path: Relative path to the file from the repository root (e.g., 'src/main/App.java')
    """
    cached = cache.get(f"health:{file_path}")
    if cached:
        return json.dumps(cached, indent=2)
    
    result = health_scorer.score_file(file_path)
    result["path"] = file_path
    result["repo"] = REPO_PATH
    
    # Add actionable advice based on markers
    advice = []
    for marker in result.get("markers", []):
        if marker["impact"] < 0:
            mid = marker["id"]
            if mid == "file_too_large":
                advice.append("⚠️ This file is too large. Consider splitting it into smaller modules.")
            elif mid == "long_functions":
                advice.append("⚠️ Long functions detected. Extract into smaller, focused functions.")
            elif mid == "deeply_nested":
                advice.append("⚠️ Deep nesting found. Consider early returns or extracting methods.")
            elif mid == "too_many_todos":
                advice.append(f"⚠️ {marker.get('detail', 'Multiple TODO/FIXME')} — technical debt accumulating.")
            elif mid == "no_comments":
                advice.append("⚠️ No documentation. Add docstrings/comments before modifying.")
            elif mid == "high_complexity":
                advice.append("⚠️ High cyclomatic complexity. Any change here has high defect risk.")
    
    result["copilot_advice"] = advice
    cache.set(f"health:{file_path}", result)
    return json.dumps(result, indent=2)


@mcp.tool()
def get_hotspots(top_n: int = 10) -> str:
    """
    Get the top N hotspot files — files with the highest churn rate (frequently changed).
    High-churn files are statistically the most defect-prone.
    Use this to identify risky areas before any large refactoring effort.
    
    Args:
        top_n: Number of hotspot files to return (default: 10, max: 30)
    """
    top_n = min(top_n, 30)
    cached = cache.get(f"hotspots:{top_n}")
    if cached:
        return json.dumps(cached, indent=2)
    
    hotspots = git_analyzer.get_hotspots(top_n)
    
    result = {
        "hotspots": hotspots,
        "insight": (
            f"The top {len(hotspots)} hotspot files account for the highest change frequency. "
            "Files with CRITICAL or HIGH risk need careful review before modification. "
            "Consider adding tests before touching these files."
        ),
        "repo": REPO_PATH
    }
    
    cache.set(f"hotspots:{top_n}", result)
    return json.dumps(result, indent=2)


@mcp.tool()
def get_codebase_summary() -> str:
    """
    Get a comprehensive health summary of the entire codebase.
    Returns average health score, grade distribution, worst and best files,
    git activity summary, and high-level architectural insights.
    Use this for an overall assessment before starting any large task.
    """
    cached = cache.get("summary")
    if cached:
        return json.dumps(cached, indent=2)
    
    health_summary = health_scorer.get_summary()
    repo_summary = git_analyzer.get_repo_summary()
    
    result = {
        "repo_path": REPO_PATH,
        "health": health_summary,
        "git_activity": repo_summary,
        "dashboard_url": f"http://localhost:{DASHBOARD_PORT}",
        "interpretation": _interpret_summary(health_summary)
    }
    
    cache.set("summary", result)
    return json.dumps(result, indent=2)


@mcp.tool()
def get_dead_code() -> str:
    """
    Find functions, classes, imports, and variables that are defined but never used.
    Uses AST multi-language adapters (Python, JS, TS, Java) with Tree-sitter to distinguish
    CONFIRMED_ISSUE (AST-verified unused private/local symbols, unused imports)
    from HEURISTIC_CANDIDATE (public exported functions with 0 static callers).
    """
    cached = cache.get("dead_code_ast")
    if cached:
        return json.dumps(cached, indent=2)
    
    dead = ast_dead_code_detector.find_dead_code()
    confirmed = [d for d in dead if d.get("category") == "CONFIRMED_ISSUE"]
    heuristics = [d for d in dead if d.get("category") == "HEURISTIC_CANDIDATE"]

    result = {
        "dead_code_candidates": dead,
        "count": len(dead),
        "confirmed_issues_count": len(confirmed),
        "heuristic_candidates_count": len(heuristics),
        "insight": (
            f"Found {len(confirmed)} AST-confirmed dead code issues and {len(heuristics)} heuristic candidates. "
            "CONFIRMED_ISSUE items are private/internal unused symbols or imports safe to remove. "
            "HEURISTIC_CANDIDATE items are public symbols that might be called externally."
        ),
        "repo": REPO_PATH
    }
    
    cache.set("dead_code_ast", result)
    return json.dumps(result, indent=2)


@mcp.tool()
def get_dependency_graph() -> str:
    """
    Get the full import/dependency graph of the codebase.
    Shows which files import which, identifies hub files (imported by 5+ others),
    circular dependencies, and orphan files.
    Use this before restructuring or extracting modules.
    """
    cached = cache.get("dependency_graph")
    if cached:
        return json.dumps(cached, indent=2)
    
    graph = dep_analyzer.build_graph()
    
    # Add insights
    hubs = [n for n in graph["nodes"] if n.get("is_hub")]
    circular = graph.get("circular_dependencies", [])
    
    insights = []
    if hubs:
        hub_names = [h["id"] for h in hubs[:5]]
        insights.append(f"🔗 Hub files (high coupling): {', '.join(hub_names)}")
    if circular:
        insights.append(f"🔄 {len(circular)} circular dependency chain(s) detected — refactoring these will be complex")
    if graph.get("orphan_files"):
        insights.append(f"🌿 {len(graph['orphan_files'])} orphan files found — potential dead code or entry points")
    
    graph["insights"] = insights
    cache.set("dependency_graph", graph)
    return json.dumps(graph, indent=2)


@mcp.tool()
def get_file_dependencies(file_path: str) -> str:
    """
    Get the specific import dependencies for a single file.
    Shows what this file imports AND what imports it (reverse dependencies).
    Use this before modifying a file to understand blast radius.
    
    Args:
        file_path: Relative path to the file from the repository root
    """
    deps = dep_analyzer.get_file_dependencies(file_path)
    
    blast_radius = len(deps["imported_by"])
    deps["blast_radius_warning"] = (
        f"⚠️ Modifying this file could affect {blast_radius} other file(s)."
        if blast_radius > 0 else
        "✅ This file is not imported by others — changes are isolated."
    )
    
    return json.dumps(deps, indent=2)


@mcp.tool()
def get_module_owners() -> str:
    """
    Get ownership information for codebase modules based on git history.
    Shows which team member/email has the most commits on each file.
    Files with low bus factor (1 owner) are high knowledge-concentration risk.
    Use this to understand who to consult before changing specific areas.
    """
    cached = cache.get("owners")
    if cached:
        return json.dumps(cached, indent=2)
    
    owners = git_analyzer.get_module_owners()
    single_owner = [o for o in owners if o["bus_factor"] == 1]
    
    result = {
        "module_owners": owners[:30],
        "single_owner_risk": {
            "count": len(single_owner),
            "files": [o["path"] for o in single_owner[:10]],
            "insight": (
                f"{len(single_owner)} file(s) have only 1 contributor — "
                "these represent knowledge concentration risk (bus factor = 1)."
                if single_owner else "No single-owner files detected."
            )
        },
        "repo": REPO_PATH
    }
    
    cache.set("owners", result)
    return json.dumps(result, indent=2)


# ─── New Tools: Feature Parity with RepoWise ──────────────────────────────────

@mcp.tool()
def get_why(file_path: str) -> str:
    """
    Explain WHY a file exists and WHY it changed the way it did.
    Uses git archaeology: analyzes commit messages, PR descriptions, and inline
    decision comments (TODO, FIXME, HACK, NOTE, REASON, WORKAROUND) for this file.
    Use this when you need historical context before modifying legacy code.

    Args:
        file_path: Relative path to the file from the repository root
    """
    cached = cache.get(f"why:{file_path}")
    if cached:
        return json.dumps(cached, indent=2)

    result = why_analyzer.get_why(file_path)
    cache.set(f"why:{file_path}", result)
    return json.dumps(result, indent=2)


@mcp.tool()
def search_codebase(query: str, search_type: str = "text", file_extension: str = "") -> str:
    """
    Search across the entire codebase for a query string, pattern, or symbol name.
    Returns matching files, line numbers, and surrounding context.

    Use this to:
    - Find all usages of a function or class name: search_type="symbol"
    - Find all places a pattern occurs: search_type="text"
    - Find patterns with regex: search_type="regex"

    Args:
        query: The text, symbol name, or regex pattern to search for
        search_type: "text" (default), "symbol" (word-boundary match), or "regex"
        file_extension: Optional filter e.g. ".js" or ".py" (leave empty for all)
    """
    ext = file_extension if file_extension else None
    result = search_engine.search(
        query=query,
        search_type=search_type,
        max_results=20,
        context_lines=2,
        file_extension=ext
    )
    return json.dumps(result, indent=2)


@mcp.tool()
def find_symbol_usages(symbol_name: str) -> str:
    """
    Find where a specific function, class, or variable is defined and where it is used.
    Returns: definition location, all files that use it, and whether it might be dead code.
    More precise than search_codebase for tracking a specific named symbol.

    Args:
        symbol_name: The function, class, or variable name to look up
    """
    result = search_engine.find_symbol_usages(symbol_name)
    return json.dumps(result, indent=2)


@mcp.tool()
def get_co_change_pairs() -> str:
    """
    Find files that are ALWAYS modified together in the same commit — hidden coupling.
    These files are behaviorally coupled even if they don't import each other.
    Essential context before any refactoring: changing one will likely require changing the other.
    High coupling strength = change them together or risk breaking behavior.
    """
    cached = cache.get("co_change_pairs")
    if cached:
        return json.dumps(cached, indent=2)

    pairs = git_analyzer.get_co_change_pairs(min_co_changes=3)

    result = {
        "co_change_pairs": pairs,
        "total_pairs": len(pairs),
        "high_coupling": [p for p in pairs if p["coupling_strength"] == "HIGH"],
        "insight": (
            f"Found {len(pairs)} file pairs with hidden coupling. "
            f"{len([p for p in pairs if p['coupling_strength'] == 'HIGH'])} HIGH-strength pairs "
            f"should always be changed together."
        )
    }

    cache.set("co_change_pairs", result)
    return json.dumps(result, indent=2)


@mcp.tool()
def get_named_imports(file_path: str) -> str:
    """
    Get symbol-level import analysis for a specific file.
    Shows exactly WHICH functions/classes this file imports from other modules
    (e.g. `import { useState, useEffect } from 'react'` -> symbols: [useState, useEffect]).
    More granular than get_file_dependencies which only shows file-level imports.

    Args:
        file_path: Relative path to the file from the repository root
    """
    result = dep_analyzer.get_named_imports(file_path)
    return json.dumps(result, indent=2)


@mcp.tool()
def get_blast_radius(file_path: str) -> str:
    """
    Calculate the exact blast radius and minimal review set for a given file or list of files.
    Traces direct dependents, historical co-change partners, and associated test files.
    Returns:
    - minimal_review_set (exact files to read/review)
    - token_savings (percentage reduction & multiplier vs reading the whole codebase)

    Args:
        file_path: Target file path (or comma-separated list of paths) to analyze
    """
    result = blast_analyzer.calculate_blast_radius(file_path)
    return json.dumps(result, indent=2)








@mcp.tool()
def analyze_changed_symbols(file_path: str, diff_content: str = "") -> str:
    """
    AST-based analysis of changed symbols, modified imports, call relationships, test conventions,
    and impacted downstream tests across Python, JavaScript, TypeScript, and Java.

    Args:
        file_path: Relative path to target file
        diff_content: Optional diff patch content to pinpoint exact modified lines
    """
    res = smart_test_analyzer.analyze_changed_symbols(file_path, diff_content)
    return json.dumps(res, indent=2)


@mcp.tool()
def recommend_tests(changed_files: str) -> str:
    """
    Recommend the smallest relevant test set for changed files with confidence scores and explanations.
    Uses direct naming conventions, dependency graph tracing, and historical co-change coupling.

    Args:
        changed_files: Comma-separated list of changed file paths e.g. 'mcp_server/server.py'
    """
    file_list = [f.strip() for f in changed_files.split(",") if f.strip()]
    res = smart_test_analyzer.recommend_tests(file_list)
    return json.dumps(res, indent=2)


@mcp.tool()
def distill_test_output(raw_output: str) -> str:
    """
    Captures raw test stdout/stderr, filters out passing items and verbose logs,
    and distills down strictly to failure trace lines using AST/pattern diagnostics (saving 60-90% output tokens).

    Args:
        raw_output: Verbose test stdout/stderr output string
    """
    res = smart_test_analyzer.distill_test_output(raw_output)
    return json.dumps(res, indent=2)


@mcp.tool()
def run_recommended_tests(test_files: str = "", filter_pattern: str = "") -> str:
    """
    Optionally run recommended test suites locally, capture stdout/stderr,
    and return token-distilled failure trace diagnostics.

    Args:
        test_files: Optional comma-separated test file paths (leave empty to auto-recommend)
        filter_pattern: Optional filter pattern for test runner
    """
    t_list = [f.strip() for f in test_files.split(",") if f.strip()] if test_files else None
    res = smart_test_analyzer.run_recommended_tests(t_list, filter_pattern)
    return json.dumps(res, indent=2)


@mcp.tool()
def query_codebase_graph(target: str, max_depth: int = 2) -> str:
    """
    Explore multi-hop relationships between code, dependencies, tests, git hotspots, defect risks, and policy rules.
    Provides local graph query capability without requiring external Neo4j setup.

    Args:
        target: Target file path or symbol name to query graph relationships
        max_depth: Maximum relationship hop depth (default: 2)
    """
    res = knowledge_graph.query_graph(target, max_depth=max_depth)
    return json.dumps(res, indent=2)


# ─── Atlassian MCP Tools ───────────────────────────────────────────────────────

@mcp.tool()
def get_jira_issues_for_file(file_path: str) -> str:
    """
    Search Jira for open defects, bugs, or tasks linked to a specific source file.

    Args:
        file_path: Relative path to the file (e.g., 'src/service/UserService.java')
    """
    if not ATLASSIAN_AVAILABLE:
        return json.dumps({"error": "Atlassian integration modules not available."})
    res = jira_manager.get_issues_for_file(file_path)
    return json.dumps(res, indent=2)


@mcp.tool()
def create_jira_issue(summary: str, description: str, issue_type: str = "Bug") -> str:
    """
    Create a new Jira issue (Bug, Task, etc.) directly from CoPilotLens findings.

    Args:
        summary: Short title of the issue
        description: Detailed explanation, code snippet, or steps to reproduce
        issue_type: Type of issue ('Bug', 'Task', 'Improvement', default is 'Bug')
    """
    if not ATLASSIAN_AVAILABLE:
        return json.dumps({"error": "Atlassian integration modules not available."})
    res = jira_manager.create_issue(summary, description, issue_type)
    return json.dumps(res, indent=2)


@mcp.tool()
def update_jira_issue(issue_key: str, append_description: str = None, new_summary: str = None) -> str:
    """
    Update an existing Jira issue by appending text to its description or changing its summary.

    Args:
        issue_key: The issue key (e.g. 'PVC-4464')
        append_description: Optional text to append to the existing issue description
        new_summary: Optional new summary/title for the issue
    """
    if not ATLASSIAN_AVAILABLE:
        return json.dumps({"error": "Atlassian integration modules not available."})
    res = jira_manager.update_issue(issue_key, summary=new_summary, append_description=append_description)
    return json.dumps(res, indent=2)


@mcp.tool()
def get_confluence_page(topic: str) -> str:
    """
    Retrieve architecture, design, or health documentation from Confluence.

    Args:
        topic: Topic, title, or search terms to look up in Confluence
    """
    if not ATLASSIAN_AVAILABLE:
        return json.dumps({"error": "Atlassian integration modules not available."})
    res = confluence_manager.get_page(topic)
    return json.dumps(res, indent=2)


@mcp.tool()
def update_confluence_page(title_or_id: str, prepend_html: str = None, append_html: str = None) -> str:
    """
    Edit an existing Confluence page by prepending or appending text/HTML content.

    Args:
        title_or_id: Title or page ID of the Confluence page to edit
        prepend_html: Text/HTML content to add to the TOP of the page
        append_html: Text/HTML content to add to the BOTTOM of the page
    """
    if not ATLASSIAN_AVAILABLE:
        return json.dumps({"error": "Atlassian integration modules not available."})
    res = confluence_manager.update_page(title_or_id, prepend_html=prepend_html, append_html=append_html)
    return json.dumps(res, indent=2)


@mcp.tool()
def get_pr_context(pr_id: str) -> str:
    """
    Fetch Pull Request metadata from Bitbucket (modified files, author, target branch).

    Args:
        pr_id: Pull Request ID or key (e.g. '42')
    """
    if not ATLASSIAN_AVAILABLE:
        return json.dumps({"error": "Atlassian integration modules not available."})
    res = bitbucket_manager.get_pr_context(pr_id)
    return json.dumps(res, indent=2)


@mcp.tool()
def annotate_pr(pr_id: str, comment_markdown: str) -> str:
    """
    Post a review comment or code health analysis to a Bitbucket Pull Request.

    Args:
        pr_id: Pull Request ID or key (e.g. '42')
        comment_markdown: Markdown formatted feedback or review analysis
    """
    if not ATLASSIAN_AVAILABLE:
        return json.dumps({"error": "Atlassian integration modules not available."})
    res = bitbucket_manager.annotate_pr(pr_id, comment_markdown)
    return json.dumps(res, indent=2)


@mcp.tool()
def get_recent_prs(limit: int = 5) -> str:
    """
    Fetch recent Pull Requests from Bitbucket and return their details and summaries.

    Args:
        limit: Number of recent PRs to retrieve (default is 5)
    """
    if not ATLASSIAN_AVAILABLE:
        return json.dumps({"error": "Atlassian integration modules not available."})
    res = bitbucket_manager.get_recent_prs(limit=limit)
    return json.dumps(res, indent=2)


@mcp.tool()
def scrape_extended_context(
    topic: str,
    max_jira: int = 10,
    max_confluence: int = 10,
    max_bitbucket: int = 10,
    min_relevance: float = 0.5
) -> str:
    """
    Scrapes comprehensive cross-system context across Jira, Confluence, and Bitbucket for a given keyword or topic.
    Applies BM25 semantic relevance ranking to filter out incidental keyword matches and retain genuine domain context.
    All extracted tickets, design pages, and pull requests are persisted into a local SQLite database for reuse.
    Returns a structured Markdown report followed by structured JSON for Copilot prompt and context injection.

    Args:
        topic: The concept, class name, feature, or keyword to investigate (e.g. 'HarnessAssembly', 'OVERBRAIDCHILD', 'Multicore')
        max_jira: Maximum number of relevant Jira issues to return (default: 10)
        max_confluence: Maximum number of relevant Confluence design pages to return (default: 10)
        max_bitbucket: Maximum number of relevant Bitbucket PRs to return (default: 10)
        min_relevance: Minimum BM25 semantic relevance score threshold (default: 0.5)
    """
    if not ATLASSIAN_AVAILABLE:
        return json.dumps({"error": "Atlassian integration modules not available. Check your .env file."})
    res = context_scraper.scrape_and_index_context(
        topic=topic,
        max_jira=max_jira,
        max_confluence=max_confluence,
        max_bitbucket=max_bitbucket,
        min_relevance_threshold=min_relevance
    )
    markdown = res.pop("context_markdown", "")
    return f"{markdown}\n\n---\n## Structured Context Data (JSON)\n```json\n{json.dumps(res, indent=1)}\n```"


@mcp.tool()
def get_cached_context(topic: str, limit: int = 30) -> str:
    """
    Retrieve previously scraped and indexed Atlassian context items (Jira, Confluence, Bitbucket)
    from the local SQLite knowledge database without making new remote API calls.

    Args:
        topic: Topic or keyword to retrieve cached context for
        limit: Maximum number of cached items to return (default: 30)
    """
    items = context_scraper.db.get_context_for_topic(topic, limit=limit)
    stats = context_scraper.db.get_stats()
    return json.dumps({"topic": topic, "count": len(items), "db_stats": stats, "items": items}, indent=2)


# ─── Capital / CLogic Tools ───────────────────────────────────────────────────

@mcp.tool()
def analyze_xml_design(xml_input: str, detail: str = "summary") -> str:
    """
    Analyze a Capital XML file or raw XML string and return its complete structured report:
    document metadata and tag inventory; object instances, attributes, containment, and ID references;
    logical-design snapshots (hierarchy trees) and paired before/after changes; related source files;
    evidence-based scenario interpretations; and conditional object/scenario ideas with downstream uses.
    The response starts with a human-readable Markdown report — present it to the user in full,
    followed by any extra detail from the JSON. Treat the XML as serialized state, distinguish
    filename-derived hypotheses from confirmed contents, and do not invent details not in the report.

    Args:
        xml_input: Absolute/relative XML file path or raw XML string
        detail: "summary" (default, compact) or "full" (every instance, attribute and reference)
    """
    res = xml_analyzer.analyze_xml(xml_input, detail=detail)
    if res.get("error"):
        return json.dumps(res, indent=2)
    markdown = res.pop("report_markdown")
    return markdown + "\n\n---\n## Structured data (JSON)\n```json\n" + json.dumps(res, indent=1) + "\n```"


@mcp.tool()
def generate_logic_action(action_name: str, target_object: str = "", package_name: str = "chs.caplets.logic.actions",
                          spec_json: str = "") -> str:
    """
    Step 1 of the Capital Logic Action Change Set workflow: PLAN a new Logic action.
    Scans the Capital repo (spec.capital_repo / $CAPITAL_REPO) for sibling actions, LogicController
    registrations, LogicResource menus/toolbars, ribbon.xml groups, bundles and derivative controllers,
    and returns a question for every undecided product decision (action type, selection, mutation,
    applications, menu, ribbon group, gating, immersed mode...). Nothing is guessed or written.
    Ask the developer every blocking question, merge the answers into spec_json and call again until
    status == "ready", then call generate_logic_action_changeset.

    Args:
        action_name: Action class name (e.g. 'RefreshConnectivityAction')
        target_object: Optional target object / selection type (e.g. 'DEVICE_CONNECTOR')
        package_name: Java package (default 'chs.caplets.logic.actions')
        spec_json: Optional full ActionSpec JSON (fields listed in the plan's questions)
    """
    res = action_generator.generate_action(action_name, target_object or None, package_name, spec_json)
    return json.dumps(res, indent=2, default=str)


@mcp.tool()
def generate_logic_action_changeset(spec_json: str) -> str:
    """
    Step 2: build the full Logic Action Change Set for a spec whose plan is "ready":
    Action + ActionUI + JUnit 3 test, LogicController/derivative registration, LogicResource
    menu/toolbar registration, resource bundle keys (+ localization report), ribbon.xml button and
    ribbon keys, icon checks and validation. Returns unified diffs and a changeset_id. Writes nothing
    to the Capital repo. Present the report and diffs to the developer for review.

    Args:
        spec_json: Complete ActionSpec JSON (same as used for planning)
    """
    res = action_generator.generate_changeset(spec_json)
    markdown = res.pop("report_markdown", None)
    body = json.dumps(res, indent=2, default=str)
    return (markdown + "\n\n---\n```json\n" + body + "\n```") if markdown else body


@mcp.tool()
def apply_logic_action_changeset(changeset_id: str, run_build: bool = False) -> str:
    """
    Step 3: apply a reviewed Logic Action Change Set to the Capital repo. Refuses if any target file
    changed since generation and rolls back on write failure. With run_build=true, runs
    $CAPITAL_BUILD_CMD and $CAPITAL_TEST_CMD ({test_class}/{test_fqn} placeholders).

    Args:
        changeset_id: ID returned by generate_logic_action_changeset
        run_build: Run the configured build and targeted test after writing
    """
    res = action_generator.apply_changeset(changeset_id, run_build)
    markdown = res.pop("report_markdown", None)
    body = json.dumps(res, indent=2, default=str)
    return (markdown + "\n\n---\n```json\n" + body + "\n```") if markdown else body


@mcp.tool()
def validate_design_drc(xml_input: str) -> str:
    """
    Run Capital Design Rule Checks (DRC) on a design XML payload or file.
    Validates cavity seals, dangling bundles, multicore path consistency, and splice separation.

    Args:
        xml_input: Path to design XML file or inline XML string
    """
    res = drc_validator.validate_drc(xml_input)
    return json.dumps(res, indent=2)


@mcp.tool()
def inspect_live_clogic_session(target_xml_or_session: str = None) -> str:
    """
    Inspect the latest CLogic design XML state and changes captured by the background workspace/log poller.
    Reports placed objects, observed add/change/remove events, next-step suggestions, and a QA reproduction checklist.
    Monitoring begins with the MCP server. Configure CLOGIC_SESSION_DIR / CLOGIC_SESSION_XML and
    CLOGIC_LOG_PATH / CMANAGER_LOG_PATH if the local installation uses different paths. DRC output is a
    CopilotLens heuristic preflight, not a native Capital DRC execution.

    Args:
        target_xml_or_session: Optional XML path or inline XML for one-off analysis; omit it for polled live state.
    """
    res = clogic_session_analyzer.inspect_live_session(target_xml_or_session)
    return json.dumps(res, indent=2)


@mcp.tool()
def generate_copilot_instructions() -> str:
    """
    Analyze the codebase and generate a .github/copilot-instructions.md file.
    This file tells GitHub Copilot about:
    - High-risk files to approach carefully
    - Key architectural patterns observed
    - Modules that need extra tests
    - Dead code safe for removal
    Returns the generated markdown content and writes it to the repo.
    """
    health = health_scorer.get_summary()
    hotspots = git_analyzer.get_hotspots(5)
    dead = dead_code_detector.find_dead_code()
    graph = dep_analyzer.build_graph()
    
    worst = [f["path"] for f in health.get("worst_files", [])[:5]]
    hotspot_paths = [h["path"] for h in hotspots[:5]]
    high_dead = [d["symbol"] for d in dead if d["confidence"] == "HIGH"][:5]
    hubs = [n["id"] for n in graph["nodes"] if n.get("is_hub")][:3]
    circular = graph.get("circular_dependencies", [])
    
    avg_score = health.get("avg_score", 0)
    grade = health.get("grade", "?")
    
    instructions = f"""# GitHub Copilot Instructions — CopilotLens Analysis

*Auto-generated by CopilotLens on this repository.*

## Overall Codebase Health: {avg_score}/100 (Grade: {grade})

## ⚠️ High-Risk Files — Approach with Extra Care
These files have the highest change frequency and defect risk. **Always add/verify tests before modifying**:
{chr(10).join(f"- `{p}`" for p in hotspot_paths) if hotspot_paths else "- None detected"}

## 🏥 Lowest Health Files — Needs Refactoring Attention  
{chr(10).join(f"- `{p}`" for p in worst) if worst else "- None detected"}

## 🔗 Hub Files — High Blast Radius
Changes to these files affect many others:
{chr(10).join(f"- `{p}`" for p in hubs) if hubs else "- None detected"}

## 🔄 Circular Dependencies
{f"⚠️ {len(circular)} circular dependency chain(s) exist. Avoid deepening these patterns." if circular else "✅ No circular dependencies detected."}

## 🧹 Dead Code Candidates (Safe to Remove)
{chr(10).join(f"- `{s}`" for s in high_dead) if high_dead else "- None detected with high confidence"}

## 📋 Coding Guidelines for this Codebase
- Run tests after any change to high-risk files listed above
- Prefer small, focused functions (< 50 lines)
- Add docstrings to any public functions in hub files
- Do not introduce new circular dependencies
- Check module ownership before proposing architecture changes

## 🛠️ CopilotLens MCP Tools Available
Use these tools in Agent mode for deeper analysis:
- `get_file_health(path)` — score any file before editing
- `get_hotspots()` — see the riskiest files
- `get_dependency_graph()` — understand blast radius
- `get_dead_code()` — find safe cleanup opportunities
"""
    
    # Write to .github/copilot-instructions.md
    output_path = Path(REPO_PATH) / ".github" / "copilot-instructions.md"
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(instructions, encoding="utf-8")
        write_status = f"✅ Written to: {output_path}"
    except Exception as e:
        write_status = f"⚠️ Could not write file: {e}"
    
    return json.dumps({
        "content": instructions,
        "write_status": write_status,
        "path": str(output_path)
    }, indent=2)


@mcp.tool()
def get_dashboard_url() -> str:
    """
    Get the URL to the CopilotLens visual dashboard.
    The dashboard shows codebase health, hotspots heatmap, and dependency graphs in a browser.
    """
    return json.dumps({
        "dashboard_url": f"http://localhost:{DASHBOARD_PORT}",
        "status": "Open this URL in your browser to see the visual dashboard"
    })


@mcp.tool()
def get_coverity_findings(file_path: Optional[str] = None, severity: Optional[str] = None) -> str:
    """
    Get Coverity static analysis scan findings and rule violations.
    Returns defect CIDs, failing rule names, line numbers, descriptions, and Copilot remediation advice.
    
    Args:
        file_path: Optional file path filter (e.g. 'src/main/App.java')
        severity: Optional severity filter ('High', 'Medium', 'Low')
    """
    findings = coverity_analyzer.get_findings(file_path=file_path, severity=severity)
    return json.dumps({
        "total": len(findings),
        "file_path_filter": file_path,
        "severity_filter": severity,
        "json_storage_file": str(coverity_analyzer.json_path),
        "findings": findings
    }, indent=2)


@mcp.tool()
def get_coverity_summary() -> str:
    """
    Get overall Coverity Scan security and rule compliance summary.
    Returns total defect counts, rule compliance score (0-100%), breakdown by severity and checker,
    and affected files count.
    """
    summary = coverity_analyzer.get_summary()
    return json.dumps(summary, indent=2)


@mcp.tool()
def import_coverity_json(json_content_or_path: str) -> str:
    """
    Import Coverity Scan results from a JSON file path or raw JSON string.
    Stores normalized findings in coverity_findings.json and updates dashboard metrics.
    
    Args:
        json_content_or_path: File path to Coverity CLI JSON export (cov-format-errors --json-output-v8) or raw JSON string.
    """
    result = coverity_analyzer.load_coverity_json(json_content_or_path)
    return json.dumps(result, indent=2)


@mcp.tool()
def run_coverity_scan() -> str:
    """
    Run/simulate Coverity scan rule checks on the workspace repository, save findings to coverity_findings.json, and return summary.
    """
    summary = coverity_analyzer.run_scan()
    return json.dumps({
        "status": "SUCCESS",
        "message": "Coverity rule scan completed and saved to coverity_findings.json",
        "summary": summary
    }, indent=2)



# ─── Copilot Interaction Learning & Policy MCP Tools ──────────────────────────

@mcp.tool()
def remember_rule(
    rule: str,
    preferred_approach: str = "",
    scope: str = "project",
    rationale: str = "",
    auto_approve: bool = False
) -> str:
    """
    Explicitly save a developer rule, correction, or project convention to the local policy repository.

    Use this when a developer says things like:
    - "Remember this rule: Do not update server.py directly"
    - "Always use async/await in this project"
    - "Never modify the generated files under /dist"

    The rule is stored with PENDING status by default (requires developer approval via review_policy_rule),
    unless auto_approve=True is set, in which case it is immediately added to copilot-instructions.md.

    Args:
        rule: The rule or convention text to remember (e.g. "Do not edit auto-generated files")
        preferred_approach: The recommended alternative or approach (optional)
        scope: Scope of the rule — a file path, module name, language, or 'project' (default: 'project')
        rationale: Why this rule exists (optional but recommended)
        auto_approve: If True, immediately approve and sync to copilot-instructions.md (default: False)
    """
    status = "APPROVED" if auto_approve else "PENDING"
    new_rule = policy_repo.add_rule(
        rule=rule,
        preferred_approach=preferred_approach or rule,
        scope=scope,
        rationale=rationale or "Explicitly submitted by developer",
        source_interaction="Copilot Agent / remember_rule command",
        confidence_level="HIGH",
        status=status
    )
    sync_msg = ""
    if auto_approve:
        sync_msg = policy_repo.sync_to_copilot_instructions()

    return json.dumps({
        "status": "SUCCESS",
        "rule": new_rule,
        "message": (
            f"✅ Rule saved and APPROVED. {sync_msg}"
            if auto_approve else
            f"📋 Rule saved as PENDING. Use review_policy_rule(rule_id='{new_rule['id']}', action='approve') to activate it."
        )
    }, indent=2)


@mcp.tool()
def analyze_copilot_interaction(
    interaction_text: str,
    auto_approve_high_confidence: bool = False
) -> str:
    """
    Analyze a Copilot chat interaction or developer correction and automatically extract
    project rules, conventions, and engineering practices.

    This tool identifies patterns like:
    - Negative directives: "Do not...", "Don't...", "Never...", "Avoid..."
    - Positive conventions: "Always use...", "Prefer...", "Must use..."
    - Explicit rules: "Remember this rule: ...", "Rule: ..."

    For each extracted rule it determines: rule text, preferred approach, scope,
    rationale, and confidence level (HIGH/MEDIUM/LOW).

    Extracted rules are stored as PENDING by default and must be reviewed by the developer
    using review_policy_rule() unless auto_approve_high_confidence=True.

    Args:
        interaction_text: The raw interaction or developer message to analyze
                          (e.g. "Do not update this file. Always use the factory pattern for services.")
        auto_approve_high_confidence: If True, automatically approve HIGH confidence rules (default: False)
    """
    result = interaction_analyzer.analyze_interaction(
        text=interaction_text,
        auto_approve_high_confidence=auto_approve_high_confidence
    )

    if result["extracted_count"] == 0:
        return json.dumps({
            "status": "NO_RULES_FOUND",
            "message": (
                "No recognizable rules or conventions were detected in the text. "
                "Try using explicit phrasing like 'Do not...', 'Always use...', or 'Remember this rule: ...'. "
                "You can also call remember_rule() directly to save a rule manually."
            ),
            "source_text": interaction_text
        }, indent=2)

    pending = [r for r in result["rules"] if r["status"] == "PENDING"]
    approved = [r for r in result["rules"] if r["status"] == "APPROVED"]

    return json.dumps({
        "status": "SUCCESS",
        "extracted_count": result["extracted_count"],
        "pending_rules": len(pending),
        "auto_approved_rules": len(approved),
        "rules": result["rules"],
        "next_step": (
            f"Review and approve {len(pending)} pending rule(s) using review_policy_rule(rule_id, action='approve'). "
            "Approved rules will be synced to .github/copilot-instructions.md automatically."
            if pending else
            "All rules have been approved and synced to .github/copilot-instructions.md."
        )
    }, indent=2)


@mcp.tool()
def get_project_rules(status: str = "all", scope: str = "") -> str:
    """
    Retrieve all stored project rules and conventions from the local policy repository.

    This is the primary tool Copilot should call at the start of any task to load
    project-specific guidance, restrictions, and approved conventions before writing code.

    Always call this before starting a significant coding task to respect team conventions.

    Args:
        status: Filter by rule status — 'all', 'APPROVED', 'PENDING', or 'REJECTED' (default: 'all')
        scope: Optional scope filter — file path, module name, or language (e.g. 'python', 'server.py')
               Leave empty to get all scopes including project-wide rules.
    """
    rules = policy_repo.list_rules(status_filter=status, scope_filter=scope)
    approved = [r for r in rules if r.get("status") == "APPROVED"]
    pending = [r for r in rules if r.get("status") == "PENDING"]
    rejected = [r for r in rules if r.get("status") == "REJECTED"]

    if not rules:
        return json.dumps({
            "status": "EMPTY",
            "message": (
                "No project rules stored yet. "
                "Use analyze_copilot_interaction() to extract rules from interactions, "
                "or remember_rule() to add rules explicitly."
            ),
            "rules": []
        }, indent=2)

    context_lines = []
    for r in approved:
        line = f"[{r['scope']}] {r['rule']}"
        if r.get("preferred_approach") and r["preferred_approach"] != r["rule"]:
            line += f" → Preferred: {r['preferred_approach']}"
        context_lines.append(line)

    return json.dumps({
        "status": "SUCCESS",
        "total": len(rules),
        "approved": len(approved),
        "pending_review": len(pending),
        "rejected": len(rejected),
        "scope_filter": scope or "all",
        "rules": rules,
        "copilot_context_summary": (
            "📜 Active project rules Copilot must follow:\n" + "\n".join(f"  • {l}" for l in context_lines)
            if context_lines else
            "No approved rules yet. Pending rules need developer approval via review_policy_rule()."
        )
    }, indent=2)


@mcp.tool()
def review_policy_rule(
    rule_id: str,
    action: str,
    preferred_approach: str = "",
    scope: str = ""
) -> str:
    """
    Review, approve, reject, edit, or delete a pending rule in the policy repository.

    Developers must approve rules before they become active Copilot guidance.
    Approved rules are automatically synced to .github/copilot-instructions.md.

    Args:
        rule_id: The rule ID to act on (from get_project_rules() or analyze_copilot_interaction())
        action: One of 'approve', 'reject', 'edit', or 'delete'
                - 'approve': Activates the rule and syncs to copilot-instructions.md
                - 'reject': Marks rule as rejected (kept for audit trail)
                - 'edit': Updates the preferred_approach and/or scope
                - 'delete': Permanently removes the rule
        preferred_approach: New preferred approach text (only used with action='edit')
        scope: New scope override (only used with action='edit')
    """
    valid_actions = ("approve", "reject", "edit", "delete")
    if action.lower() not in valid_actions:
        return json.dumps({
            "status": "ERROR",
            "message": f"Invalid action '{action}'. Must be one of: {', '.join(valid_actions)}"
        }, indent=2)

    result = policy_repo.update_rule_status(
        rule_id=rule_id,
        action=action,
        preferred_approach=preferred_approach,
        scope=scope
    )

    if "error" in result:
        return json.dumps({"status": "ERROR", "message": result["error"]}, indent=2)

    action_messages = {
        "approve": "✅ Rule APPROVED and synced to .github/copilot-instructions.md. Copilot will now follow this rule.",
        "reject": "❌ Rule REJECTED. It will not be applied to Copilot guidance.",
        "edit": "✏️ Rule UPDATED. Re-approve with action='approve' if you want changes to take effect.",
        "delete": "🗑️ Rule DELETED permanently from the policy repository."
    }

    return json.dumps({
        "status": "SUCCESS",
        "action": action.upper(),
        "rule": result,
        "message": action_messages.get(action.lower(), "Action completed.")
    }, indent=2)


@mcp.tool()
def get_copilot_context(file_path: str = "", task_description: str = "") -> str:
    """
    Get all relevant approved project rules and contextual guidance Copilot should follow
    for a specific file or task. Call this at the start of any coding task.

    This combines:
    - All project-wide approved rules
    - File/module-specific rules matching the given file_path
    - Language-specific rules detected from the file extension
    - A formatted context block ready to guide Copilot's behavior

    Args:
        file_path: The file Copilot is about to work on (e.g. 'mcp_server/server.py')
                   Used to fetch file-specific and language-specific rules.
        task_description: Brief description of what Copilot is about to do (optional, for logging)
    """
    # Collect project-wide approved rules
    project_rules = policy_repo.get_approved_rules(scope="")

    # Detect language from extension for language-scoped rules
    lang_scope = ""
    if file_path:
        ext_map = {
            ".py": "python", ".js": "javascript", ".ts": "typescript",
            ".jsx": "javascript", ".tsx": "typescript", ".java": "java",
            ".cs": "csharp", ".go": "go", ".rb": "ruby"
        }
        from pathlib import Path as _Path
        ext = _Path(file_path).suffix.lower()
        lang_scope = ext_map.get(ext, "")

    # Collect file-specific rules
    file_rules = []
    lang_rules = []
    seen_ids = set()
    for r in project_rules:
        scope = r.get("scope", "project")
        if file_path and (file_path in scope or scope in file_path):
            if r["id"] not in seen_ids:
                file_rules.append(r)
                seen_ids.add(r["id"])
        elif lang_scope and lang_scope == scope.lower():
            if r["id"] not in seen_ids:
                lang_rules.append(r)
                seen_ids.add(r["id"])

    global_rules = [r for r in project_rules if r["id"] not in seen_ids and r.get("scope") == "project"]

    # Build formatted guidance block
    guidance_lines = ["## 📜 CopilotLens Project Rules — MUST FOLLOW\n"]

    if file_rules:
        guidance_lines.append(f"### File-Specific Rules for `{file_path}`:")
        for r in file_rules:
            guidance_lines.append(f"  🔴 {r['rule']}")
            if r.get("preferred_approach") and r["preferred_approach"] != r["rule"]:
                guidance_lines.append(f"     → Do this instead: {r['preferred_approach']}")

    if lang_rules:
        guidance_lines.append(f"\n### Language Rules ({lang_scope}):")
        for r in lang_rules:
            guidance_lines.append(f"  🟡 {r['rule']}")

    if global_rules:
        guidance_lines.append("\n### Project-Wide Rules:")
        for r in global_rules:
            guidance_lines.append(f"  🟢 {r['rule']}")

    if not (file_rules or lang_rules or global_rules):
        guidance_lines.append("  ℹ️ No approved rules yet. Use remember_rule() or analyze_copilot_interaction() to add rules.")

    total = len(file_rules) + len(lang_rules) + len(global_rules)

    return json.dumps({
        "status": "SUCCESS",
        "file": file_path or "project-wide",
        "task": task_description,
        "total_applicable_rules": total,
        "file_specific_rules": len(file_rules),
        "language_rules": len(lang_rules),
        "project_rules": len(global_rules),
        "copilot_guidance": "\n".join(guidance_lines),
        "rules_detail": {
            "file_specific": file_rules,
            "language": lang_rules,
            "project": global_rules
        }
    }, indent=2)


# ─── Dashboard HTTP Server ─────────────────────────────────────────────────────

_DASHBOARD_CACHE: Dict[str, Any] = {}
_DASHBOARD_LAST_RUN: float = 0.0
_DASHBOARD_LOCK = threading.Lock()
_DASHBOARD_IS_ANALYZING = False


def _refresh_dashboard_data_async():
    """Background worker that computes heavy codebase metrics without blocking HTTP requests."""
    global _DASHBOARD_CACHE, _DASHBOARD_LAST_RUN, _DASHBOARD_IS_ANALYZING
    with _DASHBOARD_LOCK:
        if _DASHBOARD_IS_ANALYZING:
            return
        _DASHBOARD_IS_ANALYZING = True

    def _worker():
        global _DASHBOARD_CACHE, _DASHBOARD_LAST_RUN, _DASHBOARD_IS_ANALYZING
        try:
            health = health_scorer.get_summary()
        except Exception:
            health = {"avg_score": 0, "distribution": {}, "worst_files": [], "best_files": []}

        try:
            hotspots = git_analyzer.get_hotspots(15)
        except Exception:
            hotspots = []

        try:
            dead = ast_dead_code_detector.find_dead_code(limit_files=500)
        except Exception:
            dead = []

        try:
            graph = dep_analyzer.build_graph()
        except Exception:
            graph = {"nodes": [], "edges": [], "circular_dependencies": [], "orphan_files": []}

        try:
            repo_summary = git_analyzer.get_repo_summary()
        except Exception:
            repo_summary = {}

        try:
            rules = policy_repo.list_rules()
        except Exception:
            rules = []

        try:
            kg = knowledge_graph.build_graph()
        except Exception:
            kg = {"nodes": [], "edges": [], "node_count": 0, "edge_count": 0}

        try:
            test_recs = smart_test_analyzer.recommend_tests(["mcp_server/server.py"])
        except Exception:
            test_recs = {"minimal_test_set": []}

        try:
            coverity_summary = coverity_analyzer.get_summary()
        except Exception:
            coverity_summary = {"total_defects": 0, "rule_compliance_score": 100, "by_severity": {}, "by_checker": {}, "affected_files_count": 0, "findings": []}

        try:
            module_owners = git_analyzer.get_module_owners()
        except Exception:
            module_owners = []

        try:
            co_changes = git_analyzer.get_co_change_pairs()
        except Exception:
            co_changes = []

        try:
            blast_data = []
            target_sample = []
            for pair in co_changes[:3]:
                target_sample.append(pair["file_a"])
            for h in hotspots[:3]:
                if h.get("path") and h["path"] not in target_sample:
                    target_sample.append(h["path"])
            for target_path in target_sample[:5]:
                blast_data.append(blast_analyzer.calculate_blast_radius(target_path))
        except Exception:
            blast_data = []

        with _DASHBOARD_LOCK:
            _DASHBOARD_CACHE = {
                "status": "ready",
                "repo_path": REPO_PATH,
                "health": health,
                "hotspots": hotspots,
                "dead_code": dead,
                "policy_rules": rules,
                "knowledge_graph": kg,
                "test_recommendations": test_recs,
                "coverity": coverity_summary,
                "module_owners": module_owners,
                "co_change_pairs": co_changes,
                "blast_radius": blast_data,
                "dependency_graph": {
                    "nodes": graph["nodes"],
                    "edges": graph["edges"],
                    "circular": graph.get("circular_dependencies", []),
                    "orphans": graph.get("orphan_files", [])
                },
                "repo_summary": repo_summary
            }
            _DASHBOARD_LAST_RUN = time.time()
            _DASHBOARD_IS_ANALYZING = False

    t = threading.Thread(target=_worker, daemon=True)
    t.start()


def get_dashboard_data() -> dict:
    """Collect all analysis data for the dashboard with non-blocking cache return."""
    global _DASHBOARD_CACHE, _DASHBOARD_LAST_RUN
    now = time.time()
    
    # If cache is valid (within 120s), return it immediately
    if _DASHBOARD_CACHE and (now - _DASHBOARD_LAST_RUN < 120):
        return _DASHBOARD_CACHE

    # Trigger background analysis if cache is empty or stale
    _refresh_dashboard_data_async()

    # If cache exists (even slightly stale), return it while refreshing
    if _DASHBOARD_CACHE:
        return _DASHBOARD_CACHE

    # First load placeholder so the browser gets an immediate HTTP 200 response
    return {
        "status": "loading",
        "repo_path": REPO_PATH,
        "health": {"avg_score": 0, "distribution": {}, "worst_files": [], "best_files": []},
        "hotspots": [],
        "dead_code": [],
        "policy_rules": [],
        "knowledge_graph": {"nodes": [], "edges": [], "node_count": 0, "edge_count": 0},
        "test_recommendations": {"minimal_test_set": []},
        "coverity": {"total_defects": 0, "rule_compliance_score": 100, "by_severity": {}, "by_checker": {}, "affected_files_count": 0, "findings": []},
        "module_owners": [],
        "co_change_pairs": [],
        "blast_radius": [],
        "dependency_graph": {"nodes": [], "edges": [], "circular": [], "orphans": []},
        "repo_summary": {}
    }



class DashboardHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # Suppress default HTTP logs

    def do_POST(self):
        length = int(self.headers.get('Content-Length', 0))
        body_data = self.rfile.read(length).decode('utf-8') if length > 0 else "{}"
        try:
            req_json = json.loads(body_data) if body_data else {}
        except Exception:
            req_json = {}

        if self.path == "/api/sync-instructions":
            result = generate_copilot_instructions()
            self._send_json(200, json.loads(result) if isinstance(result, str) else result)
        elif self.path == "/api/remember-rule":
            rule_text = req_json.get("rule", "")
            approach = req_json.get("preferred_approach", "")
            scope = req_json.get("scope", "project")
            rationale = req_json.get("rationale", "")
            res = policy_repo.add_rule(
                rule=rule_text,
                preferred_approach=approach or rule_text,
                scope=scope,
                rationale=rationale,
                source_interaction="Dashboard UI",
                confidence_level="HIGH",
                status="APPROVED"
            )
            self._send_json(200, {"status": "SUCCESS", "rule": res})
        elif self.path == "/api/manage-rule":
            rule_id = req_json.get("rule_id", "")
            action = req_json.get("action", "")
            res = policy_repo.update_rule_status(rule_id=rule_id, action=action)
            self._send_json(200, res)
        elif self.path == "/api/run-tests":
            res = smart_test_analyzer.run_recommended_tests()
            self._send_json(200, res)
        elif self.path == "/api/coverity/import":
            json_input = req_json.get("json_content", req_json.get("json_path", ""))
            res = coverity_analyzer.load_coverity_json(json_input)
            self._send_json(200, res)
        elif self.path == "/api/coverity/scan":
            res = coverity_analyzer.run_scan()
            self._send_json(200, {"status": "SUCCESS", "summary": res})
        else:
            self._send_text(404, "Not found")

    def _send_json(self, code: int, data: Any):
        body = json.dumps(data).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        next_out_dir = Path(__file__).parent.parent / "dashboard-next" / "out"
        dashboard_dir = next_out_dir if next_out_dir.exists() else (Path(__file__).parent.parent / "dashboard")

        if self.path.startswith("/api/neo4j"):
            from urllib.parse import urlparse, parse_qs
            parsed = urlparse(self.path)
            qs = parse_qs(parsed.query)
            action = qs.get("action", ["find_by_name"])[0]
            args_raw = qs.get("args", ["{}"])[0]
            try:
                args = json.loads(args_raw)
            except Exception:
                args = {}
            result = neo4j_analyzer._run(action, args)
            self._send_json(200, result)
        elif self.path == "/api/data":
            data = get_dashboard_data()
            body = json.dumps(data).encode("utf-8")
            try:
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Content-Length", len(body))
                self.end_headers()
                self.wfile.write(body)
            except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
                pass
        elif self.path == "/api/sync-instructions":
            result = generate_copilot_instructions()
            body = result.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", len(body))
            self.end_headers()
            self.wfile.write(body)
        else:
            rel_path = self.path.lstrip("/")
            if not rel_path or rel_path == "index.html":
                file_path = dashboard_dir / "index.html"
            else:
                file_path = dashboard_dir / rel_path

            if file_path.exists() and file_path.is_file():
                content_type = "text/html; charset=utf-8"
                if file_path.suffix == ".css":
                    content_type = "text/css"
                elif file_path.suffix == ".js":
                    content_type = "application/javascript"
                elif file_path.suffix == ".json":
                    content_type = "application/json"
                elif file_path.suffix == ".svg":
                    content_type = "image/svg+xml"

                body = file_path.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", content_type)
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Content-Length", len(body))
                self.end_headers()
                self.wfile.write(body)
            else:
                self._send_text(404, "Not found")

    def _send_text(self, code, msg):
        body = msg.encode()
        self.send_response(code)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)


def start_dashboard():
    """Start the dashboard HTTP server in a background thread."""
    try:
        from http.server import ThreadingHTTPServer
        ServerClass = ThreadingHTTPServer
    except Exception:
        ServerClass = HTTPServer

    try:
        server = ServerClass(("0.0.0.0", DASHBOARD_PORT), DashboardHandler)
        print(f"[CopilotLens] Dashboard: http://localhost:{DASHBOARD_PORT}", file=sys.stderr, flush=True)
        server.serve_forever()
    except OSError as e:
        print(f"[CopilotLens] Dashboard could not start on port {DASHBOARD_PORT}: {e}", file=sys.stderr, flush=True)


# ─── Helpers ───────────────────────────────────────────────────────────────────

def _interpret_summary(health: dict) -> str:
    avg = health.get("avg_score", 0)
    dist = health.get("distribution", {})
    critical = dist.get("critical", 0)
    total = health.get("total_files", 0)
    
    if avg >= 80:
        return f"✅ Codebase is in excellent health ({avg}/100). {critical} critical files need attention."
    elif avg >= 65:
        return f"👍 Codebase health is good ({avg}/100). Focus on the {critical} critical files."
    elif avg >= 50:
        return f"⚠️ Codebase health is fair ({avg}/100). {critical}/{total} files are in critical state."
    else:
        return f"🚨 Codebase health is poor ({avg}/100). Major refactoring recommended. {critical}/{total} files critical."


# ─── Neo4j Code Graph Tools ────────────────────────────────────────────────────

@mcp.tool()
def neo4j_find_class(name: str, node_type: str = "any", max_results: int = 10) -> str:
    """
    Search the Neo4j Capital code graph for a class, interface, or test class by name.
    Always start here before running any graph traversal.

    Args:
        name: Partial or full class name to search for.
        node_type: Filter by 'Class', 'Interface', 'TestClass', or 'any' (default).
        max_results: Maximum number of results to return (default 10).
    """
    return json.dumps(neo4j_analyzer.find_by_name(name, node_type, max_results), indent=2)


@mcp.tool()
def neo4j_get_class(class_name: str) -> str:
    """
    Get full details of a Java class node from the Neo4j code graph,
    including its methods, fields, constructors, and annotations.

    Args:
        class_name: Simple name, fullName, or filePath fragment of the class.
    """
    return json.dumps(neo4j_analyzer.get_class_full(class_name), indent=2)


@mcp.tool()
def neo4j_get_interface(interface_name: str) -> str:
    """
    Get full details of a Java interface node from the Neo4j code graph,
    including its method signatures.

    Args:
        interface_name: Simple name, fullName, or filePath fragment of the interface.
    """
    return json.dumps(neo4j_analyzer.get_interface_full(interface_name), indent=2)


@mcp.tool()
def neo4j_get_class_methods(class_name: str, include_private: bool = False, limit: int = 50) -> str:
    """
    List all method signatures of a Java class or interface from the code graph.
    Use this to find coverage gaps or locate specific behaviour.

    Args:
        class_name: Target class name.
        include_private: Include private methods (default False).
        limit: Max number of methods to return (default 50).
    """
    return json.dumps(neo4j_analyzer.get_class_methods(class_name, include_private, limit), indent=2)


@mcp.tool()
def neo4j_get_test_class(class_name: str) -> str:
    """
    Resolve a TestClass node from the code graph and list its test methods.
    Works with both the test class name and the production class name.

    Args:
        class_name: Test class name or production class name.
    """
    return json.dumps(neo4j_analyzer.get_test_class(class_name), indent=2)


@mcp.tool()
def neo4j_find_by_filepath(file_path: str, max_results: int = 10) -> str:
    """
    Find Class, Interface, or TestClass nodes in the code graph by file path fragment.

    Args:
        file_path: Case-insensitive file path substring (e.g. 'harness/assembly').
        max_results: Maximum number of results (default 10).
    """
    return json.dumps(neo4j_analyzer.find_by_filepath(file_path, max_results), indent=2)


@mcp.tool()
def neo4j_expand_out(class_name: str, depth: int = 1) -> str:
    """
    Outbound graph traversal — find all classes and interfaces that the target class
    depends on (i.e. what it uses or references). Returns filePath for each node.

    Args:
        class_name: Starting class name.
        depth: Traversal depth (default 1, max recommended 3).
    """
    return json.dumps(neo4j_analyzer.expand_class_out(class_name, depth), indent=2)


@mcp.tool()
def neo4j_expand_in(class_name: str, depth: int = 1) -> str:
    """
    Inbound graph traversal — find all classes that depend on (call or import)
    the target class. Returns filePath for each node.

    Args:
        class_name: Starting class name.
        depth: Traversal depth (default 1, max recommended 3).
    """
    return json.dumps(neo4j_analyzer.expand_class_in(class_name, depth), indent=2)


@mcp.tool()
def neo4j_expand_both(class_name: str, depth: int = 1) -> str:
    """
    Bidirectional graph traversal — get the full dependency neighbourhood of a class.
    Combines inbound and outbound in one call. Returns filePath for each node.
    Use the result as seeds for neo4j_graph_intelligence() to rank by importance.

    Args:
        class_name: Starting class name.
        depth: Traversal depth (default 1, max recommended 3).
    """
    return json.dumps(neo4j_analyzer.expand_both(class_name, depth), indent=2)


@mcp.tool()
def neo4j_get_class_hierarchy(class_name: str) -> str:
    """
    Get the full inheritance and interface implementation chain for a Java class.

    Args:
        class_name: Target class name.
    """
    return json.dumps(neo4j_analyzer.get_class_hierarchy(class_name), indent=2)


@mcp.tool()
def neo4j_get_related_tests(class_name: str, max_results: int = 10) -> str:
    """
    Find TestClass nodes related to a production class by name or path match.

    Args:
        class_name: Production class name.
        max_results: Maximum number of test classes to return (default 10).
    """
    return json.dumps(neo4j_analyzer.get_related_test_classes(class_name, max_results), indent=2)


@mcp.tool()
def neo4j_expand_test_out(class_name: str, depth: int = 1) -> str:
    """
    Outbound traversal of TestClass nodes — find base test classes and shared fixtures.

    Args:
        class_name: Test class name.
        depth: Traversal depth (default 1).
    """
    return json.dumps(neo4j_analyzer.expand_test_class_out(class_name, depth), indent=2)


@mcp.tool()
def neo4j_expand_test_in(class_name: str, depth: int = 1) -> str:
    """
    Inbound traversal of TestClass nodes — find subclass test nodes.

    Args:
        class_name: Test class name.
        depth: Traversal depth (default 1).
    """
    return json.dumps(neo4j_analyzer.expand_test_class_in(class_name, depth), indent=2)


@mcp.tool()
def neo4j_expand_test_both(class_name: str, depth: int = 1) -> str:
    """
    Bidirectional traversal of TestClass nodes — full test neighbourhood.

    Args:
        class_name: Test class name.
        depth: Traversal depth (default 1).
    """
    return json.dumps(neo4j_analyzer.expand_test_class_both(class_name, depth), indent=2)


@mcp.tool()
def neo4j_get_uncovered_methods(class_name: str) -> str:
    """
    Find public and protected methods of a class that have no test coverage.
    Use this before writing new tests to identify gaps.

    Args:
        class_name: Target class name.
    """
    return json.dumps(neo4j_analyzer.get_uncovered_methods(class_name), indent=2)


@mcp.tool()
def neo4j_get_test_infrastructure(package_name: str) -> str:
    """
    Find base and abstract test classes with setup methods in a Java package.
    Use this to find test patterns and infrastructure to reference.

    Args:
        package_name: Java package name (e.g. 'com.example.harness').
    """
    return json.dumps(neo4j_analyzer.get_test_infrastructure(package_name), indent=2)


@mcp.tool()
def neo4j_find_similar_tested_classes(class_name: str) -> str:
    """
    Find sibling classes in the same package that already have tests.
    Useful for finding test patterns to reference when writing new tests.

    Args:
        class_name: Target class name.
    """
    return json.dumps(neo4j_analyzer.find_similar_tested_classes(class_name), indent=2)


@mcp.tool()
def neo4j_get_package_coverage(package_name: str) -> str:
    """
    Get test coverage status for every class in a Java package.

    Args:
        package_name: Java package name (e.g. 'com.example.harness').
    """
    return json.dumps(neo4j_analyzer.get_package_test_coverage(package_name), indent=2)


@mcp.tool()
def neo4j_graph_intelligence(class_names: str) -> str:
    """
    Rank a list of classes by combined PageRank + betweenness centrality score.
    Use this AFTER traversal (neo4j_expand_both) to identify the most architecturally
    important files to pass to Copilot as context.

    Args:
        class_names: Comma-separated list of class names to rank
                     (e.g. 'HarnessAssembly,WireHarness,IHarnessProvider').
    """
    names = [n.strip() for n in class_names.split(",") if n.strip()]
    return json.dumps(neo4j_analyzer.run_graph_intelligence(names), indent=2)


@mcp.tool()
def neo4j_pagerank(class_names: str) -> str:
    """
    Rank a list of classes by PageRank score [0-10].
    Measures architectural influence (how many classes reference each node).

    Args:
        class_names: Comma-separated list of class names to rank.
    """
    names = [n.strip() for n in class_names.split(",") if n.strip()]
    return json.dumps(neo4j_analyzer.run_pagerank(names), indent=2)


@mcp.tool()
def neo4j_betweenness(class_names: str) -> str:
    """
    Rank a list of classes by betweenness centrality score [0-10].
    Measures structural centrality (how many paths pass through each node).

    Args:
        class_names: Comma-separated list of class names to rank.
    """
    names = [n.strip() for n in class_names.split(",") if n.strip()]
    return json.dumps(neo4j_analyzer.run_betweenness(names), indent=2)


@mcp.tool()
def neo4j_run_cypher(query: str, params_json: str = "{}") -> str:
    """
    Run any parameterized Cypher query directly against the Neo4j code graph.
    Use for custom lookups not covered by other tools.

    Args:
        query: Parameterized Cypher query string.
        params_json: JSON string of query parameters (default '{}').
    """
    try:
        params = json.loads(params_json)
    except json.JSONDecodeError:
        params = {}
    return json.dumps(neo4j_analyzer.run_cypher(query, params), indent=2)


@mcp.tool()
def neo4j_filter_by_field(field_type: str) -> str:
    """
    Find all classes in the code graph that have a field of a given type.

    Args:
        field_type: Java field type name (e.g. 'HarnessProvider').
    """
    return json.dumps(neo4j_analyzer.dynamic_field_filter(field_type), indent=2)


@mcp.tool()
def neo4j_filter_by_annotation(annotation_type: str) -> str:
    """
    Find all classes in the code graph carrying a specific Java annotation.

    Args:
        annotation_type: Annotation name (e.g. 'SpringBootTest', 'Service').
    """
    return json.dumps(neo4j_analyzer.dynamic_annotation_filter(annotation_type), indent=2)


@mcp.tool()
def neo4j_search_methods(
    method_name: str = "",
    return_type: str = "",
    signature_fragment: str = "",
) -> str:
    """
    Find methods in the code graph by name, return type, or signature fragment.
    At least one argument must be provided.

    Args:
        method_name: Partial method name to match.
        return_type: Return type to filter by (e.g. 'List', 'void').
        signature_fragment: Fragment of the full method signature.
    """
    return json.dumps(
        neo4j_analyzer.dynamic_method_signature_search(
            method_name=method_name or None,
            return_type=return_type or None,
            signature_fragment=signature_fragment or None,
        ),
        indent=2,
    )


@mcp.tool()
def neo4j_lookup_enum(enum_name: str) -> str:
    """
    Resolve an Enum node from the code graph and return all its constants.

    Args:
        enum_name: Enum class name.
    """
    return json.dumps(neo4j_analyzer.dynamic_enum_lookup(enum_name), indent=2)


@mcp.tool()
def neo4j_lookup_nested_classes(parent_class_name: str) -> str:
    """
    Find all inner or nested classes of a parent Java class in the code graph.

    Args:
        parent_class_name: Parent class name.
    """
    return json.dumps(neo4j_analyzer.dynamic_nested_class_lookup(parent_class_name), indent=2)


# ─── PSI Tools (IntelliJ Native Semantic Engine) ───────────────────────────────

@mcp.tool()
def psi_health_check() -> str:
    """
    Check the connectivity and status of the IntelliJ PSI Tools plugin server (port 3000/3001)
    or CLI runner. Verifies whether IntelliJ IDEA is actively serving semantic PSI actions.
    """
    return json.dumps(psi_analyzer.health(), indent=2)


@mcp.tool()
def psi_get_class_structure(class_name: str) -> str:
    """
    Inspect the full structure of a Java class using IntelliJ PSI:
    fields, methods, constructors, inner classes, superclasses, and interfaces.

    Args:
        class_name: Fully qualified or simple class name (e.g. 'com.mentor.capital.Rule' or 'Rule').
    """
    return json.dumps(psi_analyzer.get_class_structure(class_name), indent=2)


@mcp.tool()
def psi_get_method_body(method: str) -> str:
    """
    Extract the source code body and signature of a specific method using IntelliJ PSI.

    Args:
        method: Qualified method reference, e.g. 'ClassName#methodName' or 'com.pkg.ClassName#methodName'.
    """
    return json.dumps(psi_analyzer.get_method_body(method), indent=2)


@mcp.tool()
def psi_find_usages(symbol: str, scope: str = "project", include_hierarchy: bool = True) -> str:
    """
    Find all references / usages of a Java class, method, or field across the project using IntelliJ PSI.

    Args:
        symbol: Symbol identifier or qualified name to search usages for.
        scope: Search scope ('project', 'module', or 'all'). Default is 'project'.
        include_hierarchy: Whether to include usages in sub/super types. Default is True.
    """
    return json.dumps(psi_analyzer.find_usages(symbol, scope=scope, include_hierarchy=include_hierarchy), indent=2)


@mcp.tool()
def psi_get_call_graph(method: str, direction: str = "both", depth: int = 2, max_nodes: int = 50) -> str:
    """
    Traverse callers and/or callees of a method to produce a semantic call graph using IntelliJ PSI.

    Args:
        method: Method reference, e.g. 'ClassName#methodName'.
        direction: 'incoming' (callers), 'outgoing' (callees), or 'both'.
        depth: Traversal depth (default: 2, max recommended: 4).
        max_nodes: Maximum nodes to return (default: 50).
    """
    return json.dumps(psi_analyzer.get_call_graph(method, direction=direction, depth=depth, max_nodes=max_nodes), indent=2)


@mcp.tool()
def psi_explore_class_dependencies(
    class_name: str,
    direction: str = "both",
    depth: int = 2,
    include_jdk: bool = False,
    include_libraries: bool = False,
    max_classes: int = 50,
) -> str:
    """
    Explore incoming and outgoing dependencies of a Java class via IntelliJ PSI.
    Alternative to Neo4j class dependency graphs with real-time PSI fidelity.

    Args:
        class_name: Class name to explore.
        direction: 'incoming' (dependents), 'outgoing' (dependencies), or 'both'.
        depth: Dependency search depth (default: 2).
        include_jdk: Include java.* / javax.* classes. Default is False.
        include_libraries: Include external third-party library classes. Default is False.
        max_classes: Maximum classes in graph. Default is 50.
    """
    return json.dumps(
        psi_analyzer.explore_class_dependencies(
            class_name=class_name,
            direction=direction,
            depth=depth,
            include_jdk=include_jdk,
            include_libraries=include_libraries,
            max_classes=max_classes,
        ),
        indent=2,
    )


@mcp.tool()
def psi_get_type_hierarchy(class_name: str, direction: str = "both") -> str:
    """
    Get the complete type inheritance hierarchy (subclasses, superclasses, implemented interfaces)
    for a Java class or interface using IntelliJ PSI.

    Args:
        class_name: Class or interface name.
        direction: 'subtypes', 'supertypes', or 'both'. Default is 'both'.
    """
    return json.dumps(psi_analyzer.get_type_hierarchy(class_name, direction=direction), indent=2)


@mcp.tool()
def psi_symbol_search(query: str, kind: str = "all", limit: int = 50) -> str:
    """
    Search symbols (classes, methods, fields) across the indexed IntelliJ project workspace.

    Args:
        query: Name query or pattern to search.
        kind: 'class', 'method', 'field', or 'all'.
        limit: Max results (default: 50).
    """
    return json.dumps(psi_analyzer.symbol_search(query, kind=kind, limit=limit), indent=2)


@mcp.tool()
def psi_get_file_inspections(file_path: str) -> str:
    """
    Run IntelliJ IDEA code inspections and linting checks on a file (routes to inspection server port 3001).

    Args:
        file_path: Absolute or workspace-relative path to the source file.
    """
    return json.dumps(psi_analyzer.get_file_inspections(file_path), indent=2)


# ─── Entry Point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print(f"[CopilotLens] Starting MCP server for repo: {REPO_PATH}", file=sys.stderr, flush=True)
    
    # Start dashboard in background thread
    dashboard_thread = threading.Thread(target=start_dashboard, daemon=True)
    dashboard_thread.start()
    
    # Run MCP server (blocking)
    mcp.run(transport="stdio")
