"""
CopilotLens - Blast Radius & Minimal Context Calculator
=========================================================
Calculates the exact minimal set of files affected by a change (blast radius).
Combines:
- Direct imports & dependents (DependencyGraph)
- Named symbol usages (DependencyAnalyzer)
- Historical co-change pairs (GitAnalyzer)
- Associated test files

Provides concrete token-savings metrics:
e.g., "Full codebase: 2,348 files -> Blast Radius: 4 files (99.8% token reduction)"
"""

import os
from pathlib import Path
from typing import List, Union


class BlastRadiusAnalyzer:
    def __init__(self, repo_path: str, dep_analyzer, git_analyzer):
        self.repo_path = Path(repo_path).resolve()
        self.dep_analyzer = dep_analyzer
        self.git_analyzer = git_analyzer

    def calculate_blast_radius(self, target_files: Union[str, List[str]]) -> dict:
        """
        Calculate the minimal review set and blast radius for one or more files.

        Args:
            target_files: A single file path string or a list of file paths.

        Returns:
            Dictionary containing:
            - target_files
            - direct_dependents (files that import the targets)
            - co_change_partners (files historically modified together)
            - test_files (matching test/spec files)
            - minimal_review_set (combined deduplicated file list)
            - token_savings_estimate (stats & percentage reduction)
        """
        if isinstance(target_files, str):
            # If comma-separated or space-separated, split
            targets = [f.strip() for f in target_files.replace(",", " ").split() if f.strip()]
        else:
            targets = target_files

        if not targets:
            return {"error": "No target files provided."}

        graph = self.dep_analyzer.build_graph()
        edges = graph.get("edges", [])
        all_nodes = graph.get("nodes", [])
        total_repo_files = max(len(all_nodes), 1)

        direct_dependents = set()
        imports_used = set()
        co_changes = set()
        test_files = set()

        co_pairs = self.git_analyzer.get_co_change_pairs(min_co_changes=2)

        for target in targets:
            norm_target = target.replace("\\", "/").strip("/")
            stem = Path(norm_target).stem.lower()

            # 1. Direct Dependents (Who imports target?)
            for edge in edges:
                e_target = edge["target"].replace("\\", "/").strip("/")
                e_source = edge["source"].replace("\\", "/").strip("/")
                if norm_target == e_target or norm_target.endswith(e_target) or e_target.endswith(norm_target):
                    direct_dependents.add(edge["source"])
                elif norm_target == e_source or norm_target.endswith(e_source) or e_source.endswith(norm_target):
                    imports_used.add(edge["target"])

            # 2. Co-Change Partners (Files modified together in Git)
            for pair in co_pairs:
                fa = pair["file_a"].replace("\\", "/").strip("/")
                fb = pair["file_b"].replace("\\", "/").strip("/")
                if norm_target == fa or norm_target.endswith(fa) or fa.endswith(norm_target):
                    co_changes.add(pair["file_b"])
                elif norm_target == fb or norm_target.endswith(fb) or fb.endswith(norm_target):
                    co_changes.add(pair["file_a"])

            # 3. Find associated Test Files
            for root, _, files in os.walk(self.repo_path):
                if any(skip in root for skip in [".git", "node_modules", "dist", "build", ".venv"]):
                    continue
                for fname in files:
                    fname_lower = fname.lower()
                    if len(stem) > 3 and (stem in fname_lower) and any(t in fname_lower for t in ["test", "spec"]):
                        rel = str((Path(root) / fname).relative_to(self.repo_path)).replace("\\", "/")
                        if rel not in targets:
                            test_files.add(rel)

        # Build Minimal Review Set (Deduplicated)
        minimal_set = list(set(targets) | direct_dependents | co_changes | test_files)
        review_count = len(minimal_set)

        # Calculate Token Savings Metric
        reduction_pct = round((1.0 - (review_count / max(total_repo_files, review_count))) * 100, 1)
        token_multiplier = round(total_repo_files / max(review_count, 1), 1)

        return {
            "targets": targets,
            "blast_radius_breakdown": {
                "direct_dependents": list(direct_dependents)[:10],
                "co_change_partners": list(co_changes)[:10],
                "associated_tests": list(test_files)[:10]
            },
            "minimal_review_set": minimal_set[:25],
            "total_files_in_review_set": review_count,
            "total_repo_files": total_repo_files,
            "token_savings": {
                "reduction_percentage": f"{reduction_pct}%",
                "token_reduction_multiplier": f"{token_multiplier}x fewer tokens",
                "summary": (
                    f"Context reduced from {total_repo_files} repository files down to "
                    f"{review_count} precise files ({reduction_pct}% token reduction / {token_multiplier}x savings)."
                )
            }
        }
