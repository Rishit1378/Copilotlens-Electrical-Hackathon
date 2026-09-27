"""
CopilotLens - Codebase Search
Fast text and pattern search across all source files.
Returns matching lines with surrounding context.
Supports: exact text, regex, symbol/function name search.
"""

import os
import re
from pathlib import Path
from typing import Optional


SKIP_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv",
    "dist", "build", "target", ".idea", ".gradle", "vendor",
    ".next", ".nuxt", "coverage"
}

SOURCE_EXTENSIONS = {
    ".py", ".java", ".js", ".ts", ".jsx", ".tsx", ".cs",
    ".go", ".rb", ".php", ".cpp", ".c", ".h", ".kt", ".swift",
    ".scala", ".rs", ".vue", ".svelte"
}


class CodebaseSearch:
    def __init__(self, repo_path: str):
        self.repo_path = Path(repo_path).resolve()

    def search(
        self,
        query: str,
        search_type: str = "text",
        max_results: int = 20,
        context_lines: int = 2,
        file_extension: Optional[str] = None
    ) -> dict:
        """
        Search the codebase for a query string or pattern.

        Args:
            query: What to search for
            search_type: "text" (literal), "regex" (pattern), or "symbol" (function/class name)
            max_results: Max number of matches to return
            context_lines: Lines of context around each match
            file_extension: Filter to specific extension e.g. ".js"

        Returns:
            matches with file, line number, content, and surrounding context
        """
        if search_type == "symbol":
            # Wrap as a word-boundary regex for symbol search
            pattern = re.compile(r"\b" + re.escape(query) + r"\b", re.IGNORECASE)
        elif search_type == "regex":
            try:
                pattern = re.compile(query, re.IGNORECASE)
            except re.error as e:
                return {"error": f"Invalid regex: {e}", "matches": []}
        else:
            # Literal text search (case-insensitive)
            pattern = re.compile(re.escape(query), re.IGNORECASE)

        matches = []
        files_searched = 0

        for root, dirs, files in os.walk(self.repo_path):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            for fname in files:
                if len(matches) >= max_results:
                    break

                fpath = Path(root) / fname
                ext = fpath.suffix.lower()

                if ext not in SOURCE_EXTENSIONS:
                    continue
                if file_extension and ext != file_extension.lower():
                    continue

                try:
                    content = fpath.read_text(encoding="utf-8", errors="replace")
                except Exception:
                    continue

                files_searched += 1
                lines = content.splitlines()
                rel_path = str(fpath.relative_to(self.repo_path)).replace("\\", "/")

                for i, line in enumerate(lines):
                    if len(matches) >= max_results:
                        break
                    if pattern.search(line):
                        start = max(0, i - context_lines)
                        end = min(len(lines), i + context_lines + 1)
                        context = []
                        for ci in range(start, end):
                            context.append({
                                "line_no": ci + 1,
                                "content": lines[ci],
                                "is_match": ci == i
                            })
                        matches.append({
                            "file": rel_path,
                            "line": i + 1,
                            "match_text": line.strip()[:200],
                            "context": context
                        })

        # Group matches by file for cleaner output
        by_file = {}
        for m in matches:
            f = m["file"]
            if f not in by_file:
                by_file[f] = []
            by_file[f].append({"line": m["line"], "match": m["match_text"], "context": m["context"]})

        return {
            "query": query,
            "search_type": search_type,
            "total_matches": len(matches),
            "files_with_matches": len(by_file),
            "files_searched": files_searched,
            "results": [
                {"file": f, "matches": hits}
                for f, hits in list(by_file.items())[:15]
            ],
            "truncated": len(matches) >= max_results
        }

    def find_symbol_usages(self, symbol: str) -> dict:
        """
        Find all usages of a specific function, class, or variable name.
        Returns definition location + all call sites.
        """
        # Search for definition
        def_patterns = [
            re.compile(rf"^\s*(def|class|function|const|let|var|public|private|protected)\s+{re.escape(symbol)}\b", re.MULTILINE),
            re.compile(rf"^\s*{re.escape(symbol)}\s*[=:(]", re.MULTILINE),
        ]

        usage_pattern = re.compile(r"\b" + re.escape(symbol) + r"\b", re.IGNORECASE)

        definitions = []
        usages = []
        files_checked = 0

        for root, dirs, files in os.walk(self.repo_path):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            for fname in files:
                fpath = Path(root) / fname
                if fpath.suffix.lower() not in SOURCE_EXTENSIONS:
                    continue
                files_checked += 1

                try:
                    content = fpath.read_text(encoding="utf-8", errors="replace")
                    lines = content.splitlines()
                except Exception:
                    continue

                rel = str(fpath.relative_to(self.repo_path)).replace("\\", "/")

                # Check for definition
                for dp in def_patterns:
                    for match in dp.finditer(content):
                        line_no = content[:match.start()].count("\n") + 1
                        definitions.append({
                            "file": rel,
                            "line": line_no,
                            "text": lines[line_no - 1].strip()[:100]
                        })

                # Count usages
                count = len(usage_pattern.findall(content))
                if count > 0:
                    usages.append({"file": rel, "usage_count": count})

        usages.sort(key=lambda x: x["usage_count"], reverse=True)

        return {
            "symbol": symbol,
            "definitions": definitions[:5],
            "used_in_files": usages[:20],
            "total_files_using": len(usages),
            "is_potentially_dead": len(usages) == 0 or (len(usages) == 1 and len(definitions) > 0)
        }
