"""
CopilotLens - Neo4j Code Graph Analyzer
=========================================
Wraps the neo4j_cli.mjs script as a Python subprocess, exposing all 27
Neo4j graph navigation actions as typed Python methods for the MCP server.

The CLI script is located at:
    C:/repos/iesd-26/.github/skills/neo4j-code-graph-navigator/scripts/neo4j_cli.mjs

Connection credentials are loaded from .env in the repo root or via env vars:
    NEO4J_URI       = bolt://10.103.236.11
    NEO4J_USERNAME  = neo4j
    NEO4J_PASSWORD  = <password>
    NEO4J_DATABASE  = neo4j  (optional)
"""

import json
import os
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

# Path to the neo4j_cli.mjs script
NEO4J_CLI_SCRIPT = Path(
    r"C:\repos\iesd-26\.github\skills\neo4j-code-graph-navigator\scripts\neo4j_cli.mjs"
)

# Default Neo4j connection (overridden via env vars or .env file)
_DEFAULT_ENV = {
    "NEO4J_URI": "bolt://10.103.236.11",
    "NEO4J_USERNAME": "neo4j",
    "NEO4J_PASSWORD": "Mentor@1234567",
    "NEO4J_DATABASE": "neo4j",
}


class Neo4jAnalyzer:
    """
    Python wrapper for the neo4j_cli.mjs Node.js CLI.

    All 27 actions are exposed as methods. Each method:
      1. Serialises args to JSON and sets CLI_JSON_ARGS env var.
      2. Spawns `node neo4j_cli.mjs <action>` as a subprocess.
      3. Parses and returns the JSON response.

    On failure returns: {"success": false, "error": "<message>"}
    """

    def __init__(
        self,
        neo4j_uri: Optional[str] = None,
        neo4j_username: Optional[str] = None,
        neo4j_password: Optional[str] = None,
        neo4j_database: Optional[str] = None,
        env_file: Optional[str] = None,
    ):
        self.env_overrides: Dict[str, str] = {}
        if neo4j_uri:
            self.env_overrides["NEO4J_URI"] = neo4j_uri
        if neo4j_username:
            self.env_overrides["NEO4J_USERNAME"] = neo4j_username
        if neo4j_password:
            self.env_overrides["NEO4J_PASSWORD"] = neo4j_password
        if neo4j_database:
            self.env_overrides["NEO4J_DATABASE"] = neo4j_database
        if env_file:
            self.env_overrides["ENV_FILE"] = env_file

    # ── Internal ──────────────────────────────────────────────────────────────

    def _run(self, action: str, args: Dict[str, Any]) -> Dict[str, Any]:
        """Execute an action via neo4j_cli.mjs and return parsed JSON."""
        if not NEO4J_CLI_SCRIPT.exists():
            return {
                "success": False,
                "error": f"neo4j_cli.mjs not found at: {NEO4J_CLI_SCRIPT}. "
                         "Ensure the neo4j-code-graph-navigator skill is installed.",
            }

        env = {**os.environ}
        for k, v in _DEFAULT_ENV.items():
            env.setdefault(k, v)
        env.update(self.env_overrides)
        env["CLI_JSON_ARGS"] = json.dumps(args)

        stdout = ""
        try:
            result = subprocess.run(
                ["node", str(NEO4J_CLI_SCRIPT), action],
                capture_output=True,
                text=True,
                timeout=30,
                env=env,
            )
            stdout = result.stdout.strip()
            if not stdout:
                stderr = result.stderr.strip()
                return {
                    "success": False,
                    "error": f"No output from CLI (exit {result.returncode}). stderr: {stderr}",
                }
            return json.loads(stdout)
        except subprocess.TimeoutExpired:
            return {"success": False, "error": "Neo4j CLI timed out after 30s."}
        except json.JSONDecodeError as e:
            return {"success": False, "error": f"Invalid JSON from CLI: {e}. Raw: {stdout[:300]}"}
        except FileNotFoundError:
            return {
                "success": False,
                "error": "Node.js not found. Ensure Node.js >= 18 is installed and on PATH.",
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ── Group 1: Class Resolution ─────────────────────────────────────────────

    def get_class_full(self, class_name: str) -> Dict[str, Any]:
        """Resolve a Class node with methods, fields, constructors, and annotations."""
        return self._run("get_class_full", {"className": class_name})

    def get_interface_full(self, interface_name: str) -> Dict[str, Any]:
        """Resolve an Interface node with method signatures."""
        return self._run("get_interface_full", {"interfaceName": interface_name})

    def get_class_methods(
        self, class_name: str, include_private: bool = False, limit: int = 50
    ) -> Dict[str, Any]:
        """List method signatures of a Class or Interface."""
        return self._run("get_class_methods", {
            "className": class_name,
            "includePrivate": include_private,
            "limit": limit,
        })

    def get_test_class(self, class_name: str) -> Dict[str, Any]:
        """Resolve a TestClass node and its test methods."""
        return self._run("get_test_class", {"className": class_name})

    def find_by_name(self, name: str, node_type: str = "any", max_results: int = 10) -> Dict[str, Any]:
        """Fuzzy name lookup across all node types. Best starting point."""
        return self._run("find_by_name", {
            "name": name,
            "nodeType": node_type,
            "maxResults": max_results,
        })

    def find_by_filepath(self, file_path: str, max_results: int = 10) -> Dict[str, Any]:
        """Resolve nodes by a filePath fragment (case-insensitive substring)."""
        return self._run("find_by_filepath", {"filePath": file_path, "maxResults": max_results})

    # ── Group 2: Class Node Traversal ─────────────────────────────────────────

    def expand_class_out(self, class_name: str, depth: int = 1) -> Dict[str, Any]:
        """Outbound traversal — what does this class depend on?"""
        return self._run("expand_class_out", {"className": class_name, "depth": depth})

    def expand_class_in(self, class_name: str, depth: int = 1) -> Dict[str, Any]:
        """Inbound traversal — who depends on this class?"""
        return self._run("expand_class_in", {"className": class_name, "depth": depth})

    def expand_both(self, class_name: str, depth: int = 1) -> Dict[str, Any]:
        """Bidirectional traversal — full dependency neighbourhood."""
        return self._run("expand_both", {"className": class_name, "depth": depth})

    def get_related_test_classes(self, class_name: str, max_results: int = 10) -> Dict[str, Any]:
        """Find TestClass nodes related to a production class."""
        return self._run("get_related_test_classes", {
            "className": class_name, "maxResults": max_results
        })

    def get_class_hierarchy(self, class_name: str) -> Dict[str, Any]:
        """Get the full inheritance and implementation chain for a class."""
        return self._run("get_class_hierarchy", {"className": class_name})

    # ── Group 3: TestClass Traversal ──────────────────────────────────────────

    def expand_test_class_out(self, class_name: str, depth: int = 1) -> Dict[str, Any]:
        """Outbound traversal of TestClass nodes — base classes and fixtures."""
        return self._run("expand_test_class_out", {"className": class_name, "depth": depth})

    def expand_test_class_in(self, class_name: str, depth: int = 1) -> Dict[str, Any]:
        """Inbound traversal of TestClass nodes — subclass test nodes."""
        return self._run("expand_test_class_in", {"className": class_name, "depth": depth})

    def expand_test_class_both(self, class_name: str, depth: int = 1) -> Dict[str, Any]:
        """Bidirectional traversal of TestClass nodes — full test neighbourhood."""
        return self._run("expand_test_class_both", {"className": class_name, "depth": depth})

    # ── Group 4: Coverage Analysis ────────────────────────────────────────────

    def get_uncovered_methods(self, class_name: str) -> Dict[str, Any]:
        """Find public/protected methods with no test coverage."""
        return self._run("get_uncovered_methods", {"className": class_name})

    def get_test_infrastructure(self, package_name: str) -> Dict[str, Any]:
        """Find base and abstract test classes with setup methods in a package."""
        return self._run("get_test_infrastructure", {"packageName": package_name})

    def find_similar_tested_classes(self, class_name: str) -> Dict[str, Any]:
        """Find sibling classes in the same package that already have tests."""
        return self._run("find_similar_tested_classes", {"className": class_name})

    def get_package_test_coverage(self, package_name: str) -> Dict[str, Any]:
        """Get coverage status for every class in a Java package."""
        return self._run("get_package_test_coverage", {"packageName": package_name})

    # ── Group 5: Graph Intelligence ───────────────────────────────────────────

    def run_pagerank(self, class_names: List[str]) -> Dict[str, Any]:
        """Rank nodes by PageRank [0-10] — measures architectural influence."""
        return self._run("run_pagerank", {"classNames": class_names})

    def run_betweenness(self, class_names: List[str]) -> Dict[str, Any]:
        """Rank nodes by betweenness centrality [0-10] — measures path centrality."""
        return self._run("run_betweenness", {"classNames": class_names})

    def run_graph_intelligence(self, class_names: List[str]) -> Dict[str, Any]:
        """
        Combined PageRank + betweenness score. Best single action for ranking
        which files are most architecturally important to pass to Copilot.
        """
        return self._run("run_graph_intelligence", {"classNames": class_names})

    # ── Group 6: Dynamic Queries ──────────────────────────────────────────────

    def run_cypher(self, query: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Run any parameterized Cypher query directly against Neo4j."""
        return self._run("run_cypher", {"query": query, "params": params or {}})

    def dynamic_field_filter(self, field_type: str) -> Dict[str, Any]:
        """Find classes that have a field of a given type."""
        return self._run("dynamic_field_filter", {"fieldType": field_type})

    def dynamic_annotation_filter(self, annotation_type: str) -> Dict[str, Any]:
        """Find classes carrying a specific Java annotation."""
        return self._run("dynamic_annotation_filter", {"annotationType": annotation_type})

    def dynamic_method_signature_search(
        self,
        method_name: Optional[str] = None,
        return_type: Optional[str] = None,
        signature_fragment: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Find methods by name, return type, or signature fragment. At least one arg required."""
        args: Dict[str, Any] = {}
        if method_name:
            args["methodName"] = method_name
        if return_type:
            args["returnType"] = return_type
        if signature_fragment:
            args["signatureFragment"] = signature_fragment
        return self._run("dynamic_method_signature_search", args)

    def dynamic_enum_lookup(self, enum_name: str) -> Dict[str, Any]:
        """Resolve an Enum node and all its constants."""
        return self._run("dynamic_enum_lookup", {"enumName": enum_name})

    def dynamic_nested_class_lookup(self, parent_class_name: str) -> Dict[str, Any]:
        """Find inner or nested classes of a parent class."""
        return self._run("dynamic_nested_class_lookup", {"parentClassName": parent_class_name})
