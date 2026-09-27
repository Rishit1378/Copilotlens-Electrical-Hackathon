"""
CopilotLens - Codebase Knowledge Graph Engine
==============================================
Local in-memory knowledge graph mapping relationships between code files,
symbols, import dependencies, tests, git hotspots, defect risks, and policy rules.
Provides multi-hop relationship queries and regression risk path tracing.
"""

from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Any, Optional

from .ast_adapters import ASTManager
from .dependency import DependencyAnalyzer
from .git_analyzer import GitAnalyzer
from .policy_repo import PolicyRepository


class CodebaseKnowledgeGraph:
    """Multi-hop relationship graph for code, tests, defects, and policies."""

    def __init__(self, repo_path: str):
        self.repo_path = Path(repo_path).resolve()
        self.ast_manager = ASTManager()
        self.dep_analyzer = DependencyAnalyzer(str(self.repo_path))
        self.git_analyzer = GitAnalyzer(str(self.repo_path))
        self.policy_repo = PolicyRepository(str(self.repo_path))

    def build_graph(self) -> Dict[str, Any]:
        """Build graph nodes and edges across repository artifacts."""
        nodes = {}  # node_id -> {id, type, label, data}
        edges = []  # list of {source, target, relationship, weight}

        # 1. Dependency Graph (File-to-File imports)
        dep_graph = self.dep_analyzer.build_graph()
        for node in dep_graph.get("nodes", []):
            nid = node["id"]
            nodes[nid] = {
                "id": nid,
                "type": "file",
                "label": Path(nid).name,
                "is_hub": node.get("is_hub", False),
                "in_degree": node.get("in_degree", 0)
            }

        for edge in dep_graph.get("edges", []):
            edges.append({
                "source": edge["source"],
                "target": edge["target"],
                "relationship": "IMPORTS",
                "weight": 1.0
            })

        # 2. Git Hotspots & Co-Changes
        hotspots = self.git_analyzer.get_hotspots(15)
        for h in hotspots:
            nid = h["path"]
            if nid not in nodes:
                nodes[nid] = {"id": nid, "type": "file", "label": Path(nid).name}
            nodes[nid]["risk_level"] = h.get("risk_level", "LOW")
            nodes[nid]["commit_count"] = h.get("commit_count", 0)

        co_pairs = self.git_analyzer.get_co_change_pairs(min_co_changes=2)
        for p in co_pairs:
            edges.append({
                "source": p["file_a"],
                "target": p["file_b"],
                "relationship": "CO_CHANGES_WITH",
                "weight": float(p["co_change_count"])
            })

        # 3. Policy Rules
        rules = self.policy_repo.get_approved_rules()
        for r in rules:
            rid = f"policy:{r['id']}"
            nodes[rid] = {
                "id": rid,
                "type": "policy",
                "label": r["rule"][:30],
                "rule": r["rule"],
                "scope": r["scope"]
            }
            target_scope = r["scope"]
            if target_scope != "project" and target_scope in nodes:
                edges.append({
                    "source": rid,
                    "target": target_scope,
                    "relationship": "GOVERNS",
                    "weight": 2.0
                })

        return {
            "node_count": len(nodes),
            "edge_count": len(edges),
            "nodes": list(nodes.values()),
            "edges": edges
        }

    def query_graph(self, target: str, max_depth: int = 2) -> Dict[str, Any]:
        """
        Query connected relationships for a symbol or file up to max_depth hops.
        """
        full_graph = self.build_graph()
        nodes_by_id = {n["id"]: n for n in full_graph["nodes"]}

        adj = defaultdict(list)
        for e in full_graph["edges"]:
            adj[e["source"]].append((e["target"], e["relationship"], e["weight"]))
            adj[e["target"]].append((e["source"], f"REVERSE_{e['relationship']}", e["weight"]))

        visited_nodes = set()
        matched_edges = []
        queue = [(target, 0)]
        visited_nodes.add(target)

        while queue:
            curr, depth = queue.pop(0)
            if depth >= max_depth:
                continue

            for neighbor, rel, w in adj.get(curr, []):
                matched_edges.append({
                    "source": curr,
                    "target": neighbor,
                    "relationship": rel,
                    "weight": w
                })
                if neighbor not in visited_nodes:
                    visited_nodes.add(neighbor)
                    queue.append((neighbor, depth + 1))

        result_nodes = [nodes_by_id[nid] for nid in visited_nodes if nid in nodes_by_id]

        return {
            "query_target": target,
            "max_depth": max_depth,
            "subgraph_node_count": len(result_nodes),
            "subgraph_edge_count": len(matched_edges),
            "nodes": result_nodes,
            "edges": matched_edges
        }

    def get_regression_risk_paths(self, changed_files: List[str]) -> Dict[str, Any]:
        """
        Trace regression risk propagation paths for changed files.
        """
        full_graph = self.build_graph()
        risk_paths = []

        for f in changed_files:
            sub = self.query_graph(f, max_depth=2)
            dependents = [e["target"] for e in sub["edges"] if "IMPORTS" in e["relationship"]]
            co_changed = [e["target"] for e in sub["edges"] if "CO_CHANGES_WITH" in e["relationship"]]
            governing_policies = [e["source"] for e in sub["edges"] if "GOVERNS" in e["relationship"]]

            risk_paths.append({
                "changed_file": f,
                "direct_dependents": list(set(dependents)),
                "co_change_partners": list(set(co_changed)),
                "governing_policies": list(set(governing_policies)),
                "total_affected_nodes": len(sub["nodes"])
            })

        return {
            "changed_files": changed_files,
            "regression_risk_paths": risk_paths
        }
