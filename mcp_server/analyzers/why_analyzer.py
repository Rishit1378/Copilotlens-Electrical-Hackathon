"""
CopilotLens - get_why() Analyzer
Git archaeology: explains WHY code in a file exists by analyzing:
- Commit messages and bodies for the file
- Inline comments/docstrings that explain decisions
- Patterns like "fix", "because", "refactor", "workaround"
"""

import re
import subprocess
from pathlib import Path
from collections import defaultdict


# Commit message patterns that signal architectural decisions
DECISION_PATTERNS = {
    "fix":        re.compile(r"\b(fix|fixes|fixed|bug|bugfix|patch|hotfix)\b", re.I),
    "refactor":   re.compile(r"\b(refactor|rewrite|restructure|cleanup|clean up|simplify)\b", re.I),
    "feature":    re.compile(r"\b(add|implement|introduce|feature|support|enable)\b", re.I),
    "workaround": re.compile(r"\b(workaround|hack|temporary|temp|todo|fixme|kludge)\b", re.I),
    "perf":       re.compile(r"\b(perf|performance|optimize|optimization|speed|slow|fast)\b", re.I),
    "security":   re.compile(r"\b(security|auth|authz|authn|token|secret|vulnerability|cve)\b", re.I),
    "breaking":   re.compile(r"\b(breaking|break|deprecat|remove|drop|delete)\b", re.I),
    "decision":   re.compile(r"\b(because|reason|decision|chose|chosen|prefer|instead of|rather than)\b", re.I),
}

# Inline comment patterns that explain WHY (not what)
WHY_COMMENT_PATTERNS = [
    re.compile(r"#\s*(TODO|FIXME|HACK|NOTE|WORKAROUND|REASON|WHY):?\s*(.+)", re.I),
    re.compile(r"//\s*(TODO|FIXME|HACK|NOTE|WORKAROUND|REASON|WHY):?\s*(.+)", re.I),
    re.compile(r"/\*+\s*(TODO|FIXME|HACK|NOTE|WORKAROUND|REASON|WHY):?\s*(.+?)\**/", re.I),
    re.compile(r"#\s*(because|this is|we need|required|workaround|temporary).+", re.I),
    re.compile(r"//\s*(because|this is|we need|required|workaround|temporary).+", re.I),
]


class WhyAnalyzer:
    def __init__(self, repo_path: str):
        self.repo_path = Path(repo_path).resolve()

    def get_why(self, filepath: str, max_commits: int = 20) -> dict:
        """
        Explain why a file exists and why it changed the way it did.
        Returns: commit rationale, decision types, inline why-comments, summary.
        """
        # 1. Get commit history for this file
        commits = self._get_file_commits(filepath, max_commits)

        # 2. Classify commits by decision type
        classified = self._classify_commits(commits)

        # 3. Extract inline why-comments from the file
        inline_comments = self._extract_why_comments(filepath)

        # 4. Build a narrative summary
        summary = self._build_summary(filepath, classified, inline_comments)

        return {
            "path": filepath,
            "commit_history": commits[:10],  # Top 10 most recent
            "decision_breakdown": classified["by_type"],
            "key_decisions": classified["key_decisions"],
            "inline_why_comments": inline_comments,
            "narrative": summary,
            "total_commits_analyzed": len(commits)
        }

    def _get_file_commits(self, filepath: str, limit: int) -> list:
        """Get commit log for a specific file."""
        result = subprocess.run(
            [
                "git", "--no-pager", "-C", str(self.repo_path),
                "log", "--follow",
                f"--max-count={limit}",
                "--pretty=format:%H|%ae|%ad|%s|%b",
                "--date=short",
                "--", filepath
            ],
            capture_output=True, text=True, timeout=15
        )

        commits = []
        for block in result.stdout.strip().split("\n"):
            if not block.strip():
                continue
            parts = block.split("|", 4)
            if len(parts) >= 4:
                commits.append({
                    "hash": parts[0][:8],
                    "author": parts[1],
                    "date": parts[2],
                    "subject": parts[3].strip(),
                    "body": parts[4].strip() if len(parts) > 4 else ""
                })
        return commits

    def _classify_commits(self, commits: list) -> dict:
        """Classify commits by decision type and extract key decisions."""
        type_counts = defaultdict(int)
        key_decisions = []

        for commit in commits:
            full_message = commit["subject"] + " " + commit.get("body", "")
            matched_types = []

            for dtype, pattern in DECISION_PATTERNS.items():
                if pattern.search(full_message):
                    type_counts[dtype] += 1
                    matched_types.append(dtype)

            # A "key decision" is one with a meaningful body or decision language
            if commit.get("body") or "decision" in matched_types or "workaround" in matched_types:
                key_decisions.append({
                    "date": commit["date"],
                    "author": commit["author"],
                    "message": commit["subject"],
                    "detail": commit.get("body", "")[:200],
                    "type": matched_types[0] if matched_types else "general"
                })

        return {
            "by_type": dict(type_counts),
            "key_decisions": key_decisions[:5]
        }

    def _extract_why_comments(self, filepath: str) -> list:
        """Extract comments that explain WHY (not just what) from source code."""
        abs_path = self.repo_path / filepath
        if not abs_path.exists():
            return []

        try:
            content = abs_path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return []

        found = []
        for pattern in WHY_COMMENT_PATTERNS:
            for match in pattern.finditer(content):
                line_no = content[:match.start()].count("\n") + 1
                text = match.group(0).strip()
                if len(text) > 10:  # Skip trivially short matches
                    found.append({
                        "line": line_no,
                        "comment": text[:200]
                    })

        # Deduplicate by line number
        seen_lines = set()
        unique = []
        for item in found:
            if item["line"] not in seen_lines:
                seen_lines.add(item["line"])
                unique.append(item)

        return unique[:10]

    def _build_summary(self, filepath: str, classified: dict, comments: list) -> str:
        """Build a human-readable narrative about why this file exists."""
        by_type = classified["by_type"]
        key = classified["key_decisions"]

        parts = [f"Analysis of `{filepath}`:"]

        if not by_type and not comments:
            return f"No significant commit history or decision comments found for `{filepath}`."

        dominant = sorted(by_type.items(), key=lambda x: x[1], reverse=True)
        if dominant:
            top = dominant[0]
            parts.append(
                f"This file has primarily seen **{top[0]}** changes ({top[1]} commits)."
            )

        if "workaround" in by_type:
            parts.append(
                f"⚠️ {by_type['workaround']} commit(s) mention workarounds or hacks — "
                "check inline comments before modifying."
            )

        if "security" in by_type:
            parts.append(
                f"🔒 {by_type['security']} security-related change(s) — approach with caution."
            )

        if "breaking" in by_type:
            parts.append(
                f"💥 {by_type['breaking']} breaking change(s) in history — "
                "downstream consumers may be sensitive to further changes."
            )

        if key:
            parts.append(f"\nKey decision: \"{key[0]['message']}\" ({key[0]['date']})")

        if comments:
            parts.append(
                f"\n{len(comments)} inline explanation comment(s) found "
                f"(e.g. line {comments[0]['line']}: {comments[0]['comment'][:80]}...)"
            )

        return " ".join(parts)
