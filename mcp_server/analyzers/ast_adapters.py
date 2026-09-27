"""
CopilotLens - Multi-Language AST Adapters
===========================================
AST-based code analysis adapters for Python, JavaScript, TypeScript, and Java.
Uses Tree-sitter for AST parsing with fallback regex/AST parsers for maximum resilience.
"""

import os
import re
import ast
from pathlib import Path
from typing import Dict, List, Any, Optional

# Attempt to import tree_sitter & language packs
HAS_TREE_SITTER = False
try:
    import tree_sitter
    import tree_sitter_python
    import tree_sitter_javascript
    import tree_sitter_typescript
    import tree_sitter_java

    _PY_LANG = tree_sitter.Language(tree_sitter_python.language())
    _JS_LANG = tree_sitter.Language(tree_sitter_javascript.language())
    _TS_LANG = tree_sitter.Language(tree_sitter_typescript.language_typescript())
    _JAVA_LANG = tree_sitter.Language(tree_sitter_java.language())

    HAS_TREE_SITTER = True
except Exception:
    HAS_TREE_SITTER = False


class BaseASTAdapter:
    """Base class for language-specific AST adapters."""

    def __init__(self, language_id: str):
        self.language_id = language_id

    def extract_symbols(self, code: str, file_path: str = "") -> List[Dict[str, Any]]:
        """Extract function, class, and method definitions."""
        raise NotImplementedError

    def extract_imports(self, code: str, file_path: str = "") -> List[Dict[str, Any]]:
        """Extract module imports and named symbols."""
        raise NotImplementedError

    def extract_calls(self, code: str, file_path: str = "") -> List[Dict[str, Any]]:
        """Extract function and method calls."""
        raise NotImplementedError

    def find_changed_symbols(self, code: str, line_ranges: List[tuple]) -> List[Dict[str, Any]]:
        """Find which AST symbols overlap with modified line ranges."""
        symbols = self.extract_symbols(code)
        changed = []
        for sym in symbols:
            start = sym.get("start_line", 1)
            end = sym.get("end_line", start)
            for r_start, r_end in line_ranges:
                if not (end < r_start or start > r_end):
                    sym["changed_lines_overlap"] = [max(start, r_start), min(end, r_end)]
                    changed.append(sym)
                    break
        return changed


class PythonASTAdapter(BaseASTAdapter):
    """Python AST Adapter with Tree-sitter & native `ast` fallback."""

    def __init__(self):
        super().__init__("python")

    def extract_symbols(self, code: str, file_path: str = "") -> List[Dict[str, Any]]:
        if HAS_TREE_SITTER:
            try:
                parser = tree_sitter.Parser(_PY_LANG)
                tree = parser.parse(code.encode("utf-8"))
                return self._symbols_from_tree(tree.root_node, code)
            except Exception:
                pass
        return self._symbols_fallback(code)

    def _symbols_from_tree(self, root_node, code: str) -> List[Dict[str, Any]]:
        symbols = []
        lines = code.splitlines()

        def walk(node, parent_class=None):
            if node.type in ("function_definition", "class_definition"):
                name_node = node.child_by_field_name("name")
                name = name_node.text.decode("utf-8") if name_node else "anonymous"
                kind = "class" if node.type == "class_definition" else ("method" if parent_class else "function")
                start_line = node.start_point[0] + 1
                end_line = node.end_point[0] + 1

                # Visibility check
                is_private = name.startswith("_") and not (name.startswith("__") and name.endswith("__"))
                is_dunder = name.startswith("__") and name.endswith("__")

                # Docstring check
                docstring = None
                body = node.child_by_field_name("body")
                if body and body.children:
                    first = body.children[0]
                    if first.type == "expression_statement":
                        docstring = first.text.decode("utf-8").strip("\"' \n")

                symbols.append({
                    "name": name,
                    "kind": kind,
                    "parent_class": parent_class,
                    "start_line": start_line,
                    "end_line": end_line,
                    "visibility": "private" if is_private else ("special" if is_dunder else "public"),
                    "docstring": docstring[:100] if docstring else None
                })

                new_parent = name if node.type == "class_definition" else parent_class
                for child in node.children:
                    walk(child, new_parent)
            else:
                for child in node.children:
                    walk(child, parent_class)

        walk(root_node)
        return symbols

    def _symbols_fallback(self, code: str) -> List[Dict[str, Any]]:
        symbols = []
        try:
            tree = ast.parse(code)
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    kind = "class" if isinstance(node, ast.ClassDef) else "function"
                    is_private = node.name.startswith("_") and not (node.name.startswith("__") and node.name.endswith("__"))
                    symbols.append({
                        "name": node.name,
                        "kind": kind,
                        "start_line": node.lineno,
                        "end_line": getattr(node, "end_lineno", node.lineno),
                        "visibility": "private" if is_private else "public",
                        "docstring": ast.get_docstring(node)
                    })
        except Exception:
            # Basic Regex fallback
            for match in re.finditer(r"^(?:def|class)\s+([A-Za-z_][A-Za-z0-9_]*)", code, re.M):
                name = match.group(1)
                line = code[:match.start()].count("\n") + 1
                kind = "class" if "class " in match.group() else "function"
                symbols.append({
                    "name": name,
                    "kind": kind,
                    "start_line": line,
                    "end_line": line,
                    "visibility": "private" if name.startswith("_") else "public",
                    "docstring": None
                })
        return symbols

    def extract_imports(self, code: str, file_path: str = "") -> List[Dict[str, Any]]:
        imports = []
        try:
            tree = ast.parse(code)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        imports.append({"module": alias.name, "symbol": alias.asname or alias.name, "line": node.lineno})
                elif isinstance(node, ast.ImportFrom):
                    mod = node.module or ""
                    for alias in node.names:
                        imports.append({"module": mod, "symbol": alias.name, "as_name": alias.asname, "line": node.lineno})
        except Exception:
            for match in re.finditer(r"^\s*(?:from\s+([\w\.]+)\s+)?import\s+([^\n]+)", code, re.M):
                mod = match.group(1) or ""
                syms = match.group(2).strip()
                line = code[:match.start()].count("\n") + 1
                imports.append({"module": mod, "symbol": syms, "line": line})
        return imports

    def extract_calls(self, code: str, file_path: str = "") -> List[Dict[str, Any]]:
        calls = []
        try:
            tree = ast.parse(code)
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    func_name = ""
                    if isinstance(node.func, ast.Name):
                        func_name = node.func.id
                    elif isinstance(node.func, ast.Attribute):
                        func_name = node.func.attr
                    if func_name:
                        calls.append({"name": func_name, "line": node.lineno})
        except Exception:
            for match in re.finditer(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\(", code):
                name = match.group(1)
                if name not in ("def", "class", "if", "while", "for", "with", "return"):
                    line = code[:match.start()].count("\n") + 1
                    calls.append({"name": name, "line": line})
        return calls


class JavaScriptASTAdapter(BaseASTAdapter):
    """JavaScript AST Adapter (JS/JSX) with Tree-sitter & regex fallback."""

    def __init__(self, is_jsx: bool = False):
        super().__init__("jsx" if is_jsx else "javascript")

    def extract_symbols(self, code: str, file_path: str = "") -> List[Dict[str, Any]]:
        if HAS_TREE_SITTER:
            try:
                parser = tree_sitter.Parser(_JS_LANG)
                tree = parser.parse(code.encode("utf-8"))
                return self._symbols_from_tree(tree.root_node, code)
            except Exception:
                pass
        return self._symbols_regex(code)

    def _symbols_from_tree(self, root_node, code: str) -> List[Dict[str, Any]]:
        symbols = []

        def walk(node, parent_class=None):
            if node.type in ("function_declaration", "class_declaration", "method_definition", "arrow_function"):
                name = "anonymous"
                name_node = node.child_by_field_name("name")
                if name_node:
                    name = name_node.text.decode("utf-8")
                elif node.parent and node.parent.type == "variable_declarator":
                    id_node = node.parent.child_by_field_name("name")
                    if id_node:
                        name = id_node.text.decode("utf-8")

                if name != "anonymous":
                    start_line = node.start_point[0] + 1
                    end_line = node.end_point[0] + 1
                    kind = "class" if node.type == "class_declaration" else ("method" if parent_class or node.type == "method_definition" else "function")
                    is_exported = False
                    if node.parent and node.parent.type in ("export_statement", "export_default_declaration"):
                        is_exported = True

                    symbols.append({
                        "name": name,
                        "kind": kind,
                        "parent_class": parent_class,
                        "start_line": start_line,
                        "end_line": end_line,
                        "visibility": "public" if (is_exported or not name.startswith("_")) else "private",
                        "is_exported": is_exported
                    })

                new_parent = name if node.type == "class_declaration" else parent_class
                for child in node.children:
                    walk(child, new_parent)
            else:
                for child in node.children:
                    walk(child, parent_class)

        walk(root_node)
        return symbols

    def _symbols_regex(self, code: str) -> List[Dict[str, Any]]:
        symbols = []
        patterns = [
            (r"(?:export\s+)?function\s+([A-Za-z_][A-Za-z0-9_]*)", "function"),
            (r"(?:export\s+)?class\s+([A-Za-z_][A-Za-z0-9_]*)", "class"),
            (r"(?:export\s+)?(?:const|let|var)\s+([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(?:async\s+)?(?:\([^)]*\)|[A-Za-z_][A-Za-z0-9_]*)\s*=>", "function"),
        ]
        for pat, kind in patterns:
            for match in re.finditer(pat, code):
                name = match.group(1)
                line = code[:match.start()].count("\n") + 1
                is_exported = "export" in match.group()
                symbols.append({
                    "name": name,
                    "kind": kind,
                    "start_line": line,
                    "end_line": line,
                    "visibility": "public" if is_exported else "private",
                    "is_exported": is_exported
                })
        return symbols

    def extract_imports(self, code: str, file_path: str = "") -> List[Dict[str, Any]]:
        imports = []
        # ES6 imports & CommonJS require
        for match in re.finditer(r"import\s+(?:\{([^}]+)\}|(\w+))\s+from\s+['\"]([^'\"]+)['\"]", code):
            named = match.group(1)
            default_sym = match.group(2)
            mod = match.group(3)
            line = code[:match.start()].count("\n") + 1
            if named:
                for s in named.split(","):
                    s = s.strip()
                    if s:
                        imports.append({"module": mod, "symbol": s.split(" as ")[0].strip(), "line": line})
            if default_sym:
                imports.append({"module": mod, "symbol": default_sym, "line": line})

        for match in re.finditer(r"(?:const|let|var)\s+(?:\{([^}]+)\}|(\w+))\s*=\s*require\(['\"]([^'\"]+)['\"]\)", code):
            named = match.group(1)
            default_sym = match.group(2)
            mod = match.group(3)
            line = code[:match.start()].count("\n") + 1
            if named:
                for s in named.split(","):
                    s = s.strip()
                    if s:
                        imports.append({"module": mod, "symbol": s.split(":")[0].strip(), "line": line})
            if default_sym:
                imports.append({"module": mod, "symbol": default_sym, "line": line})
        return imports

    def extract_calls(self, code: str, file_path: str = "") -> List[Dict[str, Any]]:
        calls = []
        for match in re.finditer(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\(", code):
            name = match.group(1)
            if name not in ("function", "class", "if", "while", "for", "switch", "return", "catch"):
                line = code[:match.start()].count("\n") + 1
                calls.append({"name": name, "line": line})
        return calls


class TypeScriptASTAdapter(JavaScriptASTAdapter):
    """TypeScript AST Adapter (TS/TSX) extending JavaScript Adapter."""

    def __init__(self, is_tsx: bool = False):
        super().__init__(is_jsx=is_tsx)
        self.language_id = "tsx" if is_tsx else "typescript"

    def extract_symbols(self, code: str, file_path: str = "") -> List[Dict[str, Any]]:
        if HAS_TREE_SITTER:
            try:
                parser = tree_sitter.Parser(_TS_LANG)
                tree = parser.parse(code.encode("utf-8"))
                return self._symbols_from_tree(tree.root_node, code)
            except Exception:
                pass
        return super().extract_symbols(code, file_path)


class JavaASTAdapter(BaseASTAdapter):
    """Java AST Adapter with Tree-sitter & regex fallback."""

    def __init__(self):
        super().__init__("java")

    def extract_symbols(self, code: str, file_path: str = "") -> List[Dict[str, Any]]:
        if HAS_TREE_SITTER:
            try:
                parser = tree_sitter.Parser(_JAVA_LANG)
                tree = parser.parse(code.encode("utf-8"))
                return self._symbols_from_tree(tree.root_node, code)
            except Exception:
                pass
        return self._symbols_regex(code)

    def _symbols_from_tree(self, root_node, code: str) -> List[Dict[str, Any]]:
        symbols = []

        def walk(node, parent_class=None):
            if node.type in ("class_declaration", "interface_declaration", "enum_declaration", "method_declaration"):
                name_node = node.child_by_field_name("name")
                name = name_node.text.decode("utf-8") if name_node else "anonymous"
                kind = "class" if "class" in node.type or "interface" in node.type or "enum" in node.type else "method"
                start_line = node.start_point[0] + 1
                end_line = node.end_point[0] + 1

                # Check modifiers for visibility
                is_private = False
                is_public = False
                for child in node.children:
                    if child.type == "modifiers":
                        mod_text = child.text.decode("utf-8")
                        if "private" in mod_text:
                            is_private = True
                        if "public" in mod_text:
                            is_public = True

                symbols.append({
                    "name": name,
                    "kind": kind,
                    "parent_class": parent_class,
                    "start_line": start_line,
                    "end_line": end_line,
                    "visibility": "private" if is_private else ("public" if is_public else "package-private"),
                    "is_exported": is_public
                })

                new_parent = name if kind == "class" else parent_class
                for child in node.children:
                    walk(child, new_parent)
            else:
                for child in node.children:
                    walk(child, parent_class)

        walk(root_node)
        return symbols

    def _symbols_regex(self, code: str) -> List[Dict[str, Any]]:
        symbols = []
        # Class pattern
        for match in re.finditer(r"(?:public|protected|private)?\s*(?:static\s+)?(?:final\s+)?(?:class|interface|enum)\s+([A-Za-z_][A-Za-z0-9_]*)", code):
            name = match.group(1)
            line = code[:match.start()].count("\n") + 1
            is_pub = "public" in match.group()
            is_priv = "private" in match.group()
            symbols.append({
                "name": name,
                "kind": "class",
                "start_line": line,
                "end_line": line,
                "visibility": "private" if is_priv else ("public" if is_pub else "package-private"),
                "is_exported": is_pub
            })
        # Method pattern
        for match in re.finditer(r"(?:public|protected|private)?\s*(?:static\s+)?(?:final\s+)?[\w<>,\[\]\s]+\s+([A-Za-z_][A-Za-z0-9_]*)\s*\([^)]*\)\s*\{", code):
            name = match.group(1)
            if name not in ("if", "while", "for", "switch", "catch", "synchronized"):
                line = code[:match.start()].count("\n") + 1
                is_pub = "public" in match.group()
                is_priv = "private" in match.group()
                symbols.append({
                    "name": name,
                    "kind": "method",
                    "start_line": line,
                    "end_line": line,
                    "visibility": "private" if is_priv else ("public" if is_pub else "package-private"),
                    "is_exported": is_pub
                })
        return symbols

    def extract_imports(self, code: str, file_path: str = "") -> List[Dict[str, Any]]:
        imports = []
        for match in re.finditer(r"import\s+(?:static\s+)?([\w\.]+);", code):
            full_imp = match.group(1)
            line = code[:match.start()].count("\n") + 1
            mod_parts = full_imp.split(".")
            sym = mod_parts[-1]
            mod = ".".join(mod_parts[:-1])
            imports.append({"module": mod, "symbol": sym, "full_import": full_imp, "line": line})
        return imports

    def extract_calls(self, code: str, file_path: str = "") -> List[Dict[str, Any]]:
        calls = []
        for match in re.finditer(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\(", code):
            name = match.group(1)
            if name not in ("if", "while", "for", "switch", "catch", "super", "this", "new"):
                line = code[:match.start()].count("\n") + 1
                calls.append({"name": name, "line": line})
        return calls


class ASTManager:
    """Unified AST Manager to select and execute language adapters."""

    def __init__(self):
        self.adapters = {
            ".py": PythonASTAdapter(),
            ".js": JavaScriptASTAdapter(is_jsx=False),
            ".jsx": JavaScriptASTAdapter(is_jsx=True),
            ".ts": TypeScriptASTAdapter(is_tsx=False),
            ".tsx": TypeScriptASTAdapter(is_tsx=True),
            ".java": JavaASTAdapter()
        }

    def get_adapter(self, file_path: str) -> Optional[BaseASTAdapter]:
        ext = Path(file_path).suffix.lower()
        return self.adapters.get(ext)

    def analyze_file(self, file_path: str, code: str) -> Dict[str, Any]:
        adapter = self.get_adapter(file_path)
        if not adapter:
            return {
                "supported": False,
                "has_tree_sitter": HAS_TREE_SITTER,
                "symbols": [],
                "imports": [],
                "calls": []
            }

        return {
            "supported": True,
            "language": adapter.language_id,
            "has_tree_sitter": HAS_TREE_SITTER,
            "symbols": adapter.extract_symbols(code, file_path),
            "imports": adapter.extract_imports(code, file_path),
            "calls": adapter.extract_calls(code, file_path)
        }
