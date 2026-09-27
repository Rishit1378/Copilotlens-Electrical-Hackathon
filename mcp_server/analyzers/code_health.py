"""
CopilotLens - Code Health Scorer
Deterministic, non-LLM-based health scoring for any source file.
Scores 0-100 (higher = healthier). Uses 12 weighted markers.
Supports: Python, Java, JavaScript, TypeScript, C#, Go, and more.
"""

import os
import re
from pathlib import Path
from typing import Optional


# Markers and their weights (negative = bad, positive = good)
MARKERS = {
    "file_too_large": {"weight": -20, "desc": "File exceeds 500 lines"},
    "very_large_file": {"weight": -10, "desc": "File exceeds 300 lines"},
    "too_many_todos": {"weight": -10, "desc": "More than 5 TODO/FIXME/HACK comments"},
    "no_comments": {"weight": -10, "desc": "Zero comment lines (undocumented)"},
    "deeply_nested": {"weight": -15, "desc": "Deep nesting (4+ levels)"},
    "long_functions": {"weight": -15, "desc": "Functions/methods > 50 lines"},
    "high_complexity": {"weight": -15, "desc": "Many branching paths (if/else/for/while)"},
    "magic_numbers": {"weight": -5, "desc": "Magic numbers (hardcoded literals)"},
    "coverity_rule_failure": {"weight": -25, "desc": "Coverity static analysis rule defect detected"},
    "good_comment_ratio": {"weight": 10, "desc": "Good documentation ratio (>10%)"},
    "short_file": {"weight": 5, "desc": "File is concise (<100 lines)"},
    "has_tests": {"weight": 10, "desc": "File appears to be test/spec file"},
    "consistent_style": {"weight": 5, "desc": "Consistent indentation and style"},
}

SUPPORTED_EXTENSIONS = {
    ".py", ".java", ".js", ".ts", ".jsx", ".tsx",
    ".cs", ".go", ".rb", ".php", ".cpp", ".c", ".h",
    ".kt", ".scala", ".swift"
}


class CodeHealthScorer:
    def __init__(self, repo_path: str):
        self.repo_path = Path(repo_path).resolve()

    def score_file(self, filepath: str) -> dict:
        """Score a single file. Returns score (0-100) + breakdown."""
        abs_path = self.repo_path / filepath if not os.path.isabs(filepath) else Path(filepath)

        if not abs_path.exists():
            return {"error": f"File not found: {filepath}", "score": 0}

        ext = abs_path.suffix.lower()
        if ext not in SUPPORTED_EXTENSIONS:
            return {
                "score": 50,
                "grade": "N/A",
                "note": f"Unsupported file type: {ext}",
                "markers": [],
                "lines": 0
            }

        try:
            content = abs_path.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            return {"error": str(e), "score": 0}

        lines = content.splitlines()
        total_lines = len(lines)
        return self._compute_score(filepath, content, lines, total_lines)

    def score_all_files(self, limit: int = 200) -> list:
        """Score all source files in the repo. Returns sorted list."""
        results = []
        count = 0
        for root, dirs, files in os.walk(self.repo_path):
            # Skip common non-source dirs
            dirs[:] = [d for d in dirs if d not in {
                ".git", "node_modules", "__pycache__", ".venv", "venv",
                "dist", "build", "target", ".idea", ".gradle", "vendor",
                ".next", "out", "dashboard-next"
            }]
            for fname in files:
                if count >= limit:
                    break
                fpath = Path(root) / fname
                if fpath.suffix.lower() in SUPPORTED_EXTENSIONS:
                    rel = str(fpath.relative_to(self.repo_path)).replace("\\", "/")
                    result = self.score_file(rel)
                    if "error" not in result:
                        result["path"] = rel
                        results.append(result)
                        count += 1

        results.sort(key=lambda x: x.get("score", 100))
        return results

    def get_summary(self) -> dict:
        """Compute aggregate health summary for the whole repo."""
        all_scores = self.score_all_files()
        if not all_scores:
            return {"avg_score": 0, "total_files": 0, "distribution": {}}

        scores = [f["score"] for f in all_scores]
        avg = round(sum(scores) / len(scores))

        distribution = {"critical": 0, "poor": 0, "fair": 0, "good": 0, "excellent": 0}
        for s in scores:
            if s < 30:
                distribution["critical"] += 1
            elif s < 50:
                distribution["poor"] += 1
            elif s < 70:
                distribution["fair"] += 1
            elif s < 85:
                distribution["good"] += 1
            else:
                distribution["excellent"] += 1

        worst_10 = all_scores[:10]
        best_10 = list(reversed(all_scores[-10:]))

        return {
            "avg_score": avg,
            "grade": _score_to_grade(avg),
            "total_files": len(all_scores),
            "distribution": distribution,
            "worst_files": worst_10,
            "best_files": best_10
        }

    def _compute_score(self, filepath: str, content: str, lines: list, total_lines: int) -> dict:
        score = 70  # Start at 70 (neutral-good baseline)
        fired_markers = []

        comment_lines = sum(1 for l in lines if _is_comment(l))
        blank_lines = sum(1 for l in lines if not l.strip())
        code_lines = total_lines - comment_lines - blank_lines

        # --- Negative markers ---
        if total_lines > 500:
            score += MARKERS["file_too_large"]["weight"]
            fired_markers.append({"id": "file_too_large", "impact": MARKERS["file_too_large"]["weight"],
                                   "desc": MARKERS["file_too_large"]["desc"], "detail": f"{total_lines} lines"})
        elif total_lines > 300:
            score += MARKERS["very_large_file"]["weight"]
            fired_markers.append({"id": "very_large_file", "impact": MARKERS["very_large_file"]["weight"],
                                   "desc": MARKERS["very_large_file"]["desc"], "detail": f"{total_lines} lines"})

        todo_count = len(re.findall(r"\b(TODO|FIXME|HACK|XXX|BUG)\b", content, re.IGNORECASE))
        if todo_count > 5:
            score += MARKERS["too_many_todos"]["weight"]
            fired_markers.append({"id": "too_many_todos", "impact": MARKERS["too_many_todos"]["weight"],
                                   "desc": MARKERS["too_many_todos"]["desc"], "detail": f"{todo_count} found"})

        if code_lines > 10 and comment_lines == 0:
            score += MARKERS["no_comments"]["weight"]
            fired_markers.append({"id": "no_comments", "impact": MARKERS["no_comments"]["weight"],
                                   "desc": MARKERS["no_comments"]["desc"]})

        # Nesting depth approximation (count lines with 4+ levels of indent)
        deep_nesting = sum(1 for l in lines if len(l) - len(l.lstrip()) >= 16)  # 4 tabs * 4 spaces
        if deep_nesting > 5:
            score += MARKERS["deeply_nested"]["weight"]
            fired_markers.append({"id": "deeply_nested", "impact": MARKERS["deeply_nested"]["weight"],
                                   "desc": MARKERS["deeply_nested"]["desc"], "detail": f"{deep_nesting} deeply nested lines"})

        # Function length heuristic
        long_func = _count_long_functions(lines)
        if long_func > 0:
            score += MARKERS["long_functions"]["weight"]
            fired_markers.append({"id": "long_functions", "impact": MARKERS["long_functions"]["weight"],
                                   "desc": MARKERS["long_functions"]["desc"], "detail": f"{long_func} long function(s)"})

        # Cyclomatic complexity proxy: count branches
        branches = len(re.findall(
            r"\b(if|else|elif|for|while|switch|case|catch|&&|\|\|)\b", content
        ))
        complexity_ratio = branches / max(code_lines, 1)
        if complexity_ratio > 0.3:
            score += MARKERS["high_complexity"]["weight"]
            fired_markers.append({"id": "high_complexity", "impact": MARKERS["high_complexity"]["weight"],
                                   "desc": MARKERS["high_complexity"]["desc"],
                                   "detail": f"{branches} branches ({complexity_ratio:.0%} density)"})

        # Magic numbers
        magic = len(re.findall(r"(?<![a-zA-Z_])\b[0-9]{2,}\b(?!\s*[;,\)]?\s*$)", content))
        if magic > 10:
            score += MARKERS["magic_numbers"]["weight"]
            fired_markers.append({"id": "magic_numbers", "impact": MARKERS["magic_numbers"]["weight"],
                                   "desc": MARKERS["magic_numbers"]["desc"], "detail": f"{magic} magic numbers"})

        # --- Positive markers ---
        comment_ratio = comment_lines / max(total_lines, 1)
        if comment_ratio > 0.1:
            score += MARKERS["good_comment_ratio"]["weight"]
            fired_markers.append({"id": "good_comment_ratio", "impact": MARKERS["good_comment_ratio"]["weight"],
                                   "desc": MARKERS["good_comment_ratio"]["desc"],
                                   "detail": f"{comment_ratio:.0%} comments"})

        if total_lines < 100:
            score += MARKERS["short_file"]["weight"]
            fired_markers.append({"id": "short_file", "impact": MARKERS["short_file"]["weight"],
                                   "desc": MARKERS["short_file"]["desc"]})

        is_test = bool(re.search(r"(test|spec|_test\.|\.test\.|Test\.)", filepath, re.IGNORECASE))
        if is_test:
            score += MARKERS["has_tests"]["weight"]
            fired_markers.append({"id": "has_tests", "impact": MARKERS["has_tests"]["weight"],
                                   "desc": MARKERS["has_tests"]["desc"]})

        score = max(0, min(100, score))
        return {
            "score": score,
            "grade": _score_to_grade(score),
            "lines": total_lines,
            "code_lines": code_lines,
            "comment_lines": comment_lines,
            "todo_count": todo_count,
            "markers": fired_markers,
            "is_test_file": is_test
        }


def _is_comment(line: str) -> bool:
    stripped = line.strip()
    return (
        stripped.startswith("#") or
        stripped.startswith("//") or
        stripped.startswith("*") or
        stripped.startswith("/*") or
        stripped.startswith("'") or  # VB
        stripped.startswith("--")    # SQL/Lua
    )


def _count_long_functions(lines: list, threshold: int = 50) -> int:
    """Approximate count of functions longer than threshold lines."""
    func_pattern = re.compile(
        r"^\s*(def |public |private |protected |func |function |async function )"
    )
    long_count = 0
    func_start = None
    for i, line in enumerate(lines):
        if func_pattern.match(line):
            if func_start is not None and (i - func_start) > threshold:
                long_count += 1
            func_start = i
    return long_count


def _score_to_grade(score: int) -> str:
    if score >= 85:
        return "A"
    elif score >= 70:
        return "B"
    elif score >= 55:
        return "C"
    elif score >= 40:
        return "D"
    return "F"
