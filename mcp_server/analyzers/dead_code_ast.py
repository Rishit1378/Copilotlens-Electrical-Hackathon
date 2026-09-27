"""
CopilotLens - AST-Enhanced Dead Code Analyzer
===============================================
Distinguishes AST-confirmed dead code issues (private/local symbols, unused imports)
from heuristic candidates (public exported functions without static callers).
Supports Python, JavaScript, TypeScript, and Java via AST adapters.
"""

import os
import re
from pathlib import Path
from collections import defaultdict, Counter
from typing import Dict, List, Any

from .ast_adapters import ASTManager

SKIP_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv",
    "dist", "build", "target", ".idea", ".gradle", "vendor"
}

ALWAYS_IGNORE = {
    "main", "Main", "App", "Application", "Index", "setup", "teardown",
    "setUp", "tearDown", "init", "__init__", "__str__", "__repr__",
    "toString", "hashCode", "equals", "run", "start", "stop",
    "render", "execute", "handle", "process", "test", "Test"
}


class ASTDeadCodeDetector:
    """AST-based dead code detector with confirmed vs heuristic classification."""

    def __init__(self, repo_path: str):
        self.repo_path = Path(repo_path).resolve()
        self.ast_manager = ASTManager()

    def find_dead_code(self, limit_files: int = 250) -> List[Dict[str, Any]]:
        """
        Scans codebase and categorizes unused symbols into:
        - CONFIRMED_ISSUE: Unused private/local functions, unused imports
        - HEURISTIC_CANDIDATE: Public/exported functions with 0 static callers
        """
        all_symbols = []  # List of {symbol, defined_in, line, kind, visibility, is_exported}
        all_imports = []  # List of {module, symbol, file, line}
        all_calls = Counter()

        # Step 1: AST Parsing of all files
        file_count = 0
        for root, dirs, files in os.walk(self.repo_path):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            for fname in files:
                if file_count >= limit_files:
                    break
                fpath = Path(root) / fname
                adapter = self.ast_manager.get_adapter(str(fpath))
                if not adapter:
                    continue

                rel_path = str(fpath.relative_to(self.repo_path)).replace("\\", "/")
                try:
                    code = fpath.read_text(encoding="utf-8", errors="replace")
                except Exception:
                    continue

                file_count += 1
                analysis = self.ast_manager.analyze_file(str(fpath), code)

                for sym in analysis.get("symbols", []):
                    if sym["name"] in ALWAYS_IGNORE or len(sym["name"]) < 3:
                        continue
                    sym["defined_in"] = rel_path
                    all_symbols.append(sym)

                for imp in analysis.get("imports", []):
                    if imp.get("symbol") and len(imp["symbol"]) > 2:
                        all_imports.append({
                            "symbol": imp["symbol"],
                            "module": imp.get("module", ""),
                            "defined_in": rel_path,
                            "line": imp.get("line", 1)
                        })

                for call in analysis.get("calls", []):
                    all_calls[call["name"]] += 1

        if not all_symbols and not all_imports:
            return []

        # Step 2: Classify symbols
        results = []

        # Check Unused Imports
        for imp in all_imports:
            sym_name = imp["symbol"]
            # Occurrences of symbol in call map
            count = all_calls.get(sym_name, 0)
            if count == 0:
                results.append({
                    "symbol": sym_name,
                    "defined_in": imp["defined_in"],
                    "line": imp["line"],
                    "type": "import",
                    "category": "CONFIRMED_ISSUE",
                    "confidence": "HIGH",
                    "reason": f"Unused imported symbol '{sym_name}' from module '{imp['module']}'"
                })

        # Check Unused Definitions
        for sym in all_symbols:
            sym_name = sym["name"]
            count = all_calls.get(sym_name, 0)

            if count == 0:
                is_private = sym.get("visibility") == "private"
                is_exported = sym.get("is_exported", False)

                if is_private:
                    category = "CONFIRMED_ISSUE"
                    confidence = "HIGH"
                    reason = f"Unreferenced internal/private {sym['kind']} '{sym_name}'"
                elif not is_exported:
                    category = "CONFIRMED_ISSUE"
                    confidence = "HIGH"
                    reason = f"Unreferenced non-exported {sym['kind']} '{sym_name}'"
                else:
                    category = "HEURISTIC_CANDIDATE"
                    confidence = "MEDIUM"
                    reason = f"Public/exported {sym['kind']} '{sym_name}' has 0 static callers in repo (may be entry point)"

                results.append({
                    "symbol": sym_name,
                    "defined_in": sym["defined_in"],
                    "line": sym["start_line"],
                    "type": sym["kind"],
                    "category": category,
                    "confidence": confidence,
                    "reason": reason
                })

        # Sort: CONFIRMED_ISSUE first, then by name
        results.sort(key=lambda x: (x["category"] != "CONFIRMED_ISSUE", x["symbol"]))
        return results[:60]
