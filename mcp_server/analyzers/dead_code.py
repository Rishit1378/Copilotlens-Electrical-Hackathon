"""
CopilotLens - Dead Code Detector
Finds functions, classes, and variables that are defined but never referenced.
Heuristic-based, works across Python, Java, JS/TS.
"""

import os
import re
from pathlib import Path
from collections import defaultdict


SKIP_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv",
    "dist", "build", "target", ".idea", ".gradle", "vendor"
}

# Patterns to find DEFINITIONS
DEFINITION_PATTERNS = {
    ".py": [
        re.compile(r"^(?:def|class)\s+([A-Za-z_][A-Za-z0-9_]*)", re.MULTILINE),
    ],
    ".java": [
        re.compile(
            r"(?:public|private|protected|static|final|\s)+\s+\w+\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(",
            re.MULTILINE
        ),
        re.compile(r"(?:public|private|protected)\s+(?:class|interface|enum)\s+([A-Za-z_][A-Za-z0-9_]*)", re.MULTILINE),
    ],
    ".js": [
        re.compile(r"(?:function\s+([A-Za-z_][A-Za-z0-9_]*)|(?:const|let|var)\s+([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(?:async\s+)?(?:function|\())", re.MULTILINE),
    ],
    ".ts": [
        re.compile(r"(?:function\s+([A-Za-z_][A-Za-z0-9_]*)|(?:const|let|var)\s+([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(?:async\s+)?(?:function|\()|class\s+([A-Za-z_][A-Za-z0-9_]*))", re.MULTILINE),
    ],
}
DEFINITION_PATTERNS[".jsx"] = DEFINITION_PATTERNS[".js"]
DEFINITION_PATTERNS[".tsx"] = DEFINITION_PATTERNS[".ts"]
DEFINITION_PATTERNS[".kt"] = DEFINITION_PATTERNS[".java"]


# Common symbols to always ignore (built-ins, test annotations, etc.)
ALWAYS_IGNORE = {
    "main", "Main", "App", "Application", "Index", "setup", "teardown",
    "setUp", "tearDown", "init", "__init__", "__str__", "__repr__",
    "toString", "hashCode", "equals", "run", "start", "stop",
    "render", "execute", "handle", "process", "test", "Test"
}


class DeadCodeDetector:
    def __init__(self, repo_path: str):
        self.repo_path = Path(repo_path).resolve()

    def find_dead_code(self, limit: int = 200) -> list:
        """
        Returns a list of potentially unused symbols.
        Each item: {symbol, defined_in, type, confidence}
        """
        # Step 1: Collect all definitions
        definitions = {}  # symbol -> {file, type, line}

        for root, dirs, files in os.walk(self.repo_path):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            for fname in files[:limit]:
                fpath = Path(root) / fname
                ext = fpath.suffix.lower()
                if ext not in DEFINITION_PATTERNS:
                    continue

                rel = str(fpath.relative_to(self.repo_path)).replace("\\", "/")
                try:
                    content = fpath.read_text(encoding="utf-8", errors="replace")
                except Exception:
                    continue

                for pattern in DEFINITION_PATTERNS[ext]:
                    for match in pattern.finditer(content):
                        # Get the first non-None group
                        symbol = next((g for g in match.groups() if g), None)
                        if not symbol or symbol in ALWAYS_IGNORE:
                            continue
                        if len(symbol) < 3:  # Skip very short names
                            continue
                        if symbol not in definitions:
                            line_no = content[:match.start()].count("\n") + 1
                            sym_type = "function" if "def " in match.group() or "function" in match.group() else "class"
                            definitions[symbol] = {
                                "symbol": symbol,
                                "defined_in": rel,
                                "type": sym_type,
                                "line": line_no
                            }

        if not definitions:
            return []

        # Step 2: Scan all source files for references
        all_content = self._collect_all_content()

        # Step 3: Find symbols with zero references (outside their definition file)
        from collections import Counter
        # Tokenize all content once to count occurrences (massive speedup)
        word_counts = Counter(re.findall(r"\b\w+\b", all_content))
        
        dead_candidates = []
        for symbol, info in definitions.items():
            count = word_counts.get(symbol, 0)

            # A definition itself counts as 1 occurrence; < 2 means likely unused
            if count <= 1:
                info["reference_count"] = count
                info["confidence"] = "HIGH" if count == 0 else "MEDIUM"
                dead_candidates.append(info)

        # Sort by confidence then name
        dead_candidates.sort(key=lambda x: (x["confidence"] == "MEDIUM", x["symbol"]))
        return dead_candidates[:50]

    def _collect_all_content(self, max_files: int = 300) -> str:
        """Read source files into one string for reference counting. Capped for large repos."""
        parts = []
        extensions = set(DEFINITION_PATTERNS.keys())
        count = 0
        for root, dirs, files in os.walk(self.repo_path):
            if count >= max_files:
                break
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            for fname in files:
                if count >= max_files:
                    break
                fpath = Path(root) / fname
                if fpath.suffix.lower() in extensions:
                    try:
                        parts.append(fpath.read_text(encoding="utf-8", errors="replace"))
                        count += 1
                    except Exception:
                        pass
        return "\n".join(parts)
