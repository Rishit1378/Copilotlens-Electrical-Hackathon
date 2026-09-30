"""
CopilotLens Capital Logic Action Generator
==========================================

Produces a reviewable *Logic Action Change Set* rather than a lone Java class:

    Action implementation + ActionUI + LogicController registration (+ derivative controllers)
    + LogicResource menu/toolbar/init registration + resource bundle entries (+ localisation report)
    + ribbon.xml button + ribbon resource keys + icon verification + JUnit 3 test scaffold
    + validation report

Workflow
--------
1. ``plan(spec)``               - validates the spec against the Capital repo and returns a question for every
                                  undecided product/domain decision (never guessed), plus the options discovered
                                  in the repo (sibling actions, menus, toolbars, ribbon groups, controllers...).
2. ``generate_changeset(spec)`` - builds every created/modified file in memory, validates it and stores it as a
                                  change set (unified diffs). Nothing is written to the Capital repo.
3. ``apply_changeset(id)``      - writes the files (refusing if any target changed since generation, rolling back
                                  on failure) and optionally runs the configured build/test commands.

The Capital repo root is taken from ``spec.capital_repo``, then ``$CAPITAL_REPO``, then the server repo path.
File locations can be overridden with ``spec.layout`` (see ``DEFAULT_LAYOUT``).
Build/test commands come from ``$CAPITAL_BUILD_CMD`` / ``$CAPITAL_TEST_CMD`` ({test_class}, {test_fqn} placeholders).
"""

import difflib
import hashlib
import json
import keyword
import logging
import os
import re
import subprocess
import time
import uuid
import xml.etree.ElementTree as ET
import xml.parsers.expat
from collections import Counter, defaultdict
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from xml.sax.saxutils import quoteattr

logger = logging.getLogger(__name__)

# ─── Constants ────────────────────────────────────────────────────────────────

DEFAULT_LAYOUT: Dict[str, Any] = {
    "logic_src": "clogic_src/src/capitallogic/src",
    "logic_tests": "clogic_src/src/capitallogic/tests/src",
    "controller": "clogic_src/src/capitallogic/src/chs/caplets/logic/LogicController.java",
    "controller_method": "createLogicControllerActions",
    "resource": "clogic_src/src/capitallogic/src/chs/caplets/logic/LogicResource.java",
    "resources_root": "interfaces_src/src/resources/src",
    "ribbon": "interfaces_src/src/resources/src/com/mentor/capital/javafx/ribbon/ribbon.xml",
    "bundle": None,          # auto-discovered <bundle_name>.properties nearest to the action package
    "bundle_name": "chsresources",
    "ribbon_bundle": None,   # auto-discovered properties file containing ribbon.button.* keys
    "icon_roots": ["interfaces_src/src/resources/src", "clogic_src/src/capitallogic/src"],
}
MAX_SCAN_FILES = 8000
MAX_ICON_FILES = 60000
IMAGE_EXTS = (".png", ".gif", ".svg", ".jpg", ".jpeg", ".ico")

ACTION_TYPES: Dict[str, Dict[str, Any]] = {
    "ControllerActionRT": {"base_class": "ControllerActionRT", "dependency": "ICapletController",
                           "param": "controller", "controller_scoped": True},
    "AppAction": {"base_class": "AppAction", "dependency": "IFIB", "param": "fib", "controller_scoped": False},
    "ViewActionRT": {"base_class": "ViewActionRT", "dependency": "ICapletView", "param": "view",
                     "controller_scoped": False},
    # Interactive actions use several framework base classes: base_class or sibling_action is mandatory.
    "interactive": {"base_class": None, "dependency": None, "param": None, "controller_scoped": True},
}
SELECTION_RULES = ["none", "single", "multiple", "any"]
LOCALIZATION_POLICIES = ["report", "placeholder"]
ENTRY_METHODS = ["actionPerformed", "onActivate", "execute", "doAction", "run"]
NON_LIFECYCLE = {"getActionUIClass", "isEnabled", "toString", "equals", "hashCode", "getActionClass"}
INTERACTIVE_HINTS = {"onActivate", "onTerminate", "onCancel", "onPoint", "mousePressed", "mouseMoved"}

STANDARD_TEST_SCENARIOS = [
    "Action is enabled with valid Logic context",
    "Action is disabled with no active design",
    "Action is disabled for invalid selection",
    "Action handles an empty selection",
    "Action performs the expected operation",
    "Action does not mutate the model when disabled",
    "Correct application and feature visibility",
    "Correct UI to action class mapping",
]
MUTATION_TEST_SCENARIOS = ["Undo and redo restore the model"]
INTERACTIVE_TEST_SCENARIOS = [
    "Activation result", "Point and mouse input", "Termination", "Cancellation",
    "Cleanup of temporary graphics", "Cursor and shortcut behavior",
]

# JDK types we may reference. Capital types are only ever resolved from imports found in the repo.
JDK_TYPES = {
    "ActionEvent": "java.awt.event.ActionEvent",
    "KeyStroke": "javax.swing.KeyStroke",
    "SwingUtilities": "javax.swing.SwingUtilities",
    "Level": "java.util.logging.Level",
}
JAVA_LANG = {"String", "Object", "RuntimeException", "Exception", "Override", "Class", "Integer",
             "Boolean", "Character", "Throwable", "IllegalStateException", "Void"}

_JAVA_IDENT = re.compile(r"^[A-Za-z_$][A-Za-z0-9_$]*$")
_JAVA_PACKAGE = re.compile(r"^[a-z_]\w*(\.[a-z_]\w*)*$")


# ─── Text / Java helpers ──────────────────────────────────────────────────────

def _read(path: Path, encoding: Optional[str] = None) -> Tuple[str, str]:
    """Lossless read (no newline translation). Returns (text, encoding)."""
    raw = path.read_bytes()
    if encoding:
        return raw.decode(encoding), encoding
    try:
        return raw.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        return raw.decode("latin-1"), "latin-1"


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _nl(text: str) -> str:
    return "\r\n" if "\r\n" in text else "\n"


def _line_start(text: str, idx: int) -> int:
    return text.rfind("\n", 0, idx) + 1


def _line_end(text: str, idx: int) -> int:
    j = text.find("\n", idx)
    return len(text) if j < 0 else j + 1


def _indent_at(text: str, idx: int) -> str:
    return re.match(r"[ \t]*", text[_line_start(text, idx):]).group(0)


def _strip_code(text: str) -> str:
    """Blank out comments and string/char literals, keeping offsets stable."""
    return re.sub(r'//[^\n]*|/\*.*?\*/|"(?:\\.|[^"\\\n])*"|\'(?:\\.|[^\'\\\n])*\'',
                  lambda m: re.sub(r"[^\n]", " ", m.group(0)), text, flags=re.S)


def _match_brace(text: str, open_idx: int) -> int:
    clean = _strip_code(text)
    depth = 0
    for i in range(open_idx, len(clean)):
        if clean[i] == "{":
            depth += 1
        elif clean[i] == "}":
            depth -= 1
            if depth == 0:
                return i
    return -1


def _find_method_body(text: str, name: str) -> Optional[Tuple[int, int]]:
    """(index after '{', index of matching '}') of the first declaration of `name`."""
    clean = _strip_code(text)
    m = re.search(r"\b" + re.escape(name) + r"\s*\((?:[^()]|\([^()]*\))*\)\s*(?:throws\s+[\w.,\s]+)?\{", clean)
    if not m:
        return None
    close = _match_brace(text, m.end() - 1)
    return (m.end(), close) if close > 0 else None


def _enclosing_condition(text: str, body_start: int, pos: int) -> Optional[str]:
    seg = _strip_code(text[body_start:pos])
    if seg.count("{") - seg.count("}") <= 0:
        return None
    conds = list(re.finditer(r"\bif\s*\((.*?)\)\s*\{", text[body_start:pos], re.S))
    return " ".join(conds[-1].group(1).split()) if conds else "<nested block>"


def _package_of(text: str) -> Optional[str]:
    m = re.search(r"^\s*package\s+([\w.]+)\s*;", text, re.M)
    return m.group(1) if m else None


def _class_decl(text: str) -> Tuple[Optional[str], Optional[str]]:
    clean = _strip_code(text)
    m = re.search(r"\bclass\s+(\w+)(?:\s*<[^{]*?>)?\s+extends\s+([\w.]+)", clean)
    if m:
        return m.group(1), m.group(2).split(".")[-1]
    m = re.search(r"\bclass\s+(\w+)", clean)
    return (m.group(1) if m else None), None


def _extract_imports(text: str) -> Dict[str, str]:
    return {m.group(2): f"{m.group(1)}.{m.group(2)}"
            for m in re.finditer(r"^\s*import\s+([\w.]+)\.(\w+)\s*;", text, re.M)}


_OVERRIDE = re.compile(
    r"@Override\s+(?:@\w+\s+)*((?:public|protected)\s+(?:final\s+)?([\w<>\[\]?,.\s]+?)\s+(\w+)\s*"
    r"\(((?:[^()]|\([^()]*\))*)\)\s*(?:throws\s+[\w.,\s]+?)?)\s*\{")


def _extract_overrides(text: str) -> Dict[str, Dict[str, str]]:
    out: Dict[str, Dict[str, str]] = {}
    for m in _OVERRIDE.finditer(text):
        out.setdefault(m.group(3), {"signature": " ".join(m.group(1).split()),
                                    "return_type": " ".join(m.group(2).split())})
    return out


def _ctor_params(text: str, cls: str) -> Optional[str]:
    m = re.search(r"\bpublic\s+" + re.escape(cls) + r"\s*\(([^)]*)\)", text)
    return " ".join(m.group(1).split()) if m else None


def _logger_decl(text: str, cls: str) -> Optional[Dict[str, str]]:
    m = re.search(r"^[ \t]*((?:private|protected|public)?\s*static\s+final\s+([\w.]+)\s+(\w+)\s*=\s*[^;]*?\b"
                  + re.escape(cls) + r"\b[^;]*;)", text, re.M)
    if not m or "log" not in m.group(2).lower():
        return None
    return {"declaration": " ".join(m.group(1).split()).replace(cls, "{cls}"),
            "type": m.group(2).split(".")[-1], "var": m.group(3)}


def _class_ref_in(text: str, method: str) -> Optional[str]:
    body = _find_method_body(text, method)
    if not body:
        return None
    m = re.search(r"\b(\w+)\.class\b", text[body[0]:body[1]])
    return m.group(1) if m else None


def _method_containing(text: str, needle: str) -> Optional[str]:
    idx = text.find(needle)
    if idx < 0:
        return None
    for m in re.finditer(r"\b(?:public|protected|private)\s+(?:final\s+)?void\s+(\w+)\s*\([^)]*\)\s*"
                         r"(?:throws[^{]*)?\{", text):
        close = _match_brace(text, m.end() - 1)
        if m.end() <= idx < close:
            return m.group(1)
    return None


def _default_return(return_type: str) -> Optional[str]:
    rt = return_type.strip()
    if rt == "void":
        return None
    if rt == "boolean":
        return "false"
    if rt in ("int", "long", "short", "byte", "double", "float"):
        return "0"
    return "null"


def _add_import(text: str, fqn: str) -> str:
    if re.search(r"^\s*import\s+" + re.escape(fqn) + r"\s*;", text, re.M):
        return text
    nl = _nl(text)
    imports = list(re.finditer(r"^import\s+(static\s+)?([\w.*]+)\s*;[ \t]*\r?$", text, re.M))
    if not imports:
        pkg = re.search(r"^package\s+[\w.]+\s*;[ \t]*\r?$", text, re.M)
        pos = _line_end(text, pkg.end()) if pkg else 0
        return text[:pos] + nl + f"import {fqn};" + nl + text[pos:]
    plain = [m for m in imports if not m.group(1)] or imports
    anchor = None
    for m in plain:
        if m.group(2) < fqn:
            anchor = m
    pos = _line_end(text, anchor.end()) if anchor else _line_start(text, plain[0].start())
    return text[:pos] + f"import {fqn};" + nl + text[pos:]


def _braces_balanced(text: str) -> bool:
    depth = 0
    for c in _strip_code(text):
        depth += (c == "{") - (c == "}")
        if depth < 0:
            return False
    return depth == 0


def _camel_words(name: str) -> List[str]:
    return re.findall(r"[A-Z]+(?=[A-Z][a-z]|\d|$)|[A-Z]?[a-z]+|\d+", name)


def _java_str(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


# Properties helpers (files are read/written as latin-1: lossless; new values are \\u-escaped).

def _prop_escape(value: str) -> str:
    out = []
    for i, ch in enumerate(value):
        if ch == "\\":
            out.append("\\\\")
        elif ch == "\n":
            out.append("\\n")
        elif ch == " " and i == 0:
            out.append("\\ ")
        elif ord(ch) > 126:
            out.append("\\u%04x" % ord(ch))
        else:
            out.append(ch)
    return "".join(out)


def _prop_keys(text: str) -> Dict[str, str]:
    keys: Dict[str, str] = {}
    continued = False
    for line in text.splitlines():
        stripped = line.strip()
        was_continued = continued
        continued = (len(stripped) - len(stripped.rstrip("\\"))) % 2 == 1
        if was_continued or not stripped or stripped[0] in "#!":
            continue
        m = re.match(r"((?:\\.|[^=:\s\\])+)\s*[=:\s]?\s*(.*)$", stripped)
        if m:
            keys[m.group(1)] = m.group(2)
    return keys


# ─── Specification ────────────────────────────────────────────────────────────

def _toggle(value: Any, key: str) -> Optional[Dict[str, Any]]:
    """Shorthand normalisation: False/'none' -> disabled, 'x' -> {enabled, key: 'x'}, dict -> enabled by default."""
    if value is None:
        return None
    if value is False or (isinstance(value, str) and value.strip().lower() in ("none", "no", "false", "")):
        return {"enabled": False}
    if value is True:
        return {"enabled": True}
    if isinstance(value, str):
        return {"enabled": True, key: value.strip()}
    if isinstance(value, dict):
        out = dict(value)
        out.setdefault("enabled", True)
        return out
    return None


@dataclass
class ActionSpec:
    """Everything that encodes a product/domain decision is required input; None means 'not answered yet'."""
    action_name: str
    package: str = "chs.caplets.logic.actions"
    action_type: Optional[str] = None
    base_class: Optional[str] = None
    sibling_action: Optional[str] = None
    purpose: Optional[str] = None
    target_object: Optional[str] = None
    selection_rule: Optional[str] = None
    mutates_model: Optional[bool] = None
    undo_required: Optional[bool] = None
    multi_user_safe: Optional[bool] = None
    long_running: bool = False
    ui_work: bool = False
    applications: Optional[List[str]] = None
    immersed_mode: Optional[str] = None
    immersed: Optional[Any] = None
    label: Optional[str] = None
    short_desc: Optional[str] = None
    long_desc: Optional[str] = None
    tooltip: Optional[str] = None
    mnemonic: Optional[str] = None
    accelerator: Optional[str] = None
    icon: Optional[str] = None
    icon_inactive: Optional[str] = None
    allow_missing_icons: bool = False
    menu: Optional[Any] = None
    toolbar: Optional[Any] = None
    init_in_init_actions: bool = False
    controller_registration: Optional[Any] = None
    derivative_controllers: Optional[List[str]] = None
    ribbon: Optional[Any] = None
    gating: Optional[Dict[str, Any]] = None
    localization: str = "report"
    test_scenarios: List[str] = field(default_factory=list)
    test_base: Optional[str] = None
    capital_repo: Optional[str] = None
    layout: Dict[str, Any] = field(default_factory=dict)
    unknown_fields: List[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ActionSpec":
        known = {f.name for f in fields(cls)} - {"unknown_fields"}
        spec = cls(**{k: v for k, v in data.items() if k in known})
        spec.unknown_fields = sorted(set(data) - known)
        spec._normalize()
        return spec

    def _normalize(self) -> None:
        name = (self.action_name or "").strip().replace(" ", "")
        if name and not name.endswith("Action"):
            name += "Action"
        self.action_name = name
        self.package = (self.package or "").strip()
        self.menu = _toggle(self.menu, "menu_var")
        self.toolbar = _toggle(self.toolbar, "toolbar_var")
        self.controller_registration = _toggle(self.controller_registration, "insert_after")
        self.ribbon = _toggle(self.ribbon, "group")
        self.immersed = _toggle(self.immersed, "action_id")
        if isinstance(self.applications, str):
            self.applications = [a.strip() for a in self.applications.split(",") if a.strip()]
        if self.ribbon and self.ribbon.get("enabled") and self.ribbon.get("group") and not self.ribbon.get("placements"):
            self.ribbon["placements"] = [{"group": self.ribbon.pop("group")}]
        if self.tooltip is None and self.short_desc:
            self.tooltip = self.short_desc
        if self.long_desc is None and self.short_desc:
            self.long_desc = self.short_desc
        if isinstance(self.mnemonic, str):
            self.mnemonic = self.mnemonic.strip()      # "" = answered: no mnemonic
        if isinstance(self.accelerator, str):
            self.accelerator = self.accelerator.strip()

    @property
    def ui_name(self) -> str:
        return f"{self.action_name}UI"

    @property
    def test_name(self) -> str:
        return f"{self.action_name}Test"

    @property
    def fqn(self) -> str:
        return f"{self.package}.{self.action_name}"

    @property
    def ui_fqn(self) -> str:
        return f"{self.package}.{self.ui_name}"

    @property
    def help_id(self) -> str:
        return self.fqn.replace(".", "_")

    @property
    def type_info(self) -> Dict[str, Any]:
        return ACTION_TYPES.get(self.action_type or "", {})

    @property
    def controller_scoped(self) -> bool:
        return bool(self.type_info.get("controller_scoped"))

    def enabled(self, section: str) -> bool:
        value = getattr(self, section)
        return bool(value and value.get("enabled"))

    def gating_items(self) -> Dict[str, Any]:
        return {k: v for k, v in (self.gating or {}).items() if v}

    def all_test_scenarios(self) -> List[str]:
        scenarios = list(STANDARD_TEST_SCENARIOS)
        if self.mutates_model:
            scenarios += MUTATION_TEST_SCENARIOS
        if self.action_type == "interactive":
            scenarios += INTERACTIVE_TEST_SCENARIOS
        if self.enabled("ribbon"):
            scenarios.append("Ribbon keys resolve in the ribbon bundle")
        for s in self.test_scenarios or []:
            if s not in scenarios:
                scenarios.append(s)
        return scenarios

    def validate(self, index: "LogicRepoIndex") -> Tuple[List[str], List[Dict[str, Any]]]:
        """Return (errors, questions). Every missing product decision becomes a question."""
        errors: List[str] = []
        questions: List[Dict[str, Any]] = []

        def ask(qid: str, text: str, options: Optional[List[str]] = None, blocking: bool = True) -> None:
            questions.append({"id": qid, "question": text, "options": list(options or []), "blocking": blocking})

        if not _JAVA_IDENT.match(self.action_name or "") or keyword.iskeyword(self.action_name or ""):
            errors.append(f"Invalid Java class name: {self.action_name!r}")
        if not _JAVA_PACKAGE.match(self.package or ""):
            errors.append(f"Invalid Java package: {self.package!r}")
        if self.unknown_fields:
            errors.append(f"Unknown spec fields (typo?): {', '.join(self.unknown_fields)}")
        if self.localization not in LOCALIZATION_POLICIES:
            errors.append(f"localization must be one of {LOCALIZATION_POLICIES}")

        if self.action_type is None:
            ask("action_type", "Which action type?", list(ACTION_TYPES))
        elif self.action_type not in ACTION_TYPES:
            errors.append(f"Unknown action_type {self.action_type!r}; expected one of {list(ACTION_TYPES)}")
        elif self.action_type == "interactive" and not (self.base_class or self.sibling_action):
            ask("base_class", "Interactive action: which framework base class, or which sibling_action should "
                "the interactive lifecycle be copied from?", index.interactive_candidates())
        if self.sibling_action and self.sibling_action not in index.actions():
            errors.append(f"sibling_action {self.sibling_action!r} not found in {index.rel(index.package_dir)}")

        if self.purpose is None:
            ask("purpose", "One-line purpose (Javadoc + report).", blocking=False)
        if self.target_object is None:
            ask("target_object", "Target object or selection type (e.g. DEVICE_CONNECTOR, WIRE, none)?")
        if self.selection_rule is None:
            ask("selection_rule", "Selection rule required to enable the action?", SELECTION_RULES)
        elif self.selection_rule not in SELECTION_RULES:
            errors.append(f"selection_rule must be one of {SELECTION_RULES}")

        if self.mutates_model is None:
            ask("mutates_model", "Does the action mutate the model?", ["true", "false"])
        elif self.mutates_model:
            if self.undo_required is None:
                ask("undo_required", "Must the mutation be undoable as a single step?", ["true", "false"])
            if self.multi_user_safe is None:
                ask("multi_user_safe", "Is the mutation safe in multi-user mode?", ["true", "false"])

        if not self.applications:
            ask("applications", "Applications for @ApplicationSpecification(includeIn = ...)?",
                index.application_constants())
        if self.immersed_mode is None:
            ask("immersed_mode", "ApplicationSpecification.ImmersedMode value?", index.immersed_modes())
        if self.immersed is None:
            ask("immersed", "@ImmersedAction support? false, or {action_id, button_style, icon?, label_key?, "
                "tooltip_key?}", ["false"])
        elif self.immersed.get("enabled"):
            if not self.immersed.get("action_id"):
                ask("immersed.action_id", "Immersed action ID (e.g. CAPITAL_MY_ACTION)?")
            elif self.immersed["action_id"] in index.immersed_ids():
                errors.append(f"Immersed action ID {self.immersed['action_id']!r} is already used")
            if not self.immersed.get("button_style"):
                ask("immersed.button_style", "Immersed button style?", index.button_styles())

        if self.label is None:
            ask("label", "Display name / menu label?")
        if self.short_desc is None:
            ask("short_desc", "Short description (tooltip)?")
        if self.mnemonic is None:
            ask("mnemonic", "Mnemonic character (empty = none)?", blocking=False)
        if self.accelerator is None:
            ask("accelerator", "Accelerator keystroke, e.g. 'ctrl shift R' (empty = none)?", blocking=False)
        if self.icon is None:
            ask("icon", "Active icon name/path (empty string = no icon)?")

        res = index.resource_info()
        menus = sorted(res.get("menus", {}))
        toolbars = sorted(res.get("toolbars", {}))
        if self.menu is None:
            ask("menu", "LogicResource menu variable to register in, or 'none'?", menus + ["none"])
        elif self.menu.get("enabled"):
            var = self.menu.get("menu_var")
            if not var:
                ask("menu.menu_var", "Which menu variable?", menus)
            elif var not in res.get("menus", {}):
                if not self.menu.get("new_submenu_declaration") or not self.menu.get("parent_menu_var"):
                    ask("menu.menu_var", f"Menu variable {var!r} is not in LogicResource. Choose an existing one, "
                        "or supply new_submenu_declaration (Java statements) and parent_menu_var.", menus)
                elif self.menu["parent_menu_var"] not in res.get("menus", {}):
                    errors.append(f"parent_menu_var {self.menu['parent_menu_var']!r} not found in LogicResource")
        if self.toolbar is None:
            ask("toolbar", "Toolbar variable to register in, or 'none'?", toolbars + ["none"])
        elif self.toolbar.get("enabled") and self.toolbar.get("toolbar_var") not in res.get("toolbars", {}):
            ask("toolbar.toolbar_var", "Toolbar variable not found in LogicResource; pick one.", toolbars)

        if self.controller_registration is None:
            if self.controller_scoped:
                ask("controller_registration", "Register in LogicController? {insert_after: <sibling action>, "
                    "condition: <Java expression or null>} or false.", index.controller_info().get("registered", []))
            else:
                self.controller_registration = {"enabled": False}
        elif self.controller_registration.get("enabled"):
            after = self.controller_registration.get("insert_after")
            if after and after not in index.controller_info().get("registered", []):
                errors.append(f"controller_registration.insert_after {after!r} is not registered in LogicController")

        derivatives = {d["name"] for d in index.derivative_controllers()}
        if self.derivative_controllers is None and derivatives and self.enabled("controller_registration"):
            ask("derivative_controllers", "Also register in derivative controllers? ([] for none)", sorted(derivatives))
        for name in self.derivative_controllers or []:
            if name not in derivatives:
                errors.append(f"Derivative controller {name!r} not found")

        if self.ribbon is None:
            ask("ribbon", "Add to ribbon.xml? false, or {placements:[{group, insert_after_target?, x?, y?}], icon, "
                "visibility:{applications:[...], project_open:true, conditions:[raw xml]} or "
                "copy_visibility_from_anchor:true}", ["false"] + index.ribbon_group_labels())
        elif self.ribbon.get("enabled"):
            if not self.ribbon.get("placements"):
                ask("ribbon.placements", "Which ribbon group(s)? Buttons are inserted next to a sibling, never "
                    "appended to the end of the file.", index.ribbon_group_labels())
            if not self.ribbon.get("visibility") and not self.ribbon.get("copy_visibility_from_anchor"):
                ask("ribbon.visibility", "Ribbon visibility {applications:[...], project_open:true} or "
                    "copy_visibility_from_anchor:true?")
            if self.ribbon.get("icon") is None:
                ask("ribbon.icon", "Ribbon icon file (e.g. my-action-small.png)?")

        if self.gating is None:
            ask("gating", "Permission / feature flag / licence / QA gating? {} for none, else "
                "{qa_only, feature_flag, licence, permission}.")
        return errors, questions


# ─── Repository index ─────────────────────────────────────────────────────────

class LogicRepoIndex:
    """Read-only discovery of Capital Logic conventions (all results cached per instance)."""

    def __init__(self, root: str, layout: Optional[Dict[str, Any]] = None,
                 package: str = "chs.caplets.logic.actions"):
        self.root = Path(root).resolve()
        self.layout = dict(DEFAULT_LAYOUT)
        self.layout.update(layout or {})
        self.package = package
        self._memo: Dict[str, Any] = {}

    def path(self, key: str) -> Optional[Path]:
        value = self.layout.get(key)
        return self.root / value if value else None

    def rel(self, path: Path) -> str:
        try:
            return Path(path).resolve().relative_to(self.root).as_posix()
        except ValueError:
            return str(path)

    @property
    def package_dir(self) -> Path:
        return self.path("logic_src") / Path(*self.package.split("."))

    @property
    def tests_dir(self) -> Path:
        return self.path("logic_tests") / Path(*self.package.split("."))

    def _cached(self, key: str, loader):
        if key not in self._memo:
            self._memo[key] = loader()
        return self._memo[key]

    # classes in the action package
    def actions(self) -> Dict[str, Dict[str, Any]]:
        return self._cached("actions", self._load_actions)

    def _load_actions(self) -> Dict[str, Dict[str, Any]]:
        out: Dict[str, Dict[str, Any]] = {}
        if not self.package_dir.is_dir():
            return out
        for path in sorted(self.package_dir.glob("*.java")):
            text, _ = _read(path)
            name, base = _class_decl(text)
            if not name:
                continue
            out[name] = {
                "name": name, "path": path, "base": base, "text": text,
                "overrides": _extract_overrides(text), "ctor": _ctor_params(text, name),
                "ui_class": _class_ref_in(text, "getActionUIClass"),
                "action_class": _class_ref_in(text, "getActionClass"),
                "logger": _logger_decl(text, name), "mutates": "beginOperation" in text,
            }
        return out

    # repo-wide scan (imports, derivative controllers, annotation values)
    def _scan(self) -> Dict[str, Any]:
        return self._cached("scan", self._load_scan)

    def _load_scan(self) -> Dict[str, Any]:
        info: Dict[str, Any] = {"imports": defaultdict(Counter), "derivatives": [], "apps": Counter(),
                                "modes": Counter(), "styles": Counter(), "immersed_ids": set(),
                                "files": 0, "truncated": False}
        for base in (self.path("logic_src"), self.path("logic_tests")):
            if not base or not base.is_dir() or info["truncated"]:
                continue
            for dirpath, dirnames, filenames in os.walk(base):
                dirnames[:] = [d for d in dirnames if not d.startswith(".")]
                for filename in filenames:
                    if not filename.endswith(".java"):
                        continue
                    info["files"] += 1
                    if info["files"] > MAX_SCAN_FILES:
                        info["truncated"] = True
                        break
                    path = Path(dirpath) / filename
                    try:
                        text, _ = _read(path)
                    except OSError:
                        continue
                    self._scan_file(path, text, info)
                if info["truncated"]:
                    logger.warning("Capital scan truncated at %d files", MAX_SCAN_FILES)
                    break
        return info

    @staticmethod
    def _scan_file(path: Path, text: str, info: Dict[str, Any]) -> None:
        for simple, fqn in _extract_imports(text).items():
            info["imports"][simple][fqn] += 1
        pkg = _package_of(text)
        if pkg:
            info["imports"][path.stem][f"{pkg}.{path.stem}"] += 1
        if "ApplicationSpecification" in text or "ImmersedAction" in text:
            info["apps"].update(re.findall(r"\bApplication\.([A-Z]\w*)", text))
            info["modes"].update(re.findall(r"\bImmersedMode\.(\w+)", text))
            info["styles"].update(re.findall(r'buttonStyle\s*=\s*"(\w+)"', text))
            info["immersed_ids"].update(re.findall(r'actionId\s*=\s*"([^"]+)"', text))
        m = re.search(r"\bclass\s+(\w+)[^{;]*?\bextends\s+(\w*(?:LogicController|DerivativeController)\w*)", text)
        if m and m.group(1) != "LogicController" and "addAction(" in text:
            info["derivatives"].append({
                "name": m.group(1), "base": m.group(2), "path": path,
                "method": _method_containing(text, "addAction("),
                "registered": re.findall(r"\baddAction\(\s*new\s+(\w+)\s*\(", text),
            })

    def resolve(self, simple: str) -> Optional[str]:
        counts = self._scan()["imports"].get(simple)
        if counts:
            return counts.most_common(1)[0][0]
        return JDK_TYPES.get(simple)

    def application_constants(self) -> List[str]:
        return [a for a, _ in self._scan()["apps"].most_common()]

    def immersed_modes(self) -> List[str]:
        return [a for a, _ in self._scan()["modes"].most_common()]

    def button_styles(self) -> List[str]:
        return [a for a, _ in self._scan()["styles"].most_common()]

    def immersed_ids(self) -> set:
        return self._scan()["immersed_ids"]

    def derivative_controllers(self) -> List[Dict[str, Any]]:
        return self._scan()["derivatives"]

    def interactive_candidates(self) -> List[str]:
        return sorted({a["base"] for a in self.actions().values()
                       if a["base"] and INTERACTIVE_HINTS & set(a["overrides"])})

    def usage_example(self, needle: str) -> Optional[str]:
        return next((a["name"] for a in self.actions().values() if needle in a["text"]), None)

    # LogicController / LogicResource
    def controller_info(self) -> Dict[str, Any]:
        return self._cached("controller", self._load_controller)

    def _load_controller(self) -> Dict[str, Any]:
        path = self.path("controller")
        if not path or not path.is_file():
            return {"error": f"LogicController not found at {self.layout.get('controller')}"}
        text, enc = _read(path)
        method = self.layout["controller_method"]
        body = _find_method_body(text, method)
        regs = []
        if body:
            for m in re.finditer(r"\baddAction\(\s*new\s+(\w+)\s*\(", text[body[0]:body[1]]):
                regs.append({"action": m.group(1),
                             "condition": _enclosing_condition(text, body[0], body[0] + m.start())})
        return {"path": path, "encoding": enc, "method": method, "has_method": bool(body),
                "registrations": regs, "registered": [r["action"] for r in regs]}

    def resource_info(self) -> Dict[str, Any]:
        return self._cached("resource", self._load_resource)

    def _load_resource(self) -> Dict[str, Any]:
        path = self.path("resource")
        if not path or not path.is_file():
            return {"error": f"LogicResource not found at {self.layout.get('resource')}"}
        text, enc = _read(path)
        menus: Dict[str, List[str]] = defaultdict(list)
        toolbars: Dict[str, List[str]] = defaultdict(list)
        rb = caplet_var = None
        for m in re.finditer(r"\b(\w+)\.addActionUI\(\s*new\s+(\w+)\s*\(\s*(\w+)\s*\)\s*,\s*(\w+)\s*\)", text):
            rb, caplet_var = rb or m.group(1), caplet_var or m.group(3)
            menus[m.group(4)].append(m.group(2))
        for m in re.finditer(r"\b(\w+)\.addActionUIEntry\(\s*(\w+)\.class\s*,\s*(\w+)\s*\)", text):
            rb = rb or m.group(1)
            toolbars[m.group(3)].append(m.group(2))
        sep = re.search(r"\b\w+\.(\w*[Ss]eparator\w*)\(\s*\w+\s*\)", text)
        if not caplet_var:
            m = re.search(r"\bnew\s+\w+UI\s*\(\s*(\w+)\s*\)", text)
            caplet_var = m.group(1) if m else "caplet"
        return {"path": path, "encoding": enc, "rb": rb or "rb", "caplet_var": caplet_var,
                "menus": dict(menus), "toolbars": dict(toolbars),
                "separator_method": sep.group(1) if sep else None,
                "has_init_actions": bool(_find_method_body(text, "initActions"))}

    # ribbon.xml (parsed with expat to keep exact byte offsets -> surgical insertion)
    def ribbon(self) -> Dict[str, Any]:
        return self._cached("ribbon", self._load_ribbon)

    def _load_ribbon(self) -> Dict[str, Any]:
        path = self.path("ribbon")
        if not path or not path.is_file():
            return {"error": f"ribbon.xml not found at {self.layout.get('ribbon')}"}
        data = path.read_bytes()
        m = re.match(rb'(?:\xef\xbb\xbf)?<\?xml[^>]*encoding=["\']([\w.-]+)["\']', data)
        encoding = m.group(1).decode("ascii") if m else "utf-8"
        parser = xml.parsers.expat.ParserCreate()
        nodes: List[Dict[str, Any]] = []
        stack: List[Dict[str, Any]] = []

        def start(tag, attrs):
            node = {"tag": tag, "attrs": attrs, "start": parser.CurrentByteIndex, "end": None,
                    "children": [], "parent": stack[-1] if stack else None}
            if stack:
                stack[-1]["children"].append(node)
            stack.append(node)
            nodes.append(node)

        def end(_tag):
            node = stack.pop()
            node["end"] = data.index(b">", max(parser.CurrentByteIndex, node["start"])) + 1

        parser.StartElementHandler = start
        parser.EndElementHandler = end
        try:
            parser.Parse(data, True)
        except xml.parsers.expat.ExpatError as exc:
            return {"error": f"ribbon.xml is not well-formed: {exc}"}

        groups, seen = [], Counter()
        for node in nodes:
            buttons = [c for c in node["children"] if c["tag"] == "button"]
            if not buttons:
                continue
            chain, cur = [], node
            while cur is not None:
                chain.append(cur)
                cur = cur["parent"]
            parts = []
            for anc in reversed(chain):
                label = anc["attrs"].get("name") or anc["attrs"].get("id") or anc["attrs"].get("label")
                parts.append(f"{anc['tag']}[{label}]" if label else anc["tag"])
            group_path = "/".join(parts)
            seen[group_path] += 1
            if seen[group_path] > 1:
                group_path += f"#{seen[group_path]}"
            apps = sorted({d["attrs"]["name"] for d in self._descendants(node)
                           if d["tag"] == "application" and d["attrs"].get("name")})
            groups.append({"path": group_path, "applications": apps,
                           "buttons": [self._button(b, data) for b in buttons]})
        return {"path": path, "data": data, "encoding": encoding, "groups": groups,
                "help_ids": {n["attrs"]["help-id"] for n in nodes if n["attrs"].get("help-id")},
                "targets": {n["attrs"]["target"] for n in nodes if n["attrs"].get("target")}}

    @staticmethod
    def _descendants(node: Dict[str, Any]):
        for child in node["children"]:
            yield child
            yield from LogicRepoIndex._descendants(child)

    @staticmethod
    def _button(node: Dict[str, Any], data: bytes) -> Dict[str, Any]:
        def as_int(v):
            try:
                return int(v)
            except (TypeError, ValueError):
                return None
        ls = data.rfind(b"\n", 0, node["start"]) + 1
        vis = next((c for c in node["children"] if c["tag"] == "visibility"), None)
        return {"target": node["attrs"].get("target"), "help_id": node["attrs"].get("help-id"),
                "x": as_int(node["attrs"].get("x")), "y": as_int(node["attrs"].get("y")),
                "start": node["start"], "end": node["end"],
                "indent": re.match(rb"[ \t]*", data[ls:]).group(0).decode("ascii"),
                "visibility": (data.rfind(b"\n", 0, vis["start"]) + 1, vis["end"]) if vis else None}

    def ribbon_group_labels(self) -> List[str]:
        return [f"{g['path']}  (apps: {', '.join(g['applications']) or '-'}; buttons: {len(g['buttons'])})"
                for g in self.ribbon().get("groups", [])]

    def find_ribbon_group(self, wanted: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        groups = self.ribbon().get("groups", [])
        wanted = wanted.split("  (apps:")[0].strip()
        exact = [g for g in groups if g["path"] == wanted]
        if exact:
            return exact[0], None
        partial = [g for g in groups if wanted and wanted in g["path"]]
        if len(partial) == 1:
            return partial[0], None
        if not partial:
            return None, f"Ribbon group {wanted!r} not found"
        return None, f"Ribbon group {wanted!r} is ambiguous: {[g['path'] for g in partial]}"

    # bundles / icons
    def bundle(self) -> Optional[Path]:
        if self.layout.get("bundle"):
            path = self.root / self.layout["bundle"]
            return path if path.is_file() else None
        name = f"{self.layout['bundle_name']}.properties"
        pkg = Path(*self.package.split("."))
        for base in (self.path("resources_root"), self.path("logic_src")):
            if not base or not base.is_dir():
                continue
            cur = base / pkg
            while True:
                if (cur / name).is_file():
                    return cur / name
                if cur == base or base not in cur.parents:
                    break
                cur = cur.parent
        return None

    @staticmethod
    def locale_bundles(bundle: Path) -> List[Path]:
        return sorted(bundle.parent.glob(f"{bundle.stem}_*.properties"))

    def ribbon_bundle(self) -> Optional[Path]:
        return self._cached("ribbon_bundle", self._load_ribbon_bundle)

    def _load_ribbon_bundle(self) -> Optional[Path]:
        if self.layout.get("ribbon_bundle"):
            path = self.root / self.layout["ribbon_bundle"]
            return path if path.is_file() else None
        candidates: List[Path] = []
        ribbon = self.path("ribbon")
        if ribbon and ribbon.parent.is_dir():
            candidates += sorted(ribbon.parent.glob("*.properties"))
        root = self.path("resources_root")
        if root and root.is_dir():
            candidates += sorted(root.rglob("*.properties"))[:3000]
        for path in candidates:
            if re.search(r"_[a-z]{2}(_[A-Z]{2})?\.properties$", path.name):
                continue
            try:
                if "ribbon.button." in _read(path, "latin-1")[0]:
                    return path
            except OSError:
                continue
        return None

    def _icon_index(self) -> Dict[str, List[str]]:
        index: Dict[str, List[str]] = defaultdict(list)
        count = 0
        for rel_root in self.layout.get("icon_roots") or []:
            base = self.root / rel_root
            if not base.is_dir():
                continue
            for dirpath, dirnames, filenames in os.walk(base):
                dirnames[:] = [d for d in dirnames if not d.startswith(".")]
                for filename in filenames:
                    if filename.lower().endswith(IMAGE_EXTS):
                        count += 1
                        rel = self.rel(Path(dirpath) / filename)
                        index[filename.lower()].append(rel)
                        index["stem:" + filename.rsplit(".", 1)[0].lower()].append(rel)
                if count > MAX_ICON_FILES:
                    return index
        return index

    def find_icon(self, name: Optional[str]) -> List[str]:
        if not name:
            return []
        idx = self._cached("icons", self._icon_index)
        base = name.replace("\\", "/").split("/")[-1].lower()
        return idx.get(base, []) if "." in base else idx.get("stem:" + base, [])

    def hidpi_variants(self, name: str) -> List[str]:
        stem = name.replace("\\", "/").split("/")[-1].rsplit(".", 1)[0]
        found: List[str] = []
        for variant in (f"{stem}@2x", f"{stem}_2x", f"{stem}_hidpi", f"{stem}-hidpi"):
            found += self.find_icon(variant)
        return found


class _Imports:
    """Collects imports; Capital types are resolved only from the repo, never invented."""

    def __init__(self, index: LogicRepoIndex, package: str, local: set):
        self.index, self.package, self.local = index, package, local
        self.fqns: set = set()
        self.unresolved: set = set()

    def use(self, simple: Optional[str], fqn: Optional[str] = None) -> None:
        if not simple or simple in JAVA_LANG or simple in self.local:
            return
        fqn = fqn or self.index.resolve(simple)
        if not fqn:
            self.unresolved.add(simple)
        elif fqn.rsplit(".", 1)[0] != self.package:
            self.fqns.add(fqn)

    def use_types_in(self, code: str) -> None:
        for simple in re.findall(r"\b([A-Z]\w*)\b", code):
            if simple.isupper():      # constants such as SMALL_IMAGE are not types
                continue
            self.use(simple)

    def render(self) -> str:
        lines = [f"import {f};" for f in sorted(self.fqns)]
        lines += [f"// TODO(import): resolve {s} - not imported anywhere in the scanned Capital sources"
                  for s in sorted(self.unresolved)]
        return "\n".join(lines)


# ─── Generator ────────────────────────────────────────────────────────────────

class LogicActionGenerator:
    """Plans, generates, validates and applies Capital Logic action change sets."""

    def __init__(self, repo_path: str):
        self.repo_path = Path(repo_path)
        self.store_dir = self.repo_path / ".copilotlens" / "logic_action_changesets"

    # ── public API ──────────────────────────────────────────────────────────
    def generate_action(self, action_name: str, target_object: Optional[str] = None,
                        package_name: str = "chs.caplets.logic.actions", spec_json: str = "") -> Dict[str, Any]:
        """Backwards-compatible entry point: returns the plan (questions + discovered options)."""
        data: Dict[str, Any] = {}
        if spec_json and spec_json.strip():
            try:
                data = json.loads(spec_json)
            except json.JSONDecodeError as exc:
                return {"status": "error", "errors": [f"spec_json is not valid JSON: {exc}"]}
            if not isinstance(data, dict):
                return {"status": "error", "errors": ["spec_json must be a JSON object"]}
        data.setdefault("action_name", action_name)
        data.setdefault("package", package_name)
        if target_object:
            data.setdefault("target_object", target_object)
        return self.plan(data)

    def plan(self, spec_input: Any) -> Dict[str, Any]:
        spec, index, errors = self._load(spec_input)
        if errors:
            return {"status": "error", "errors": errors}
        errors, questions = spec.validate(index)
        errors += self._environment_errors(spec, index)
        blocking = [q for q in questions if q["blocking"]]
        status = "error" if errors else ("needs_input" if blocking else "ready")
        sibling = self._choose_sibling(spec, index) if spec.action_type else None
        bundle = index.bundle()
        ribbon_on = spec.enabled("ribbon")
        result = {
            "status": status,
            "capital_repo": str(index.root),
            "action": spec.fqn,
            "errors": errors,
            "questions": questions,
            "discovered": {
                "sibling_action": sibling["name"] if sibling else None,
                "menus": index.resource_info().get("menus", {}),
                "toolbars": index.resource_info().get("toolbars", {}),
                "controller_registrations": index.controller_info().get("registrations", [])[:60],
                "derivative_controllers": [{"name": d["name"], "method": d["method"], "path": index.rel(d["path"])}
                                           for d in index.derivative_controllers()],
                "ribbon_groups": index.ribbon_group_labels(),
                "bundle": index.rel(bundle) if bundle else None,
                "locale_bundles": [index.rel(p) for p in index.locale_bundles(bundle)] if bundle else [],
                "ribbon_bundle": index.rel(index.ribbon_bundle()) if ribbon_on and index.ribbon_bundle() else None,
                "java_files_scanned": index._scan()["files"],
            },
            "planned_files": self._planned_files(spec, index) if status != "error" else {},
            "must_be_confirmed_by_developer": [
                "Action base class", "Domain mutation semantics (left as TODO)", "Selection rules",
                "Menu/submenu", "Application and caplet visibility", "Feature/licence/permission guards",
                "Undo/redo behaviour", "Exact ribbon location", "Derivative controller registration",
                "Immersed-mode support", "Localization wording", "Multi-user safety",
            ],
        }
        result["next_step"] = {
            "ready": "Call generate_logic_action_changeset with the same spec to get reviewable diffs.",
            "needs_input": "Ask the developer every blocking question, add the answers to the spec and re-plan.",
            "error": "Fix the errors above and re-plan.",
        }[status]
        return result

    def generate_changeset(self, spec_input: Any) -> Dict[str, Any]:
        plan = self.plan(spec_input)
        if plan["status"] != "ready":
            plan["message"] = "Change set not generated - the plan is not ready."
            return plan
        spec, index, _ = self._load(spec_input)
        cs = self._build(spec, index)
        blocking = [v for v in cs["validation"] if v["status"] == "fail"] + \
                   [{"check": "generation", "status": "fail", "detail": e} for e in cs["errors"]]
        files = []
        for path, entry in cs["files"].items():
            rel = index.rel(path)
            old, new = entry["old"], entry["new"]
            diff = "".join(difflib.unified_diff(
                (old or "").splitlines(keepends=True), new.splitlines(keepends=True),
                fromfile="/dev/null" if old is None else f"a/{rel}", tofile=f"b/{rel}", n=3)).replace("\r", "")
            files.append({"path": rel, "action": "create" if old is None else "modify",
                          "encoding": entry["encoding"],
                          "original_sha256": None if old is None else _sha(old.encode(entry["encoding"])),
                          "new_content": new, "diff": diff})
        record = {
            "id": time.strftime("%Y%m%d%H%M%S") + "-" + uuid.uuid4().hex[:8],
            "action": spec.fqn, "test_class": spec.test_name, "test_fqn": f"{spec.package}.{spec.test_name}",
            "capital_repo": str(index.root), "created": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "files": files, "todos": cs["todos"], "warnings": cs["warnings"],
            "localization": cs["localization"], "validation": cs["validation"], "applied": None,
        }
        status = "blocked" if blocking else "generated"
        if not blocking:
            self.store_dir.mkdir(parents=True, exist_ok=True)
            (self.store_dir / f"{record['id']}.json").write_text(json.dumps(record, indent=1), encoding="utf-8")
        logger.info("Logic action change set %s for %s: %s", record["id"], spec.fqn, status)
        return {
            "status": status,
            "changeset_id": record["id"] if not blocking else None,
            "blocking_issues": blocking,
            "report_markdown": self._report(record, status),
            "files": [{k: f[k] for k in ("path", "action", "diff")} for f in files],
            "next_step": "Review the diffs, then call apply_logic_action_changeset(changeset_id)." if not blocking
            else "Resolve the blocking issues and regenerate.",
        }

    def apply_changeset(self, changeset_id: str, run_build: bool = False) -> Dict[str, Any]:
        if not re.match(r"^[\w-]+$", changeset_id or ""):
            return {"status": "error", "errors": ["Invalid changeset id"]}
        store = self.store_dir / f"{changeset_id}.json"
        if not store.is_file():
            return {"status": "error", "errors": [f"Change set {changeset_id} not found"]}
        record = json.loads(store.read_text(encoding="utf-8"))
        if record.get("applied"):
            return {"status": "error", "errors": [f"Change set already applied at {record['applied']}"]}
        root = Path(record["capital_repo"])

        conflicts, originals = [], {}
        for f in record["files"]:
            target = root / f["path"]
            if f["action"] == "create":
                if target.exists():
                    conflicts.append(f"{f['path']} already exists")
            elif not target.is_file():
                conflicts.append(f"{f['path']} no longer exists")
            else:
                data = target.read_bytes()
                if _sha(data) != f["original_sha256"]:
                    conflicts.append(f"{f['path']} changed since the change set was generated")
                originals[f["path"]] = data
        if conflicts:
            return {"status": "conflict", "errors": conflicts, "next_step": "Regenerate the change set."}

        written: List[Dict[str, Any]] = []
        try:
            for f in record["files"]:
                target = root / f["path"]
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(f["new_content"].encode(f["encoding"]))
                written.append(f)
        except (OSError, UnicodeEncodeError) as exc:
            logger.exception("Applying change set %s failed; rolling back", changeset_id)
            for f in written:
                target = root / f["path"]
                if f["action"] == "create":
                    target.unlink(missing_ok=True)
                else:
                    target.write_bytes(originals[f["path"]])
            return {"status": "error", "errors": [f"Write failed, rolled back: {exc}"]}

        record["applied"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        record["build"] = self._run_build(root, record) if run_build else [
            {"step": "build/test", "status": "skipped", "detail": "run_build=false"}]
        store.write_text(json.dumps(record, indent=1), encoding="utf-8")
        logger.info("Applied logic action change set %s (%d files)", changeset_id, len(written))
        return {"status": "applied", "changeset_id": changeset_id,
                "written": [f"{f['action']}: {f['path']}" for f in written],
                "build": record["build"], "report_markdown": self._report(record, "applied")}

    # ── internals: loading / planning ───────────────────────────────────────
    def _load(self, spec_input: Any) -> Tuple[Optional[ActionSpec], Optional[LogicRepoIndex], List[str]]:
        if isinstance(spec_input, str):
            try:
                data = json.loads(spec_input) if spec_input.strip() else {}
            except json.JSONDecodeError as exc:
                return None, None, [f"spec_json is not valid JSON: {exc}"]
        else:
            data = spec_input or {}
        if not isinstance(data, dict):
            return None, None, ["The spec must be a JSON object"]
        data = dict(data)
        if not data.get("action_name"):
            return None, None, ["action_name is required"]
        spec = ActionSpec.from_dict(data)
        root = spec.capital_repo or os.environ.get("CAPITAL_REPO") or str(self.repo_path)
        return spec, LogicRepoIndex(root, spec.layout, spec.package), []

    @staticmethod
    def _environment_errors(spec: ActionSpec, index: LogicRepoIndex) -> List[str]:
        errors: List[str] = []
        if not index.package_dir.is_dir():
            errors.append(f"Action package directory not found: {index.package_dir}. Set spec.capital_repo or "
                          f"$CAPITAL_REPO to the Capital checkout, or override spec.layout.logic_src.")
            return errors
        for path in (index.package_dir / f"{spec.action_name}.java", index.package_dir / f"{spec.ui_name}.java",
                     index.tests_dir / f"{spec.test_name}.java"):
            if path.exists():
                errors.append(f"{index.rel(path)} already exists")
        if spec.enabled("controller_registration"):
            ctrl = index.controller_info()
            if ctrl.get("error"):
                errors.append(ctrl["error"])
            elif not ctrl["has_method"]:
                errors.append(f"{ctrl['method']}() not found in LogicController")
            elif spec.action_name in ctrl["registered"]:
                errors.append(f"{spec.action_name} is already registered in LogicController")
        if spec.enabled("menu") or spec.enabled("toolbar") or spec.init_in_init_actions:
            res = index.resource_info()
            if res.get("error"):
                errors.append(res["error"])
            elif spec.init_in_init_actions and not res["has_init_actions"]:
                errors.append("initActions() not found in LogicResource")
        if spec.enabled("ribbon"):
            rib = index.ribbon()
            if rib.get("error"):
                errors.append(rib["error"])
            else:
                if spec.help_id in rib["help_ids"]:
                    errors.append(f"help-id {spec.help_id} already exists in ribbon.xml")
                for pl in spec.ribbon.get("placements") or []:
                    _, err = index.find_ribbon_group(pl.get("group", ""))
                    if err:
                        errors.append(err)
                if not index.ribbon_bundle():
                    errors.append("Ribbon resource bundle not found; set spec.layout.ribbon_bundle")
        if not index.bundle():
            errors.append(f"{index.layout['bundle_name']}.properties not found for package {spec.package}; "
                          "set spec.layout.bundle")
        return errors

    @staticmethod
    def _planned_files(spec: ActionSpec, index: LogicRepoIndex) -> Dict[str, List[str]]:
        create = [index.rel(index.package_dir / f"{spec.action_name}.java"),
                  index.rel(index.package_dir / f"{spec.ui_name}.java"),
                  index.rel(index.tests_dir / f"{spec.test_name}.java")]
        modify: List[str] = []
        if spec.enabled("controller_registration"):
            modify.append(index.layout["controller"])
            modify += [index.rel(d["path"]) for d in index.derivative_controllers()
                       if d["name"] in (spec.derivative_controllers or [])]
        if spec.enabled("menu") or spec.enabled("toolbar") or spec.init_in_init_actions:
            modify.append(index.layout["resource"])
        bundle = index.bundle()
        if bundle:
            modify.append(index.rel(bundle))
            if spec.localization == "placeholder":
                modify += [index.rel(p) for p in index.locale_bundles(bundle)]
        if spec.enabled("ribbon"):
            modify.append(index.layout["ribbon"])
            rb = index.ribbon_bundle()
            if rb and rb != bundle:
                modify.append(index.rel(rb))
        return {"create": create, "modify": modify}

    @staticmethod
    def _choose_sibling(spec: ActionSpec, index: LogicRepoIndex) -> Optional[Dict[str, Any]]:
        actions = index.actions()
        if spec.sibling_action:
            return actions.get(spec.sibling_action)
        base = spec.base_class or spec.type_info.get("base_class")
        if not base:
            return None
        target = (spec.target_object or "").lower().replace("_", "")
        best, best_score = None, -1
        for a in actions.values():
            if a["base"] != base or a["name"] in (spec.action_name, spec.ui_name):
                continue
            score = 3 if a["ui_class"] in actions else 0
            score += 2 if target and target in a["text"].lower().replace("_", "") else 0
            score += 1 if spec.mutates_model is not None and a["mutates"] == bool(spec.mutates_model) else 0
            if score > best_score:
                best, best_score = a, score
        return best

    # ── internals: building ─────────────────────────────────────────────────
    def _build(self, spec: ActionSpec, index: LogicRepoIndex) -> Dict[str, Any]:
        cs: Dict[str, Any] = {"files": {}, "errors": [], "todos": [], "warnings": [], "localization": [],
                              "validation": []}

        def current(path: Path, encoding: Optional[str] = None) -> Tuple[str, str]:
            if path in cs["files"]:
                return cs["files"][path]["new"], cs["files"][path]["encoding"]
            return _read(path, encoding)

        def put(path: Path, new: str, encoding: str = "utf-8", created: bool = False) -> None:
            if path in cs["files"]:
                cs["files"][path]["new"] = new
            else:
                old = None if created else _read(path, encoding)[0]
                cs["files"][path] = {"old": old, "new": new, "encoding": encoding}

        sibling = self._choose_sibling(spec, index)
        actions = index.actions()
        sibling_ui = actions.get(sibling["ui_class"]) if sibling and sibling.get("ui_class") else None
        if sibling:
            cs["warnings"].append(f"Conventions copied from sibling {sibling['name']}"
                                  + (f" / {sibling_ui['name']}" if sibling_ui else ""))
        else:
            cs["warnings"].append("No sibling action with the same base class was found; default framework "
                                  "signatures were used - verify them against the base class.")

        local = set(actions) | {spec.action_name, spec.ui_name, spec.test_name}
        action_src, error_keys = self._render_action(spec, index, sibling, local, cs)
        ui_src, ui_keys = self._render_ui(spec, index, sibling, sibling_ui, local, cs)
        all_keys = {**ui_keys, **error_keys}
        test_src = self._render_test(spec, index, sibling, local, list(all_keys), cs)
        put(index.package_dir / f"{spec.action_name}.java", action_src, created=True)
        put(index.package_dir / f"{spec.ui_name}.java", ui_src, created=True)
        put(index.tests_dir / f"{spec.test_name}.java", test_src, created=True)

        # LogicController + derivative controllers
        if spec.enabled("controller_registration"):
            ctrl = index.controller_info()
            text, enc = current(ctrl["path"])
            new, err, note = self._patch_controller(text, spec, ctrl["method"], spec.controller_registration)
            if err:
                cs["errors"].append(f"LogicController: {err}")
            else:
                put(ctrl["path"], new, enc)
                if note:
                    cs["warnings"].append(note)
            for d in index.derivative_controllers():
                if d["name"] not in (spec.derivative_controllers or []):
                    continue
                if not d["method"]:
                    cs["errors"].append(f"{d['name']}: no method containing addAction(...) found")
                    continue
                text, enc = current(d["path"])
                new, err, _ = self._patch_controller(text, spec, d["method"], {"enabled": True})
                if err:
                    cs["errors"].append(f"{d['name']}: {err}")
                else:
                    put(d["path"], new, enc)

        # LogicResource
        if spec.enabled("menu") or spec.enabled("toolbar") or spec.init_in_init_actions:
            res = index.resource_info()
            text, enc = current(res["path"])
            new, errs, notes = self._patch_resource(text, spec, res)
            cs["errors"] += [f"LogicResource: {e}" for e in errs]
            cs["todos"] += notes
            if not errs:
                put(res["path"], new, enc)

        # Resource bundles
        entries = dict(all_keys)
        if spec.enabled("immersed"):
            words = ".".join(w.lower() for w in _camel_words(spec.action_name))
            entries[spec.immersed.get("label_key") or f"capital.{words}.label"] = spec.label
            entries[spec.immersed.get("tooltip_key") or f"capital.{words}.tooltip"] = spec.tooltip
            cs["todos"].append("Immersed label/tooltip keys were added to the default bundle - confirm the "
                               "immersed framework reads them from that bundle.")
        bundle = index.bundle()
        if bundle:
            text, _ = current(bundle, "latin-1")
            new, errs = self._patch_properties(text, entries, spec.action_name)
            cs["errors"] += errs
            put(bundle, new, "latin-1")
            self._localize(spec, index, bundle, entries, cs, current, put)

        # Ribbon
        ribbon_keys: Dict[str, str] = {}
        if spec.enabled("ribbon"):
            rib = index.ribbon()
            new_bytes, errs, notes = self._patch_ribbon(rib, spec, index)
            cs["errors"] += errs
            cs["todos"] += notes
            if not errs:
                put(rib["path"], new_bytes.decode(rib["encoding"]), rib["encoding"])
            ribbon_keys = {f"ribbon.button.{spec.action_name}.text": spec.label,
                           f"ribbon.button.{spec.action_name}.tooltip": spec.tooltip}
            rbundle = index.ribbon_bundle()
            if rbundle:
                text, _ = current(rbundle, "latin-1")
                new, errs = self._patch_properties(text, ribbon_keys, f"{spec.action_name} ribbon")
                cs["errors"] += errs
                put(rbundle, new, "latin-1")
                if rbundle != bundle:
                    self._localize(spec, index, rbundle, ribbon_keys, cs, current, put)

        cs["validation"] = self._validate(spec, index, cs, entries, ribbon_keys, bundle)
        return cs

    def _localize(self, spec, index, bundle, entries, cs, current, put) -> None:
        locales = index.locale_bundles(bundle)
        if not locales:
            return
        if spec.localization == "placeholder":
            for loc in locales:
                text, _ = current(loc, "latin-1")
                new, errs = self._patch_properties(text, entries, f"{spec.action_name} (TODO(l10n): translate)",
                                                   l10n_todo=True)
                cs["errors"] += errs
                put(loc, new, "latin-1")
            status = "placeholders added (English text marked TODO(l10n))"
        else:
            status = "translation required"
        cs["localization"].append({"bundle": index.rel(bundle), "status": status,
                                   "locales": [index.rel(p) for p in locales], "keys": list(entries)})

    # ── rendering ───────────────────────────────────────────────────────────
    def _render_action(self, spec, index, sibling, local, cs) -> Tuple[str, Dict[str, str]]:
        imp = _Imports(index, spec.package, local)
        name, ui = spec.action_name, spec.ui_name
        base = spec.base_class or spec.type_info.get("base_class") or (sibling or {}).get("base")
        imp.use(base)

        dep, param = spec.type_info.get("dependency"), spec.type_info.get("param")
        sib_ctor = (sibling or {}).get("ctor")
        if sib_ctor:
            tokens = re.sub(r"@\w+\s*", "", sib_ctor).split(",")[0].split()
            if len(tokens) >= 2:
                if dep and tokens[-2] != dep:
                    cs["warnings"].append(f"Sibling {sibling['name']} constructor takes {tokens[-2]}, "
                                          f"expected {dep} for {spec.action_type}")
                dep, param = dep or tokens[-2], param or tokens[-1]
        if not dep:
            dep, param = "ICapletController", "controller"
            cs["todos"].append(f"{name}: constructor dependency could not be derived from a sibling - verify it.")
        imp.use(dep)
        imp.use("NotNull")

        overrides = (sibling or {}).get("overrides", {})
        log = (sibling or {}).get("logger")
        if log:
            log_decl = log["declaration"].replace("{cls}", name)
            imp.use(log["type"])
            jul = index.resolve(log["type"]) == "java.util.logging.Logger"
            log_var = log["var"]
        else:
            log_decl = f"private static final Logger LOG = Logger.getLogger({name}.class.getName());"
            imp.use("Logger", "java.util.logging.Logger")
            jul, log_var = True, "LOG"
        if jul:
            imp.use("Level", "java.util.logging.Level")

        def warn(expr: str) -> str:
            return f"{log_var}.warning({expr});" if jul else f"{log_var}.warn({expr});"

        def error(expr: str) -> str:
            return f"{log_var}.log(Level.SEVERE, {expr}, e);" if jul else f"{log_var}.error({expr}, e);"

        imp.use("ResourceMgr")
        err_invalid, err_failed = f"{name}.error.invalidSelection", f"{name}.error.operationFailed"
        error_keys = {err_invalid: f"{spec.label} is not available for the current selection.",
                      err_failed: f"{spec.label} failed."}

        ui_override = overrides.get("getActionUIClass", {})
        ui_sig = ui_override.get("signature", "public String getActionUIClass()")
        ui_ret = f"{ui}.class" if "Class" in ui_override.get("return_type", "String") else f"{ui}.class.getName()"
        enabled_sig = overrides.get("isEnabled", {}).get("signature", "public boolean isEnabled()")
        lifecycle = [m for m in overrides if m not in NON_LIFECYCLE]
        entry = next((m for m in ENTRY_METHODS if m in overrides), None)
        if entry is None and spec.action_type == "interactive" and lifecycle:
            entry = lifecycle[0]
        if entry:
            entry_sig, entry_ret = overrides[entry]["signature"], overrides[entry]["return_type"]
        else:
            entry, entry_sig, entry_ret = "actionPerformed", "public void actionPerformed(ActionEvent event)", "void"
        for sig in (ui_sig, enabled_sig, entry_sig):
            imp.use_types_in(sig)
        default = _default_return(entry_ret)
        ret = "return;" if default is None else f"return {default};"
        purpose = spec.purpose or "TODO(developer): describe the purpose of this action."

        L = [f"package {spec.package};", "", "@@IMPORTS@@", "", "/**", f" * {purpose}", " * <p>",
             f" * Target object: {spec.target_object}. Selection rule: {spec.selection_rule}. "
             f"Mutates model: {str(bool(spec.mutates_model)).lower()}.",
             " * <p>",
             " * Generated by CopilotLens. Sections marked TODO(developer) hold domain decisions that must be",
             " * written by hand - the generator never infers model semantics from the action name.",
             " */", f"public class {name} extends {base}", "{", f"    {log_decl}", "",
             f"    public {name}(@NotNull {dep} {param})", "    {", f"        super({param});", "    }", "",
             "    @Override", f"    {ui_sig}", "    {", f"        return {ui_ret};", "    }", "",
             "    @Override", f"    {enabled_sig}", "    {",
             "        return isGatingSatisfied() && isSelectionValid();", "    }", "",
             "    @Override", f"    {entry_sig}", "    {",
             "        if (!isEnabled())", "        {",
             f"            {warn(f'ResourceMgr.getString({ui}.class, {_java_str(err_invalid)})')}",
             f"            {ret}", "        }"]
        if spec.long_running:
            example = index.usage_example("WaitCursor")
            L.append("        // TODO(ui): long-running operation - wrap runAction() in a WaitCursor"
                     + (f" following {example}." if example else " (no existing usage found in this package)."))
            cs["todos"].append(f"{name}: apply the WaitCursor pattern around runAction().")
        L += ["        try", "        {", "            runAction();", "        }", "        catch (RuntimeException e)",
              "        {", f"            String message = ResourceMgr.getString({ui}.class, {_java_str(err_failed)});",
              f"            {error('message')}"]
        if spec.ui_work:
            imp.use("SwingUtilities", "javax.swing.SwingUtilities")
            L += ["            SwingUtilities.invokeLater(() -> {",
                  "                // TODO(ui): show `message` with the caplet's standard error dialog (EDT).",
                  "            });"]
            cs["todos"].append(f"{name}: show the operation-failed message using the standard error dialog.")
        L += ["        }"]
        if default is not None:
            L.append(f"        {ret}")
        L += ["    }", ""]

        if spec.action_type == "interactive" and sibling:
            for method in lifecycle:
                if method == entry:
                    continue
                sig = overrides[method]["signature"]
                imp.use_types_in(sig)
                d = _default_return(overrides[method]["return_type"])
                L += ["    @Override", f"    {sig}", "    {",
                      f"        // TODO(developer): interactive lifecycle - mirror {sibling['name']}.{method}() "
                      "(restore cursor, clean up temporary graphics)."]
                if d is not None:
                    L.append(f"        return {d};")
                L += ["    }", ""]
            cs["todos"].append(f"{name}: implement the interactive lifecycle methods copied from {sibling['name']}.")
        elif spec.action_type == "interactive":
            cs["todos"].append(f"{name}: no interactive sibling found - add the {base} lifecycle overrides by hand.")

        gating = spec.gating_items()
        L += ["    private boolean isGatingSatisfied()", "    {"]
        if gating:
            for key, value in gating.items():
                L.append(f"        // TODO(gating): enforce {key} = {value} using the project's standard check.")
            L.append("        return false; // disabled until the gating checks above are implemented")
            cs["todos"].append(f"{name}: implement gating checks {gating}.")
        else:
            L.append("        return true; // no permission, feature-flag, licence or QA gating was specified")
        L += ["    }", "", "    private boolean isSelectionValid()", "    {",
              f"        // TODO(selection): enable only with an active Logic design and selection rule "
              f"'{spec.selection_rule}' on {spec.target_object}"
              + (f" (see {sibling['name']}.isEnabled())." if sibling else "."),
              "        return false; // safe default: disabled until the rule is implemented", "    }", "",
              "    private void runAction()", "    {"]
        cs["todos"].append(f"{name}: implement isSelectionValid() for rule '{spec.selection_rule}'.")
        if spec.mutates_model:
            imp.use("FactoryMgr")
            if spec.multi_user_safe is False:
                L.append("        // WARNING: specified as NOT multi-user safe - TODO(developer): add the required "
                         "ownership/lock check before mutating.")
                cs["todos"].append(f"{name}: add a multi-user ownership/lock check.")
            L += ["        FactoryMgr.getAPIFactory().beginOperation();", "        try", "        {",
                  f"            // TODO(developer): model mutation on {spec.target_object}. Intentionally not "
                  "generated.",
                  "            // Undo/redo: " + ("all changes inside this operation must form ONE undoable step."
                                                  if spec.undo_required else
                                                  "specified as NOT requiring undo - confirm this is intended."),
                  "        }", "        finally", "        {", "            FactoryMgr.getAPIFactory().endOperation();",
                  "        }"]
            cs["todos"].append(f"{name}: write the model mutation inside the operation boundary.")
        else:
            L.append("        // TODO(developer): read-only logic. This action must not mutate the model.")
            cs["todos"].append(f"{name}: implement the read-only action logic.")
        L += ["    }", "}", ""]
        if imp.unresolved:
            cs["warnings"].append(f"{name}: unresolved imports {sorted(imp.unresolved)}")
        return "\n".join(L).replace("@@IMPORTS@@", imp.render()), error_keys

    def _render_ui(self, spec, index, sibling, sibling_ui, local, cs) -> Tuple[str, Dict[str, str]]:
        imp = _Imports(index, spec.package, local)
        ui = spec.ui_name
        for simple in ("ActionUI", "ApplicationSpecification", "Application", "NotNull", "ResourceMgr"):
            imp.use(simple)
        ctor = (sibling_ui or {}).get("ctor") or "ICaplet caplet"
        ctor_tokens = re.sub(r"@\w+\s*", "", ctor).split(",")[0].split()
        ctor_type, ctor_param = (ctor_tokens[-2], ctor_tokens[-1]) if len(ctor_tokens) >= 2 else ("ICaplet", "caplet")
        imp.use(ctor_type)
        setup_sig = (sibling_ui or {}).get("overrides", {}).get("setupUI", {}).get(
            "signature", "protected void setupUI()")

        body_lines = None
        if sibling_ui:
            body = _find_method_body(sibling_ui["text"], "setupUI")
            if body and "ResourceMgr.getString(" in sibling_ui["text"][body[0]:body[1]]:
                body_lines = self._transplant_setup(sibling_ui["text"][body[0]:body[1]], sibling_ui["name"],
                                                    sibling["name"], spec, cs)
                imp.use_types_in("\n".join(body_lines))
        if body_lines is None:
            def key(k: str) -> str:
                return f"ResourceMgr.getString({ui}.class, {_java_str(f'{ui}.{k}')})"
            body_lines = [f"        setName({key('name.decl')});",
                          f"        setShortDescription({key('shortDesc.decl')});",
                          f"        setLongDescription({key('longDesc.decl')});"]
            if spec.mnemonic:
                body_lines.append(f"        setMnemonic({key('mnemonic')}.charAt(0));")
            if spec.accelerator:
                imp.use("KeyStroke", "javax.swing.KeyStroke")
                body_lines.append(f"        setAccelerator(KeyStroke.getKeyStroke({_java_str(spec.accelerator)}));")
            if spec.icon:
                body_lines.append(f"        setActiveIcon({_java_str(spec.icon)});")
            if spec.icon_inactive:
                body_lines.append(f"        setInactiveIcon({_java_str(spec.icon_inactive)});")
            cs["todos"].append(f"{ui}: setupUI() written from the default pattern (no sibling UI using "
                               "ResourceMgr) - verify the ActionUI setter names.")

        keys: Dict[str, str] = {}
        for k in re.findall(r'"(' + re.escape(ui) + r'\.[\w.]+)"', "\n".join(body_lines)):
            suffix = k[len(ui) + 1:].lower()
            if "mnemonic" in suffix:
                value = spec.mnemonic
            elif "tooltip" in suffix or "tip" in suffix:
                value = spec.tooltip
            elif "short" in suffix:
                value = spec.short_desc
            elif "long" in suffix:
                value = spec.long_desc
            elif "name" in suffix or "label" in suffix:
                value = spec.label
            else:
                value = spec.label
                cs["todos"].append(f"Resource key {k} has no mapped spec field; the label was used as its value.")
            if value:
                keys[k] = value

        apps = ",\n".join(f"        Application.{a}" for a in spec.applications or [])
        L = [f"package {spec.package};", "", "@@IMPORTS@@", "", "/**",
             f" * UI metadata for {{@link {spec.action_name}}}. Generated by CopilotLens.", " */",
             "@ApplicationSpecification(", "    includeIn = {", apps, "    },",
             f"    immersedMode = ApplicationSpecification.ImmersedMode.{spec.immersed_mode}", ")"]
        if spec.enabled("immersed"):
            imp.use("ImmersedAction")
            words = ".".join(w.lower() for w in _camel_words(spec.action_name))
            im = spec.immersed
            L += ["@ImmersedAction(", f"    actionId = {_java_str(im['action_id'])},",
                  f"    label = {_java_str(im.get('label_key') or f'capital.{words}.label')},",
                  f"    tooltip = {_java_str(im.get('tooltip_key') or f'capital.{words}.tooltip')},",
                  f"    icon = {_java_str(im.get('icon') or spec.icon or '')},",
                  f"    buttonStyle = {_java_str(im['button_style'])}", ")"]
        L += [f"public class {ui} extends ActionUI", "{",
              f"    public {ui}(@NotNull {ctor_type} {ctor_param})", "    {", f"        super({ctor_param});", "    }", "",
              "    @Override", "    public String getActionClass()", "    {",
              f"        return {spec.action_name}.class.getName();", "    }", "",
              "    @Override", f"    {setup_sig}", "    {"] + body_lines + ["    }", "}", ""]
        if imp.unresolved:
            cs["warnings"].append(f"{ui}: unresolved imports {sorted(imp.unresolved)}")
        return "\n".join(L).replace("@@IMPORTS@@", imp.render()), keys

    @staticmethod
    def _transplant_setup(body: str, sib_ui: str, sib_action: str, spec: ActionSpec, cs) -> List[str]:
        """Reuse the sibling's setupUI() statements with names, keys, icons and accelerator replaced."""
        text = re.sub(r"\b" + re.escape(sib_ui) + r"\b", spec.ui_name, body)
        text = re.sub(r"\b" + re.escape(sib_action) + r"\b", spec.action_name, text)
        out: List[str] = []
        for line in text.replace("\r", "").split("\n"):
            if not line.strip():
                continue
            low = line.lower()
            literal = re.search(r'"(?:\\.|[^"\\])*"', line)
            if "accelerator" in low or "keystroke" in low:
                if not spec.accelerator:
                    continue
                if literal:
                    line = line[:literal.start()] + _java_str(spec.accelerator) + line[literal.end():]
                else:
                    indent = re.match(r"\s*", line).group(0)
                    out.append(f"{indent}// TODO(accelerator): apply {spec.accelerator!r} using the sibling "
                               "pattern below.")
                    line = f"{indent}// {line.strip()}"
                    cs["todos"].append(f"{spec.ui_name}: set accelerator {spec.accelerator!r}.")
            elif "mnemonic" in low and not spec.mnemonic:
                continue
            elif "icon" in low:
                inactive = "inactive" in low or "disabled" in low
                value = spec.icon_inactive if inactive else spec.icon
                if not value:
                    continue
                if literal:
                    line = line[:literal.start()] + _java_str(value) + line[literal.end():]
                else:
                    cs["todos"].append(f"{spec.ui_name}: icon line copied from {sib_ui} without a literal - "
                                       f"verify: {line.strip()}")
            elif literal and "ResourceMgr" not in line:
                cs["todos"].append(f"{spec.ui_name}: literal copied from {sib_ui} - verify: {line.strip()}")
            out.append(line)
        return out

    def _render_test(self, spec, index, sibling, local, keys, cs) -> str:
        imp = _Imports(index, spec.package, local)
        base = spec.test_base
        if not base and sibling:
            sib_test = index.tests_dir / f"{sibling['name']}Test.java"
            if sib_test.is_file():
                base = _class_decl(_read(sib_test)[0])[1]
        base = base or "LogicTestCase"
        for simple in (base, "AIGenerated", "ResourceMgr"):
            imp.use(simple)
        L = [f"package {spec.package};", "", "@@IMPORTS@@", "", "/**",
             f" * Tests for {{@link {spec.action_name}}} and {{@link {spec.ui_name}}}.", " * <p>",
             f" * Generated JUnit 3 scaffold on {base}. Scenarios calling fail(\"TODO...\") must be implemented",
             " * with factory/builder-created Logic objects (no Mockito; JMockit only as a last resort).",
             " * Mutating scenarios must run in READ_WRITE operation mode.", " */", "@AIGenerated",
             f"public class {spec.test_name} extends {base}", "{",
             f"    public {spec.test_name}(String name)", "    {", "        super(name);", "    }", "",
             "    @Override", "    protected void setUp() throws Exception", "    {", "        super.setUp();",
             "        // TODO(test): create the Logic design and selection with factories/builders.", "    }", "",
             "    @Override", "    protected void tearDown() throws Exception", "    {", "        try", "        {",
             "            // TODO(test): release fixtures created in setUp().", "        }", "        finally",
             "        {", "            super.tearDown();", "        }", "    }", "",
             "    @AIGenerated", "    public void testResourceKeysResolve()", "    {", "        String[] keys = {"]
        L += [f"            {_java_str(k)}," for k in keys]
        L += ["        };", "        for (String key : keys)", "        {",
              f"            assertNotNull(key, ResourceMgr.getString({spec.ui_name}.class, key));", "        }",
              "    }", ""]
        used = {"testResourceKeysResolve"}
        for scenario in spec.all_test_scenarios():
            method = "test" + "".join(w[:1].upper() + w[1:] for w in re.findall(r"[A-Za-z0-9]+", scenario))
            if method in used:
                continue
            used.add(method)
            L += ["    @AIGenerated", f"    public void {method}()", "    {"]
            if spec.mutates_model and any(w in scenario.lower() for w in ("undo", "performs", "mutate")):
                L.append("        // Run in READ_WRITE operation mode.")
            L += [f"        fail({_java_str('TODO(test): ' + scenario)});", "    }", ""]
        L += ["}", ""]
        cs["todos"].append(f"{spec.test_name}: implement {len(used) - 1} scenario tests (they fail until done).")
        if imp.unresolved:
            cs["warnings"].append(f"{spec.test_name}: unresolved imports {sorted(imp.unresolved)}")
        return "\n".join(L).replace("@@IMPORTS@@", imp.render())

    # ── patching ────────────────────────────────────────────────────────────
    @staticmethod
    def _patch_controller(text: str, spec: ActionSpec, method: str,
                          cfg: Dict[str, Any]) -> Tuple[str, Optional[str], Optional[str]]:
        name = spec.action_name
        if re.search(r"\bnew\s+" + re.escape(name) + r"\s*\(", text):
            return text, f"{name} is already registered", None
        body = _find_method_body(text, method)
        if not body:
            return text, f"{method}() not found", None
        nl = _nl(text)
        b0, b1 = body
        segment = text[b0:b1]
        after, cond = cfg.get("insert_after"), cfg.get("condition")
        if after:
            m = re.search(r"^[^\n]*\baddAction\(\s*new\s+" + re.escape(after) + r"\s*\([^\n]*$", segment, re.M)
            if not m:
                return text, f"{after} is not registered in {method}()", None
            indent = _indent_at(text, b0 + m.start())
            insert_at = _line_end(text, b0 + m.end())
        else:
            regs = [r for r in re.finditer(r"^[^\n]*\baddAction\(", segment, re.M)
                    if _enclosing_condition(text, b0, b0 + r.start()) is None]   # top-level statements only
            indent = _indent_at(text, b0 + regs[-1].start()) if regs else _indent_at(text, b0 - 1) + "    "
            insert_at = _line_start(text, b1)
        stmt = f"addAction(new {name}(this));"
        block = (f"{indent}if ({cond}){nl}{indent}{{{nl}{indent}    {stmt}{nl}{indent}}}{nl}"
                 if cond else f"{indent}{stmt}{nl}")
        inherited = _enclosing_condition(text, b0, insert_at)
        text = text[:insert_at] + block + text[insert_at:]
        if _package_of(text) != spec.package:
            text = _add_import(text, spec.fqn)
        note = f"Controller registration inherits the enclosing condition: {inherited}" if inherited else None
        return text, None, note

    @staticmethod
    def _insert_after_last(text: str, pattern: str, lines: List[str]) -> Optional[str]:
        matches = list(re.finditer(pattern, text, re.M))
        if not matches:
            return None
        m = matches[-1]
        indent = _indent_at(text, m.start())
        nl = _nl(text)
        pos = _line_end(text, m.end())
        return text[:pos] + "".join(f"{indent}{ln}{nl}" for ln in lines) + text[pos:]

    def _patch_resource(self, text: str, spec: ActionSpec, res: Dict[str, Any]) -> Tuple[str, List[str], List[str]]:
        errors: List[str] = []
        notes: List[str] = []
        ui, rb, cv = spec.ui_name, res["rb"], res["caplet_var"]
        if re.search(r"\b" + re.escape(ui) + r"\b", text):
            return text, [f"{ui} is already referenced"], notes
        nl = _nl(text)
        if spec.init_in_init_actions:
            body = _find_method_body(text, "initActions")
            if not body:
                errors.append("initActions() not found")
            else:
                stmts = list(re.finditer(r"^[ \t]*\S[^\n]*;", text[body[0]:body[1]], re.M))
                indent = _indent_at(text, body[0] + stmts[-1].start()) if stmts else \
                    _indent_at(text, body[0] - 1) + "    "
                pos = _line_start(text, body[1])
                text = text[:pos] + f"{indent}new {ui}({cv});{nl}" + text[pos:]

        if spec.enabled("menu"):
            var = spec.menu["menu_var"]
            lines: List[str] = []
            if spec.menu.get("separator_before"):
                if res["separator_method"]:
                    lines.append(f"{rb}.{res['separator_method']}({var});")
                else:
                    lines.append(f"// TODO(menu): add a separator before {ui} (no separator call found).")
                    notes.append(f"LogicResource: add the separator before {ui} manually.")
            lines.append(f"{rb}.addActionUI(new {ui}({cv}), {var});")
            if spec.menu.get("label_override"):
                notes.append(f"LogicResource: menu label override {spec.menu['label_override']!r} requested - no "
                             "existing override pattern found, apply it manually.")
            if var not in res["menus"]:
                parent = spec.menu["parent_menu_var"]
                decl = [ln.strip() for ln in spec.menu["new_submenu_declaration"].splitlines() if ln.strip()]
                pattern = r"^[^\n]*\.addActionUI\([^\n]*,\s*" + re.escape(parent) + r"\s*\)\s*;[^\n]*$"
                new = self._insert_after_last(text, pattern, decl + lines)
            else:
                after = spec.menu.get("insert_after")
                if after:
                    pattern = (r"^[^\n]*\.addActionUI\(\s*new\s+" + re.escape(after) + r"\s*\([^\n]*,\s*"
                               + re.escape(var) + r"\s*\)\s*;[^\n]*$")
                else:
                    pattern = r"^[^\n]*\.addActionUI\([^\n]*,\s*" + re.escape(var) + r"\s*\)\s*;[^\n]*$"
                new = self._insert_after_last(text, pattern, lines)
            if new is None:
                errors.append(f"No anchor registration found for menu {var!r}"
                              + (f" after {spec.menu.get('insert_after')}" if spec.menu.get("insert_after") else ""))
            else:
                text = new

        if spec.enabled("toolbar"):
            var = spec.toolbar["toolbar_var"]
            pattern = r"^[^\n]*\.addActionUIEntry\([^\n]*,\s*" + re.escape(var) + r"\s*\)\s*;[^\n]*$"
            new = self._insert_after_last(text, pattern, [f"{rb}.addActionUIEntry({ui}.class, {var});"])
            if new is None:
                errors.append(f"No anchor registration found for toolbar {var!r}")
            else:
                text = new
        if _package_of(text) != spec.package:
            text = _add_import(text, spec.ui_fqn)
        return text, errors, notes

    @staticmethod
    def _patch_properties(text: str, entries: Dict[str, Optional[str]], header: str,
                          l10n_todo: bool = False) -> Tuple[str, List[str]]:
        existing = _prop_keys(text)
        errors: List[str] = []
        lines: List[str] = []
        for key, value in entries.items():
            if value is None:
                continue
            escaped = _prop_escape(value)
            if key in existing:
                if existing[key] != escaped:
                    errors.append(f"Resource key {key} already exists with a different value")
                continue
            if l10n_todo:
                lines.append("# TODO(l10n): translate")
            lines.append(f"{key}={escaped}")
        if not lines:
            return text, errors
        nl = _nl(text) if text else "\n"
        prefix = "" if not text or text.endswith("\n") else nl
        block = nl.join([f"# --- {header} (generated by CopilotLens) ---"] + lines) + nl
        return text + prefix + nl + block, errors

    @staticmethod
    def _patch_ribbon(rib: Dict[str, Any], spec: ActionSpec,
                      index: LogicRepoIndex) -> Tuple[bytes, List[str], List[str]]:
        data, enc = rib["data"], rib["encoding"]
        nl = "\r\n" if b"\r\n" in data else "\n"
        errors: List[str] = []
        notes: List[str] = []
        inserts: List[Tuple[int, bytes]] = []
        vis_cfg = spec.ribbon.get("visibility") or {}
        for pl in spec.ribbon["placements"]:
            group, err = index.find_ribbon_group(pl.get("group", ""))
            if err:
                errors.append(err)
                continue
            if any(b["target"] == spec.ui_fqn for b in group["buttons"]):
                errors.append(f"{spec.ui_fqn} is already in ribbon group {group['path']}")
                continue
            anchor = group["buttons"][-1]
            wanted = pl.get("insert_after_target")
            if wanted:
                match = [b for b in group["buttons"] if b["target"] and
                         (b["target"] == wanted or b["target"].endswith("." + wanted))]
                if not match:
                    errors.append(f"insert_after_target {wanted!r} not found in {group['path']}")
                    continue
                anchor = match[0]
            x, y = pl.get("x"), pl.get("y")
            if x is None or y is None:
                x = anchor["x"] if x is None else x
                if y is None:
                    ys = sorted({b["y"] for b in group["buttons"] if b["x"] == x and b["y"] is not None})
                    steps = [b - a for a, b in zip(ys, ys[1:]) if b > a]
                    step = min(steps) if steps else 1
                    y = anchor["y"] if anchor["x"] == x and anchor["y"] is not None else (ys[-1] if ys else -step)
                    y += step
                    while y in ys:                       # first free slot after the anchor
                        y += step
                x = 0 if x is None else x
                notes.append(f"Ribbon x/y proposed as ({x}, {y}) in {group['path']} - verify the layout.")
            ind = anchor["indent"]
            attrs = [("help-id", spec.help_id), ("icon", spec.ribbon.get("icon") or ""), ("name", spec.label),
                     ("target", spec.ui_fqn), ("text", f"ribbon.button.{spec.action_name}.text"),
                     ("tooltip", f"ribbon.button.{spec.action_name}.tooltip"), ("x", str(x)), ("y", str(y))]
            lines = [f"{ind}<button"] + [f"{ind}    {k}={quoteattr(v)}" for k, v in attrs]
            lines[-1] += ">"
            if spec.ribbon.get("copy_visibility_from_anchor") and anchor["visibility"]:
                s, e = anchor["visibility"]
                lines.append(data[s:e].decode(enc).rstrip())
            else:
                lines.append(f"{ind}    <visibility>")
                for app in vis_cfg.get("applications") or []:
                    lines.append(f"{ind}        <application name={quoteattr(app)}/>")
                if vis_cfg.get("project_open") is not None:
                    lines.append(f"{ind}        <project open=\"{str(bool(vis_cfg['project_open'])).lower()}\"/>")
                lines += [f"{ind}        {c}" for c in vis_cfg.get("conditions") or []]
                lines.append(f"{ind}    </visibility>")
            lines.append(f"{ind}</button>")
            inserts.append((anchor["end"], (nl + nl.join(lines)).encode(enc)))
        for pos, chunk in sorted(inserts, key=lambda t: t[0], reverse=True):
            data = data[:pos] + chunk + data[pos:]
        return data, errors, notes

    # ── validation / build / report ─────────────────────────────────────────
    @staticmethod
    def _validate(spec, index, cs, entries, ribbon_keys, bundle) -> List[Dict[str, str]]:
        results: List[Dict[str, str]] = []

        def check(name: str, ok: bool, detail: str, severity: str = "fail") -> None:
            results.append({"check": name, "status": "pass" if ok else severity, "detail": detail})

        files = {index.rel(p): e["new"] for p, e in cs["files"].items()}
        action = files.get(index.rel(index.package_dir / f"{spec.action_name}.java"), "")
        ui = files.get(index.rel(index.package_dir / f"{spec.ui_name}.java"), "")
        check("ui_action_mapping", f"{spec.ui_name}.class" in action and f"{spec.action_name}.class" in ui,
              "getActionUIClass() and getActionClass() reference each other")

        for rel, content in files.items():
            if rel.endswith(".java"):
                check(f"braces_balanced:{rel}", _braces_balanced(content), "Java braces balanced")

        if bundle:
            keys = _prop_keys(files.get(index.rel(bundle), ""))
            referenced = set(re.findall(r'ResourceMgr\.getString\(\s*\w+\.class\s*,\s*"([^"]+)"\)', action + ui))
            referenced |= {k for k, v in entries.items() if v is not None}
            missing = sorted(k for k in referenced if k not in keys)
            check("resource_keys_resolve", not missing, f"missing: {missing}" if missing else
                  f"{len(referenced)} keys present in {index.rel(bundle)}")

        if spec.enabled("ribbon"):
            rib = index.ribbon()
            rib_rel = index.rel(rib["path"])
            try:
                ET.fromstring(files.get(rib_rel, "").encode(rib["encoding"]))
                check("ribbon_xml_well_formed", True, rib_rel)
            except ET.ParseError as exc:
                check("ribbon_xml_well_formed", False, str(exc))
            rbundle = index.ribbon_bundle()
            if rbundle:
                keys = _prop_keys(files.get(index.rel(rbundle), ""))
                missing = [k for k in ribbon_keys if k not in keys]
                check("ribbon_keys_resolve", not missing, f"missing: {missing}" if missing else "ribbon keys present")

        icons = [("icon", spec.icon), ("icon_inactive", spec.icon_inactive)]
        if spec.enabled("ribbon"):
            icons.append(("ribbon.icon", spec.ribbon.get("icon")))
        if spec.enabled("immersed"):
            icons.append(("immersed.icon", spec.immersed.get("icon")))
        for label, name in icons:
            if not name:
                continue
            found = index.find_icon(name)
            check(f"icon_exists:{label}", bool(found), ", ".join(found[:3]) if found else
                  f"{name!r} not found under {index.layout.get('icon_roots')}",
                  "warn" if spec.allow_missing_icons else "fail")
            if found and not index.hidpi_variants(name):
                results.append({"check": f"icon_hidpi:{label}", "status": "warn",
                                "detail": f"no high-DPI variant found for {name!r}"})

        if cs["localization"]:
            pending = [loc for loc in cs["localization"] if loc["status"] == "translation required"]
            results.append({"check": "localization", "status": "warn" if pending else "pass",
                            "detail": "; ".join(f"{loc['bundle']}: {loc['status']} for {len(loc['locales'])} locales"
                                                for loc in cs["localization"])})
        for warning in cs["warnings"]:
            if "unresolved imports" in warning:
                results.append({"check": "imports", "status": "warn", "detail": warning})
        return results

    @staticmethod
    def _run_build(root: Path, record: Dict[str, Any]) -> List[Dict[str, str]]:
        results: List[Dict[str, str]] = []
        for step, env in (("build", "CAPITAL_BUILD_CMD"), ("test", "CAPITAL_TEST_CMD")):
            cmd = os.environ.get(env)
            if not cmd:
                results.append({"step": step, "status": "skipped", "detail": f"set ${env} to enable"})
                continue
            cmd = cmd.replace("{test_class}", record["test_class"]).replace("{test_fqn}", record["test_fqn"])
            try:
                proc = subprocess.run(cmd, shell=True, cwd=str(root), capture_output=True, text=True, timeout=1800)
                results.append({"step": step, "status": "pass" if proc.returncode == 0 else "fail",
                                "detail": (proc.stdout + proc.stderr)[-4000:]})
            except subprocess.TimeoutExpired:
                results.append({"step": step, "status": "fail", "detail": "timed out after 30 minutes"})
            if results[-1]["status"] == "fail":
                break
        return results

    @staticmethod
    def _report(record: Dict[str, Any], status: str) -> str:
        icon = {"pass": "✅", "warn": "⚠️", "fail": "❌", "skipped": "⏭️"}
        out = [f"# Logic Action Change Set — `{record['action']}`", "",
               f"**Status:** {status}  |  **Change set:** `{record['id']}`  |  **Capital repo:** "
               f"`{record['capital_repo']}`", "", "## Files"]
        for f in record["files"]:
            added = sum(1 for ln in f["diff"].splitlines() if ln.startswith("+") and not ln.startswith("+++"))
            out.append(f"- **{f['action']}** `{f['path']}` (+{added} lines)")
        out += ["", "## Validation"]
        out += [f"- {icon.get(v['status'], '•')} **{v['check']}** — {v['detail']}" for v in record["validation"]]
        if record.get("build"):
            out += ["", "## Build / tests"]
            out += [f"- {icon.get(b['status'], '•')} **{b['step']}** — {b['detail'][-300:]}" for b in record["build"]]
        out += ["", "## Unresolved decisions (TODO in generated code)"]
        out += [f"- {t}" for t in record["todos"]] or ["- none"]
        if record["localization"]:
            out += ["", "## Localization"]
            for loc in record["localization"]:
                out.append(f"- `{loc['bundle']}` — {loc['status']}: {', '.join(loc['locales'])} "
                           f"(keys: {', '.join(loc['keys'])})")
        if record["warnings"]:
            out += ["", "## Notes"] + [f"- {w}" for w in record["warnings"]]
        return "\n".join(out)




