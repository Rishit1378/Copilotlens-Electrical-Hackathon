"""
CopilotLens - PSI Tools Semantic Analyzer
===========================================
Integrates IntelliJ IDEA's Program Structure Interface (PSI) via the
PSI Tools plugin (localhost:3000 / :3001) or CLI runner (`psi_tools_cli.ps1`).

Exposes all semantic Java analysis capabilities:
- Class structure, annotations, imports, method bodies
- Usages, call graphs, class dependencies
- Type hierarchies, subclasses, superclasses, interface implementations
- Method override hierarchies
- Inspections & diagnostics
"""

import json
import os
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional
import urllib.request
import urllib.error

PSI_CLI_SCRIPT = Path(r"C:\repos\iesd-26\.github\skills\psi-tools\scripts\psi_tools_cli.ps1")

# Inspection actions routed to port 3001
INSPECTION_ACTIONS = {"get_file_inspections", "get_changeset_inspections"}


class PsiToolsAnalyzer:
    """
    Python interface to the PSI Tools IntelliJ plugin.
    Supports direct JSON-RPC over HTTP (port 3000/3001) for maximum speed,
    with automatic fallback to `psi_tools_cli.ps1` via PowerShell.
    """

    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        inspection_port: Optional[int] = None,
        timeout: int = 15,
    ):
        self.host = host or os.getenv("PSI_TOOLS_HOST", "localhost")
        self.port = int(port or os.getenv("PSI_TOOLS_PORT", "3000"))
        self.inspection_port = int(inspection_port or os.getenv("PSI_TOOLS_INSPECTION_PORT", "3001"))
        self.timeout = timeout

    def _get_url(self, action: str) -> str:
        port = self.inspection_port if action in INSPECTION_ACTIONS else self.port
        return f"http://{self.host}:{port}/mcp"

    def _run_http(self, action: str, args: Dict[str, Any]) -> Dict[str, Any]:
        """Direct JSON-RPC HTTP call to the PSI Tools plugin."""
        url = self._get_url(action)
        body = json.dumps({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": action,
                "arguments": args
            }
        }).encode("utf-8")

        req = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                resp_data = json.loads(resp.read().decode("utf-8"))
                if resp_data.get("error"):
                    return {"success": False, "error": resp_data["error"].get("message", "Unknown RPC error")}
                
                content = resp_data.get("result", {}).get("content", [])
                if content and isinstance(content, list) and content[0].get("text"):
                    try:
                        parsed = json.loads(content[0]["text"])
                        return {"success": True, "data": parsed}
                    except json.JSONDecodeError:
                        return {"success": True, "data": content[0]["text"]}
                return {"success": True, "data": resp_data.get("result", {})}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _run_cli(self, action: str, args: Dict[str, Any]) -> Dict[str, Any]:
        """Fallback via PowerShell psi_tools_cli.ps1."""
        if not PSI_CLI_SCRIPT.exists():
            return {
                "success": False,
                "error": f"psi_tools_cli.ps1 not found at {PSI_CLI_SCRIPT}. Ensure psi-tools skill is installed.",
            }

        env = {**os.environ}
        env["CLI_JSON_ARGS"] = json.dumps(args)

        try:
            result = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(PSI_CLI_SCRIPT),
                    action,
                ],
                capture_output=True,
                text=True,
                timeout=30,
                env=env,
            )
            stdout = result.stdout.strip()
            if not stdout:
                stderr = result.stderr.strip()
                return {"success": False, "error": f"No output from PSI CLI (exit {result.returncode}). stderr: {stderr}"}
            return json.loads(stdout)
        except subprocess.TimeoutExpired:
            return {"success": False, "error": "PSI Tools CLI timed out after 30s."}
        except json.JSONDecodeError as e:
            return {"success": False, "error": f"Invalid JSON from PSI CLI: {e}. Raw: {stdout[:300]}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def run(self, action: str, args: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Execute action, trying direct HTTP first for speed, falling back to CLI."""
        params = args or {}
        # Try direct HTTP
        res = self._run_http(action, params)
        if res.get("success"):
            return res

        # Try CLI fallback
        cli_res = self._run_cli(action, params)
        if cli_res.get("success"):
            return cli_res

        # Return best error explanation
        return {
            "success": False,
            "error": res.get("error") or cli_res.get("error"),
            "note": "PSI Tools requires IntelliJ IDEA to be running with the PSI Tools plugin active (port 3000/3001)."
        }

    # ── High-Level Action Helpers ──────────────────────────────────────────

    def check_health(self) -> Dict[str, Any]:
        return self.run("health")

    def health(self) -> Dict[str, Any]:
        return self.check_health()

    def symbol_search(self, query: str, kind: str = "all", limit: int = 50) -> Dict[str, Any]:
        return self.run("symbol_search", {"query": query, "kind": kind, "limit": limit})

    def file_search(self, pattern: str, include_tests: bool = True) -> Dict[str, Any]:
        return self.run("file_search", {"pattern": pattern, "includeTests": include_tests})

    def text_search(self, query: str, regex: bool = False, file_pattern: str = None, case_sensitive: bool = True) -> Dict[str, Any]:
        args = {"query": query, "regex": regex, "caseSensitive": case_sensitive}
        if file_pattern:
            args["filePattern"] = file_pattern
        return self.run("text_search", args)

    def get_class_structure(self, class_name: str) -> Dict[str, Any]:
        return self.run("get_class_structure", {"className": class_name})

    def get_method_body(self, method: str) -> Dict[str, Any]:
        return self.run("get_method_body", {"method": method})

    def get_imports(self, file_path: str) -> Dict[str, Any]:
        return self.run("get_imports", {"filePath": file_path})

    def get_annotations(self, class_name: str, include_members: bool = True) -> Dict[str, Any]:
        return self.run("get_annotations", {"className": class_name, "includeMembers": include_members})

    def find_usages(self, symbol: str, scope: str = "project", include_hierarchy: bool = True) -> Dict[str, Any]:
        return self.run("find_usages", {"symbol": symbol, "scope": scope, "includeHierarchy": include_hierarchy})

    def get_call_graph(self, method: str, direction: str = "both", depth: int = 2, max_nodes: int = 50) -> Dict[str, Any]:
        return self.run("get_call_graph", {"method": method, "direction": direction, "depth": depth, "maxNodes": max_nodes})

    def get_method_hierarchy(self, method: str, direction: str = "both") -> Dict[str, Any]:
        return self.run("get_method_hierarchy", {"method": method, "direction": direction})

    def show_subclasses(self, class_name: str, include_indirect: bool = True, limit: int = 50) -> Dict[str, Any]:
        return self.run("show_subclasses", {"className": class_name, "includeIndirect": include_indirect, "limit": limit})

    def show_superclasses(self, class_name: str) -> Dict[str, Any]:
        return self.run("show_superclasses", {"className": class_name})

    def find_implementations(self, interface_name: str, include_abstract: bool = False, limit: int = 50) -> Dict[str, Any]:
        return self.run("find_implementations", {"interfaceName": interface_name, "includeAbstract": include_abstract, "limit": limit})

    def get_type_hierarchy(self, class_name: str, direction: str = "both") -> Dict[str, Any]:
        return self.run("get_type_hierarchy", {"className": class_name, "direction": direction})

    def explore_class_dependencies(
        self,
        class_name: str,
        direction: str = "both",
        depth: int = 2,
        include_jdk: bool = False,
        include_libraries: bool = False,
        max_classes: int = 50,
    ) -> Dict[str, Any]:
        return self.run(
            "explore_class_dependencies",
            {
                "className": class_name,
                "direction": direction,
                "depth": depth,
                "includeJdk": include_jdk,
                "includeLibraries": include_libraries,
                "maxClasses": max_classes,
            },
        )

    def get_changed_line_ranges(self, diff_mode: str = "working_tree_vs_head", commit_range: str = None, file_pattern: str = None) -> Dict[str, Any]:
        args = {"diffMode": diff_mode}
        if commit_range:
            args["commitRange"] = commit_range
        if file_pattern:
            args["filePattern"] = file_pattern
        return self.run("get_changed_line_ranges", args)

    def get_file_inspections(self, file_path: str) -> Dict[str, Any]:
        return self.run("get_file_inspections", {"filePath": file_path})

    def get_changeset_inspections(self, diff_mode: str = "working_tree_vs_head") -> Dict[str, Any]:
        return self.run("get_changeset_inspections", {"diffMode": diff_mode})
