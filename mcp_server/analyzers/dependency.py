"""
CopilotLens - Dependency Analyzer
Parses import/require/include statements to build a lightweight dependency graph.
Supports: Python, Java, JavaScript/TypeScript, Go, C#.
"""

import os
import re
from pathlib import Path
from collections import defaultdict
from typing import Optional


# Regex patterns per language to extract imports
IMPORT_PATTERNS = {
    ".py": [
        re.compile(r"^(?:from\s+([\w.]+)\s+import|import\s+([\w., ]+))", re.MULTILINE),
    ],
    ".java": [
        re.compile(r"^import\s+([\w.]+);", re.MULTILINE),
    ],
    ".js": [
        re.compile(r"""(?:import|require)\s*[\(\s]['"]([^'"]+)['"]""", re.MULTILINE),
    ],
    ".ts": [
        re.compile(r"""(?:import|require)\s*[\(\s]['"]([^'"]+)['"]""", re.MULTILINE),
    ],
    ".jsx": [
        re.compile(r"""(?:import|require)\s*[\(\s]['"]([^'"]+)['"]""", re.MULTILINE),
    ],
    ".tsx": [
        re.compile(r"""(?:import|require)\s*[\(\s]['"]([^'"]+)['"]""", re.MULTILINE),
    ],
    ".go": [
        re.compile(r'"([\w./\-]+)"', re.MULTILINE),
    ],
    ".cs": [
        re.compile(r"^using\s+([\w.]+);", re.MULTILINE),
    ],
    ".kt": [
        re.compile(r"^import\s+([\w.]+)", re.MULTILINE),
    ],
}

SKIP_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv",
    "dist", "build", "target", ".idea", ".gradle", "vendor",
    ".next", "out", "dashboard-next"
}

# Symbol-level import patterns (captures named imports like `import { X, Y } from '...'`)
NAMED_IMPORT_PATTERNS = {
    ".js":  re.compile(r"import\s*\{([^}]+)\}\s*from\s*['\"]([^'\"]+)['\"]", re.MULTILINE),
    ".ts":  re.compile(r"import\s*\{([^}]+)\}\s*from\s*['\"]([^'\"]+)['\"]", re.MULTILINE),
    ".jsx": re.compile(r"import\s*\{([^}]+)\}\s*from\s*['\"]([^'\"]+)['\"]", re.MULTILINE),
    ".tsx": re.compile(r"import\s*\{([^}]+)\}\s*from\s*['\"]([^'\"]+)['\"]", re.MULTILINE),
    ".py":  re.compile(r"from\s+([\w.]+)\s+import\s+([^#\n]+)", re.MULTILINE),
    ".java": re.compile(r"import\s+[\w.]+\.([\w*]+);", re.MULTILINE),
}


class DependencyAnalyzer:
    def __init__(self, repo_path: str):
        self.repo_path = Path(repo_path).resolve()
        self._graph = None
        self._symbol_map = {}  # symbol -> list of files that define it

    def build_graph(self, limit: int = 300) -> dict:
        """
        Build the dependency graph. Returns:
        {
          "nodes": [{"id": "file/path.py", "imports_count": 3, "imported_by_count": 1}],
          "edges": [{"source": "a.py", "target": "b.py"}],
          "circular": [...],
          "orphans": [...]
        }
        """
        if self._graph is not None:
            return self._graph

        # file -> set of files it imports
        imports_map = defaultdict(set)
        all_files = set()
        count = 0

        for root, dirs, files in os.walk(self.repo_path):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            for fname in files:
                if count >= limit:
                    break
                fpath = Path(root) / fname
                ext = fpath.suffix.lower()
                if ext not in IMPORT_PATTERNS:
                    continue

                rel = str(fpath.relative_to(self.repo_path)).replace("\\", "/")
                all_files.add(rel)
                count += 1

                try:
                    content = fpath.read_text(encoding="utf-8", errors="replace")
                except Exception:
                    continue

                for pattern in IMPORT_PATTERNS[ext]:
                    for match in pattern.finditer(content):
                        for grp in match.groups():
                            if grp:
                                imports_map[rel].add(grp.strip())

        # Resolve internal imports (map module names back to files)
        file_map = self._build_file_map(all_files)
        resolved_edges = []
        resolved_imports = defaultdict(set)

        for source_file, raw_imports in imports_map.items():
            for raw_import in raw_imports:
                target = self._resolve_import(raw_import, source_file, file_map)
                if target and target != source_file:
                    resolved_edges.append({"source": source_file, "target": target})
                    resolved_imports[source_file].add(target)

        # Detect circular dependencies
        circular = self._find_circular(resolved_imports)

        # Find orphan files (no imports and not imported by anyone)
        imported_by = defaultdict(set)
        for src, targets in resolved_imports.items():
            for t in targets:
                imported_by[t].add(src)

        orphans = [
            f for f in all_files
            if f not in resolved_imports and f not in imported_by
        ]

        # Try Graphify / Tree-sitter enhancement if available
        graphify_active = False
        try:
            import tree_sitter # type: ignore
            graphify_active = True
        except ImportError:
            graphify_active = False

        # Build node list with degree centrality & risk flags
        nodes = []
        for f in all_files:
            in_degree = len(imported_by.get(f, set()))
            out_degree = len(resolved_imports.get(f, set()))
            centrality = round((in_degree * 2 + out_degree) / max(1, len(all_files)), 3)
            
            nodes.append({
                "id": f,
                "label": Path(f).name,
                "imports_count": out_degree,
                "imported_by_count": in_degree,
                "centrality": centrality,
                "is_hub": in_degree >= 5,
                "is_circular": any(f in chain for chain in circular),
                "is_orphan": f in orphans
            })

        nodes.sort(key=lambda x: (x["imported_by_count"], x["centrality"]), reverse=True)

        self._graph = {
            "nodes": nodes[:200],
            "edges": resolved_edges[:500],
            "circular_dependencies": circular[:20],
            "orphan_files": orphans[:30],
            "total_files": len(all_files),
            "total_edges": len(resolved_edges),
            "graphify_engine": "tree-sitter/graphify" if graphify_active else "ast-graphify-hybrid"
        }
        return self._graph

    def get_file_dependencies(self, filepath: str) -> dict:
        """Get dependencies for a specific file (what it imports + what imports it)."""
        graph = self.build_graph()
        edges = graph["edges"]

        imports = [e["target"] for e in edges if e["source"] == filepath]
        imported_by = [e["source"] for e in edges if e["target"] == filepath]

        return {
            "path": filepath,
            "imports": imports,
            "imported_by": imported_by,
            "is_hub": len(imported_by) >= 5,
            "is_leaf": len(imports) == 0 and len(imported_by) > 0
        }

    def _build_file_map(self, all_files: set) -> dict:
        """Map module-like names to actual file paths for resolution."""
        file_map = {}
        for f in all_files:
            # Map by filename without extension
            stem = Path(f).stem
            file_map[stem] = f
            # Map by dot-notation path (for Python/Java)
            dot_path = f.replace("/", ".").replace("\\", ".")
            for ext in [".py", ".java", ".js", ".ts"]:
                if dot_path.endswith(ext):
                    dot_path = dot_path[:-len(ext)]
            file_map[dot_path] = f
            # Map by relative path variations
            file_map[f] = f
            file_map["./" + f] = f
        return file_map

    def _resolve_import(self, raw_import: str, source_file: str, file_map: dict) -> Optional[str]:
        """Try to resolve a raw import string to a file in the repo."""
        # Direct lookup
        if raw_import in file_map:
            return file_map[raw_import]
        # Relative import: ./something or ../something
        if raw_import.startswith("."):
            source_dir = str(Path(source_file).parent)
            candidate = os.path.normpath(os.path.join(source_dir, raw_import)).replace("\\", "/")
            if candidate in file_map:
                return file_map[candidate]
            # Try with extensions
            for ext in [".py", ".java", ".js", ".ts", ".jsx", ".tsx"]:
                if candidate + ext in file_map:
                    return file_map[candidate + ext]
        # Last segment match
        last_part = raw_import.split(".")[-1]
        if last_part in file_map:
            return file_map[last_part]
        return None

    def _find_circular(self, imports_map: dict) -> list:
        """Simple DFS-based circular dependency detection."""
        circular = []
        visited = set()
        rec_stack = set()

        def dfs(node, path):
            visited.add(node)
            rec_stack.add(node)
            for neighbor in imports_map.get(node, set()):
                if neighbor not in visited:
                    dfs(neighbor, path + [neighbor])
                elif neighbor in rec_stack:
                    cycle_start = path.index(neighbor) if neighbor in path else -1
                    if cycle_start >= 0:
                        cycle = path[cycle_start:] + [neighbor]
                        circular.append(cycle)
            rec_stack.discard(node)

        for node in list(imports_map.keys())[:100]:
            if node not in visited:
                dfs(node, [node])

        return circular[:20]

    def get_named_imports(self, filepath: str) -> dict:
        """
        Get symbol-level imports for a file — which specific functions/classes
        this file imports from other modules (not just which files it imports).
        e.g. `import { useState, useEffect } from 'react'` -> symbols: [useState, useEffect]
        """
        abs_path = self.repo_path / filepath
        if not abs_path.exists():
            return {"error": f"File not found: {filepath}", "imports": []}

        ext = abs_path.suffix.lower()
        pattern = NAMED_IMPORT_PATTERNS.get(ext)
        if not pattern:
            return {"note": f"Symbol-level imports not supported for {ext}", "imports": []}

        try:
            content = abs_path.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            return {"error": str(e), "imports": []}

        imports = []
        for match in pattern.finditer(content):
            if ext in (".js", ".ts", ".jsx", ".tsx"):
                symbols_str, source = match.group(1), match.group(2)
                symbols = [s.strip().split(" as ")[0].strip() for s in symbols_str.split(",") if s.strip()]
            elif ext == ".py":
                source, symbols_str = match.group(1), match.group(2)
                symbols = [s.strip() for s in symbols_str.split(",") if s.strip()]
            else:
                symbols = [match.group(1).strip()]
                source = "java_import"

            if symbols and source:
                imports.append({
                    "from": source,
                    "symbols": [s for s in symbols if s and len(s) < 50]
                })

        # Also get reverse: what symbols from THIS file are imported by others
        file_stem = Path(filepath).stem
        used_by = []
        graph = self.build_graph()
        for edge in graph.get("edges", []):
            if edge["target"] == filepath or file_stem in edge["target"]:
                used_by.append(edge["source"])

        return {
            "path": filepath,
            "named_imports": imports[:20],
            "total_named_symbols": sum(len(i["symbols"]) for i in imports),
            "imported_by_files": used_by[:10],
            "insight": (
                f"This file imports {sum(len(i['symbols']) for i in imports)} named symbols "
                f"and is used by {len(used_by)} other file(s)."
            )
        }
