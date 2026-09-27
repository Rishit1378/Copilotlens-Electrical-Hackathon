"""
CopilotLens - Git Analyzer
Analyzes git history to compute: churn, hotspots, ownership, bus factor, co-change pairs.
Works on ANY git repository — no special setup needed.
"""

import os
import re
from pathlib import Path
from collections import defaultdict, Counter
from datetime import datetime, timedelta, timezone
from typing import Optional


def _try_git_import():
    try:
        import git
        return git
    except ImportError:
        return None


class GitAnalyzer:
    def __init__(self, repo_path: str):
        self.repo_path = Path(repo_path).resolve()
        self._git = _try_git_import()
        self._repo = None
        self._commits_cache = None
        self._file_stats_cache = None
        self._available = False

        if self._git is None:
            print("[GitAnalyzer] gitpython not installed, using fallback git CLI")
            return

        try:
            self._repo = self._git.Repo(self.repo_path, search_parent_directories=True)
            self._available = True
        except Exception as e:
            print(f"[GitAnalyzer] Not a git repo or error: {e}")

    def _run_git(self, *args) -> str:
        """Run git command directly via subprocess."""
        import subprocess
        try:
            result = subprocess.run(
                ["git", "--no-pager", "-C", str(self.repo_path)] + list(args),
                capture_output=True, text=True, timeout=30
            )
            return result.stdout.strip()
        except Exception:
            return ""

    def get_file_stats(self, days: int = 90) -> dict:
        """
        Returns per-file stats: commit_count, authors, last_changed.
        Uses git log --numstat for speed.
        """
        if self._file_stats_cache is not None:
            return self._file_stats_cache

        since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        raw = self._run_git(
            "log", f"--since={since}", "--numstat",
            "--pretty=format:COMMIT|%H|%ae|%ad", "--date=short"
        )

        file_stats = defaultdict(lambda: {
            "commit_count": 0,
            "authors": set(),
            "additions": 0,
            "deletions": 0,
            "last_changed": None
        })

        current_author = None
        current_date = None

        for line in raw.splitlines():
            if line.startswith("COMMIT|"):
                parts = line.split("|")
                current_author = parts[2] if len(parts) > 2 else "unknown"
                current_date = parts[3] if len(parts) > 3 else None
                continue

            parts = line.split("\t")
            if len(parts) == 3:
                adds_str, dels_str, filepath = parts
                if filepath and not filepath.startswith("-"):
                    # Skip binary files (shown as "-")
                    try:
                        adds = int(adds_str) if adds_str != "-" else 0
                        dels = int(dels_str) if dels_str != "-" else 0
                    except ValueError:
                        adds, dels = 0, 0

                    stats = file_stats[filepath]
                    stats["commit_count"] += 1
                    if current_author:
                        stats["authors"].add(current_author)
                    stats["additions"] += adds
                    stats["deletions"] += dels
                    if stats["last_changed"] is None:
                        stats["last_changed"] = current_date

        # Convert sets to lists for JSON serialization
        result = {}
        for filepath, stats in file_stats.items():
            result[filepath] = {
                **stats,
                "authors": list(stats["authors"]),
                "churn": stats["additions"] + stats["deletions"]
            }

        self._file_stats_cache = result
        return result

    def get_hotspots(self, n: int = 15) -> list:
        """
        Returns top N hotspot files, sorted by commit_count (churn frequency).
        Hotspots = high-churn = high risk.
        """
        stats = self.get_file_stats()
        sorted_files = sorted(
            stats.items(),
            key=lambda x: (x[1]["commit_count"], x[1]["churn"]),
            reverse=True
        )
        result = []
        for filepath, data in sorted_files[:n]:
            result.append({
                "path": filepath,
                "commit_count": data["commit_count"],
                "churn": data["churn"],
                "authors": data["authors"][:5],
                "last_changed": data["last_changed"],
                "risk_level": _compute_risk(data["commit_count"])
            })
        return result

    def get_module_owners(self) -> list:
        """
        Returns per-file ownership: which author has the most commits on that file.
        """
        stats = self.get_file_stats()
        # Use separate git log per-author is expensive; approximate from numstat
        # We collect author per commit per file via full log
        raw = self._run_git(
            "log", "--since=180 days ago", "--pretty=format:%ae", "--name-only"
        )

        file_author_counts = defaultdict(Counter)
        current_author = None
        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue
            if "@" in line or line == "unknown":
                current_author = line
            elif current_author:
                file_author_counts[line][current_author] += 1

        result = []
        for filepath, author_counts in file_author_counts.items():
            if not author_counts:
                continue
            top_author, count = author_counts.most_common(1)[0]
            total = sum(author_counts.values())
            bus_factor = len(author_counts)
            result.append({
                "path": filepath,
                "owner": top_author,
                "owner_commit_share": round(count / total * 100) if total > 0 else 0,
                "bus_factor": bus_factor,
                "all_authors": dict(author_counts.most_common(5))
            })

        # Sort by lowest bus_factor (highest risk)
        result.sort(key=lambda x: x["bus_factor"])
        return result[:50]

    def get_co_change_pairs(self, min_co_changes: int = 3) -> list:
        """
        Find files that are frequently modified in the same commit — hidden coupling.
        These files are coupled by behavior even if they don't import each other.
        Use this before refactoring to find non-obvious blast radius.
        """
        # Get all commits with their changed files
        raw = self._run_git(
            "log", "--since=90 days ago",
            "--pretty=format:COMMIT",
            "--name-only"
        )

        # Parse commit groups
        commits = []
        current = []
        for line in raw.splitlines():
            line = line.strip()
            if line == "COMMIT":
                if current:
                    commits.append(set(current))
                current = []
            elif line and not line.startswith("Merge"):
                current.append(line)
        if current:
            commits.append(set(current))

        # Count co-occurrence pairs
        from collections import Counter
        pair_counts = Counter()
        for file_set in commits:
            files = sorted(file_set)
            for i in range(len(files)):
                for j in range(i + 1, min(i + 10, len(files))):
                    pair = (files[i], files[j])
                    pair_counts[pair] += 1

        # Filter and format
        results = []
        for (f1, f2), count in pair_counts.most_common(30):
            if count >= min_co_changes:
                results.append({
                    "file_a": f1,
                    "file_b": f2,
                    "co_change_count": count,
                    "coupling_strength": "HIGH" if count >= 8 else "MEDIUM" if count >= 5 else "LOW",
                    "insight": f"Modified together {count}x — likely coupled in behavior"
                })

        return results

    def get_repo_summary(self) -> dict:
        """High-level repository summary."""
        total_commits = self._run_git("rev-list", "--count", "HEAD")
        branches = self._run_git("branch", "-r", "--list").count("\n") + 1
        contributors = self._run_git(
            "shortlog", "-sn", "--since=90 days ago", "HEAD"
        )
        contributor_list = []
        for line in contributors.splitlines():
            parts = line.strip().split("\t", 1)
            if len(parts) == 2:
                contributor_list.append({"name": parts[1], "commits": int(parts[0].strip())})

        stats = self.get_file_stats()
        return {
            "total_commits": int(total_commits) if total_commits.isdigit() else 0,
            "total_files_changed": len(stats),
            "remote_branches": branches,
            "active_contributors_90d": contributor_list[:10],
            "analysis_window_days": 90
        }


def _compute_risk(commit_count: int) -> str:
    if commit_count >= 30:
        return "CRITICAL"
    elif commit_count >= 15:
        return "HIGH"
    elif commit_count >= 5:
        return "MEDIUM"
    return "LOW"
