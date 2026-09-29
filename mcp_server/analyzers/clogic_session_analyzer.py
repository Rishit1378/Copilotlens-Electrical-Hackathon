"""
CopilotLens Live CLogic & CManager Session Interceptor
Monitors active CLogic GUI actions (placing devices, routing wires, connecting pins),
evaluates design integrity on placed objects, suggests logical next placement steps,
and generates step-by-step bug reproduction procedures.
"""

from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Any, Optional
import xml.etree.ElementTree as ET
import os
import re
import threading
import time


class CLogicSessionAnalyzer:
    """Intersects and evaluates active CLogic client session events and design state."""

    def __init__(self, repo_path: str, xml_analyzer=None, drc_validator=None):
        self.repo_path = Path(repo_path)
        self.xml_analyzer = xml_analyzer
        self.drc_validator = drc_validator
        self._monitor_lock = threading.RLock()
        self._poll_lock = threading.Lock()
        self._monitor_stop = threading.Event()
        self._monitor_thread = None
        self._monitor_target = None
        self._poll_interval = 2.0
        self._last_poll_at = None
        self._last_error = None
        self._current_design = None
        self._current_source = None
        self._file_signatures = {}
        self._log_offsets = {}
        self._events = deque(maxlen=200)

    def inspect_live_session(self, target_xml_or_session: str = None) -> Dict[str, Any]:
        """
        Inspect one supplied snapshot, or return the latest state/deltas from the
        background poller. Live monitoring is best-effort file/log polling, not a
        native CLogic event hook; see monitor_diagnostics in the response.
        """
        if target_xml_or_session:
            xml_content, source_name, error = self._read_explicit_input(target_xml_or_session)
            if error:
                return {"error": True, "reason": error}
            state = self._analyze_snapshot(xml_content, source_name)
            if state.get("error"):
                return state
            state["change_events"] = []
            state["monitoring"] = False
            return state

        self.start_monitoring()
        self._poll_once()
        with self._monitor_lock:
            current = dict(self._current_design) if self._current_design else None
            new_events = [dict(e) for e in self._events if e["sequence"] > getattr(self, "_last_reported_sequence", 0)]
            if new_events:
                self._last_reported_sequence = new_events[-1]["sequence"]
            diagnostics = self._monitor_diagnostics()

        if current is None:
            return {
                "error": False,
                "monitoring": True,
                "session_source": None,
                "session_detected": False,
                "message": "Monitoring is running, but no readable live design XML snapshot has been found yet.",
                "placed_objects_summary": {},
                "placed_entities": [],
                "change_events": new_events,
                "log_events": self._recent_log_events(),
                "recommended_next_steps": ["Open or create a CLogic design and make a change; this monitor detects workspace XML/log file updates."],
                "bug_reproduction_procedure": [],
                "monitor_diagnostics": diagnostics,
            }

        current.update({
            "monitoring": True,
            "session_detected": True,
            "change_events": new_events,
            "log_events": self._recent_log_events(),
            "monitor_diagnostics": diagnostics,
        })
        return current

    def _read_explicit_input(self, target: str):
        if "<" in target:
            return target, "inline_xml", None
        path = Path(target).expanduser()
        if not path.is_absolute():
            path = self.repo_path / path
        try:
            return path.read_text(encoding="utf-8", errors="replace"), path.name, None
        except OSError as exc:
            return None, None, f"Could not read XML/session path '{path}': {exc}"

    def _analyze_snapshot(self, xml_content: str, source_name: str) -> Dict[str, Any]:
        try:
            root = ET.fromstring(xml_content)
        except ET.ParseError as exc:
            return {"error": True, "reason": f"XML Parse Error: {exc}"}

        placed = self._extract_placed_objects(root)
        drc_eval = self.drc_validator.validate_drc(xml_content) if self.drc_validator else {}
        if drc_eval and not drc_eval.get("error"):
            drc_eval["note"] = "CopilotLens XML heuristic preflight; this is not a native CLogic/CManager DRC run."
        return {
            "session_source": source_name,
            "placed_objects_summary": placed["summary"],
            "placed_entities": placed["entities"],
            "live_drc_evaluation": drc_eval,
            "recommended_next_steps": self._suggest_next_placement_steps(placed),
            "bug_reproduction_procedure": self._generate_bug_reproduction_steps(placed),
        }

    def start_monitoring(self, target_dir: str = None, poll_interval: float = None) -> Dict[str, Any]:
        """Start best-effort local file polling; safe to call more than once."""
        with self._monitor_lock:
            if target_dir:
                self._monitor_target = Path(target_dir).expanduser()
            if poll_interval is not None:
                self._poll_interval = max(0.5, min(float(poll_interval), 60.0))
            self._monitor_stop.clear()
            if self._monitor_thread and self._monitor_thread.is_alive():
                return {"running": True, "already_running": True}
            self._monitor_thread = threading.Thread(
                target=self._monitor_loop,
                name="copilotlens-clogic-session-monitor",
                daemon=True,
            )
            self._monitor_thread.start()
        return {"running": True, "poll_interval_seconds": self._poll_interval}

    def stop_monitoring(self) -> Dict[str, Any]:
        """Stop the background poller (primarily useful in tests/shutdown)."""
        self._monitor_stop.set()
        thread = self._monitor_thread
        if thread and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=2.0)
        return {"running": bool(thread and thread.is_alive())}

    def _monitor_loop(self):
        while not self._monitor_stop.is_set():
            try:
                self._poll_once()
            except Exception as exc:  # keep monitoring if a file is transiently locked/partial
                with self._monitor_lock:
                    self._last_error = str(exc)
            self._monitor_stop.wait(self._poll_interval)

    def _workspace_dirs(self) -> List[Path]:
        candidates = []
        if self._monitor_target:
            candidates.append(self._monitor_target)
        configured = os.environ.get("CLOGIC_SESSION_DIR")
        if configured:
            candidates.append(Path(configured).expanduser())
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            candidates.append(Path(local_app_data) / "Temp" / "chs_workspace")
        return list(dict.fromkeys(p for p in candidates if p.exists() and p.is_dir()))

    def _snapshot_candidates(self) -> List[Path]:
        configured_file = os.environ.get("CLOGIC_SESSION_XML")
        candidates = [Path(configured_file).expanduser()] if configured_file else []
        for directory in self._workspace_dirs():
            try:
                candidates.extend(directory.rglob("*.xml"))
            except OSError:
                continue
        valid = []
        for path in set(candidates):
            try:
                if path.is_file() and path.stat().st_size <= 50 * 1024 * 1024:
                    valid.append(path)
            except OSError:
                continue
        return sorted(valid, key=lambda p: p.stat().st_mtime_ns, reverse=True)

    def _log_candidates(self) -> List[Path]:
        candidates = []
        for env_name in ("CLOGIC_LOG_PATH", "CMANAGER_LOG_PATH"):
            if os.environ.get(env_name):
                candidates.append(Path(os.environ[env_name]).expanduser())
        for directory in self._workspace_dirs():
            for pattern in ("*cmanager*.log", "*clogic*.log", "*.log"):
                candidates.extend(directory.glob(pattern))
        candidates.append(self.repo_path / "chs_home" / "logs" / "cmanager.log")
        result = []
        for path in dict.fromkeys(candidates):
            try:
                if path.is_file() and path.stat().st_size <= 100 * 1024 * 1024:
                    result.append(path)
            except OSError:
                pass
        return result

    def _poll_once(self):
        with self._poll_lock:
            self._poll_once_locked()

    def _poll_once_locked(self):
        now = datetime.now(timezone.utc).isoformat()
        for path in self._log_candidates():
            self._read_log_delta(path, now)

        candidates = self._snapshot_candidates()
        if candidates:
            snapshot_path = candidates[0]
            try:
                stat = snapshot_path.stat()
                signature = (stat.st_mtime_ns, stat.st_size)
                previous_signature = self._file_signatures.get(str(snapshot_path))
                if previous_signature != signature:
                    content = snapshot_path.read_text(encoding="utf-8", errors="replace")
                    analyzed = self._analyze_snapshot(content, snapshot_path.name)
                    if not analyzed.get("error"):
                        self._record_snapshot(analyzed, str(snapshot_path), signature, now)
                    else:
                        with self._monitor_lock:
                            self._last_error = analyzed.get("reason")
            except (OSError, ET.ParseError) as exc:
                with self._monitor_lock:
                    self._last_error = f"Could not read live snapshot {snapshot_path}: {exc}"
        with self._monitor_lock:
            self._last_poll_at = now
            self._last_error = None if candidates and self._current_design else self._last_error

    def _record_snapshot(self, analyzed: Dict[str, Any], source_path: str, signature, observed_at: str):
        new_entities = analyzed.get("placed_entities", [])
        with self._monitor_lock:
            old_entities = self._current_design.get("placed_entities", []) if self._current_design else []
            old_by_key = {self._entity_key(e): e for e in old_entities}
            new_by_key = {self._entity_key(e): e for e in new_entities}
            if not self._current_design:
                self._append_event("snapshot_loaded", f"Loaded design snapshot with {len(new_entities)} detected objects.", observed_at)
            else:
                for key, entity in new_by_key.items():
                    if key not in old_by_key:
                        self._append_event("object_added", f"Detected {entity['type']} {entity['name']}.", observed_at, entity)
                    elif entity != old_by_key[key]:
                        self._append_event("object_changed", f"Detected change to {entity['type']} {entity['name']}.", observed_at, entity)
                for key, entity in old_by_key.items():
                    if key not in new_by_key:
                        self._append_event("object_removed", f"Detected removal of {entity['type']} {entity['name']}.", observed_at, entity)
            self._current_design = analyzed
            self._current_design["snapshot_path"] = source_path
            self._current_design["last_updated"] = observed_at
            self._current_source = source_path
            self._file_signatures[source_path] = signature
            self._last_error = None

    @staticmethod
    def _entity_key(entity: Dict[str, Any]) -> str:
        return f"{entity.get('type')}:{entity.get('id') or entity.get('name')}"

    def _read_log_delta(self, path: Path, observed_at: str):
        try:
            size = path.stat().st_size
            key = str(path)
            offset = self._log_offsets.get(key)
            if offset is None or size < offset:
                offset = max(0, size - 32768)
            with path.open("rb") as stream:
                stream.seek(offset)
                chunk = stream.read(256 * 1024)
                new_offset = stream.tell()
            self._log_offsets[key] = new_offset
            for line in chunk.decode("utf-8", errors="replace").splitlines():
                if not line.strip():
                    continue
                lowered = line.lower()
                if not re.search(r"device|connector|pin|wire|conductor|backshell|splice|drc|undo|redo|error|exception|placed|routing|connect", lowered):
                    continue
                kind = "log_activity"
                for keyword, event_type in (("error", "log_error"), ("exception", "log_error"), ("drc", "drc_activity"),
                                            ("undo", "undo_activity"), ("redo", "redo_activity"), ("device", "device_activity"),
                                            ("connector", "connector_activity"), ("wire", "wire_activity"), ("pin", "pin_activity")):
                    if keyword in lowered:
                        kind = event_type
                        break
                self._append_event(kind, line.strip()[:300], observed_at, {"log_file": path.name})
        except OSError as exc:
            with self._monitor_lock:
                self._last_error = f"Could not read log {path}: {exc}"

    def _append_event(self, kind: str, message: str, observed_at: str, details: Dict[str, Any] = None):
        with self._monitor_lock:
            sequence = self._events[-1]["sequence"] + 1 if self._events else 1
            event = {"sequence": sequence, "timestamp": observed_at, "type": kind, "message": message}
            if details:
                event["details"] = details
            self._events.append(event)

    def _recent_log_events(self) -> List[Dict[str, Any]]:
        with self._monitor_lock:
            return [dict(event) for event in self._events if event["type"].startswith("log_") or event["type"].endswith("_activity")][-25:]

    def _monitor_diagnostics(self) -> Dict[str, Any]:
        with self._monitor_lock:
            thread = self._monitor_thread
            return {
                "running": bool(thread and thread.is_alive()),
                "poll_interval_seconds": self._poll_interval,
                "workspace_directories": [str(path) for path in self._workspace_dirs()],
                "snapshot_source": self._current_source,
                "last_poll_at": self._last_poll_at,
                "last_error": self._last_error,
                "events_buffered": len(self._events),
                "watched_log_files": list(self._log_offsets),
                "input_config": ["CLOGIC_SESSION_DIR", "CLOGIC_SESSION_XML", "CLOGIC_LOG_PATH", "CMANAGER_LOG_PATH"],
            }

    def _extract_placed_objects(self, root: ET.Element) -> Dict[str, Any]:
        """Extract actual connectivity instances, not project preferences/symbol glyphs."""
        connectivity = next((e for e in root.iter() if self._tag(e) == "connectivity"), None)
        scope_root = connectivity if connectivity is not None else root
        scope = list(scope_root.iter())
        parents = {child: parent for parent in scope for child in parent}
        entities = []
        counts = {
            "devices": 0, "device_connectors": 0, "connectors": 0,
            "wires": 0, "backshells": 0, "terminations": 0,
            "pins": 0, "splices": 0, "cavity_seals": 0,
        }
        type_by_tag = {
            "device": ("DEVICE", "devices"),
            "deviceconnector": ("DEVICE_CONNECTOR", "device_connectors"),
            "connector": ("CONNECTOR", "connectors"),
            "plugconnector": ("PLUG_CONNECTOR", "connectors"),
            "receptacleconnector": ("RECEPTACLE_CONNECTOR", "connectors"),
            "wireconductor": ("WIRE", "wires"),
            "netconductor": ("NET_CONDUCTOR", "wires"),
            "backshell": ("BACKSHELL", "backshells"),
            "termination": ("TERMINATION", "terminations"),
            "backshelltermination": ("TERMINATION", "terminations"),
            "pin": ("PIN", "pins"),
            "splice": ("SPLICE", "splices"),
            "cavityseal": ("CAVITY_SEAL", "cavity_seals"),
        }
        for elem in scope:
            tag = self._tag(elem)
            definition = type_by_tag.get(tag)
            if not definition:
                continue
            entity_type, count_key = definition
            counts[count_key] += 1
            attrs = elem.attrib
            parent = parents.get(elem)
            record = {
                "type": entity_type,
                "name": attrs.get("name") or attrs.get("refdes") or attrs.get("id") or entity_type,
                "id": attrs.get("id"),
            }
            for key in ("partnumber", "libraryref", "pintype", "sealed", "plugged", "owner", "connref"):
                if attrs.get(key) not in (None, ""):
                    record[key] = attrs[key]
            if parent is not None and self._tag(parent) in ("device", "deviceconnector", "backshell"):
                record["parent"] = parent.attrib.get("name") or parent.attrib.get("id")
            entities.append(record)

        mappings = []
        for elem in scope:
            if self._tag(elem) == "dcpinmap":
                mappings.append({"device_connector_pin": elem.get("dcpin"), "device_pin": elem.get("devpin")})
        return {"summary": counts, "entities": entities[:500], "pin_mappings": mappings}

    @staticmethod
    def _tag(elem: ET.Element) -> str:
        return elem.tag.rsplit("}", 1)[-1].lower() if isinstance(elem.tag, str) else ""

    def _suggest_next_placement_steps(self, placed: Dict[str, Any]) -> List[str]:
        """Suggest the next useful design action from the current connectivity inventory."""
        counts = placed["summary"]
        steps = []
        if counts["devices"] == 0:
            steps.append("Place a device on the design, then add or associate its device connector(s).")
        elif counts["device_connectors"] == 0 and counts["connectors"] == 0:
            steps.append("Add/associate a device connector on the placed device; confirm its pins map to device pins.")
        elif counts["pins"] < 2:
            steps.append("Add or associate the required connector/device pins, then map the connector pins to device pins.")
        elif counts["wires"] == 0:
            steps.append("Connect the intended pins with a wire/conductor; record the source and destination for a reproducible routing test.")
        else:
            steps.append("Run the design's native DRC in CLogic/CManager and capture its results before and after the next change.")
        if counts["backshells"] and counts["terminations"] == 0:
            steps.append("This design has a backshell without a termination; add one if required by the connector scenario.")
        if counts["wires"] > 2 and counts["splices"] == 0:
            steps.append("For a branching harness scenario, add a splice and test connectivity, separation rules, and undo/redo.")
        return steps

    def _generate_bug_reproduction_steps(self, placed: Dict[str, Any]) -> List[str]:
        """Build a practical QA checklist from observed design objects."""
        counts = placed["summary"]
        by_type = {}
        for entity in placed.get("entities", []):
            by_type.setdefault(entity["type"], []).append(entity["name"])
        steps = [
            "Launch CLogic and connect to CManager; open the affected project/design.",
            "Save/export a baseline design snapshot and record the application/build and project version.",
        ]
        for entity_type, verb in (("DEVICE", "Place device(s)"), ("DEVICE_CONNECTOR", "Add device connector(s)"),
                                  ("CONNECTOR", "Add connector(s)"), ("PIN", "Confirm/map pins"),
                                  ("WIRE", "Route wire(s)"), ("BACKSHELL", "Add backshell(s)"),
                                  ("TERMINATION", "Add backshell termination(s)"), ("SPLICE", "Add splice(s)")):
            names = by_type.get(entity_type, [])
            if names:
                steps.append(f"{verb}: {', '.join(names[:10])}.")
        if placed.get("pin_mappings"):
            steps.append(f"Verify the {len(placed['pin_mappings'])} device-connector pin mapping(s) and note expected source/target pins.")
        steps.append("Perform the exact action that triggers the issue; note each click/command and the expected versus actual result.")
        steps.append("Save a post-action snapshot, collect CLogic/CManager logs, run native DRC, and verify undo/redo if relevant.")
        steps.append("Attach before/after snapshots, timestamps, logs, and any DRC output to the bug report.")
        return steps
