"""
CopilotLens XML Design & Scenario Analyzer
Parses Capital XML files (project exports, design actions, schematic definitions),
extracts object hierarchies and connectivity, links them to codebase handling logic,
identifies scenarios, and suggests schema completions/next steps.
"""

from collections import Counter, defaultdict
from io import StringIO
from pathlib import Path
import re
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional


class XmlAnalyzer:
    """Inspect Capital XML exports and explain their contents and likely uses."""

    # XML bookkeeping and drawing primitives are useful in the inventory but are
    # not domain instances; expose them separately from the main object list.
    _INFRA_TAGS = {
        "prefentry", "glyph", "defaultname", "parameter", "objecttypeinfo",
        "point", "attributetext", "ddattribute", "namespace", "xreftextcontainer",
        "xreftext", "designsharedpinusage", "refattachschem", "schempin",
        "designnamemgr", "designsharedusagemgr", "designwideusagemgr",
        "diagramsharedusagemgr", "diagramcontent", "diagramsettings", "diagramsetting",
        "diagramsetting", "extendedattributes", "designtags", "connectivity",
        "polygon", "paramextent", "parameters", "schemdevice", "schemdeviceconnector",
        "logicconnectorcavitywiretabledata", "logicdevicecavitywiretabledata",
        "datadictionary", "fillcolor", "fillforegroundcolor", "color", "grid",
        "opacityconfiguration", "balloonthickness", "decimalformatting", "hwmnamespace",
        "folderpath",
    }
    _DOMAIN_TAGS = {
        "device", "deviceconnector", "connector", "backshell", "termination", "pin",
        "cavity", "cavityseal", "cavityplug", "cavitycomponent", "wireconductor",
        "netconductor", "shieldconductor", "multicore", "splice", "bundle", "overbraid",
        "bundle_ins", "insulation_run", "clip", "grommet", "assembly", "plug",
        "receptacle", "ground", "block", "node", "signal", "inline", "ifconn",
        "virtualconnector", "virtualharness", "harness", "project", "logicaldesign",
        "design", "diagram", "schematic", "dcpinmap", "designusages", "buildlist",
    }
    _REF_RE = re.compile(r"(?:ref|target|owner|parent|baseid)$", re.IGNORECASE)

    def __init__(self, repo_path: str, search_engine=None):
        self.repo_path = Path(repo_path)
        self.search_engine = search_engine

    @staticmethod
    def _local_tag(tag: str) -> str:
        """Return an XML local name, independent of an optional namespace prefix."""
        return tag.rsplit("}", 1)[-1].split(":")[-1]

    _KEY_ATTRS = ("partnumber", "libraryref", "partdesc", "typecode", "typecodedesc", "groupname",
                  "footprintname", "pintype", "issealed", "isplugged", "isgreased")
    _SAMPLE_LIMIT = 25

    def analyze_xml(self, xml_input: str, detail: str = "summary") -> Dict[str, Any]:
        """Return a complete, evidence-bearing analysis for a file or XML string.

        detail="summary" (default) keeps the report compact enough for an LLM tool response;
        detail="full" additionally returns every raw instance, attribute and reference.
        """
        report = self._analyze_full(xml_input)
        if report.get("error"):
            return report
        report["report_markdown"] = self._markdown(report)
        if str(detail).lower() != "full":
            report = self._compact(report)
        # Put the readable report first so it's never lost to truncation.
        return {"report_markdown": report.pop("report_markdown"), **report}

    def _analyze_full(self, xml_input: str) -> Dict[str, Any]:
        xml_path = None
        try:
            if "<" not in xml_input:
                candidate = Path(xml_input)
                if candidate.exists() and candidate.is_file():
                    xml_path = candidate
                elif (self.repo_path / xml_input).is_file():
                    xml_path = self.repo_path / xml_input
        except OSError:
            # Raw XML can be longer than a valid Windows path; parse it as content.
            xml_path = None
        try:
            if xml_path:
                xml_content = xml_path.read_text(encoding="utf-8", errors="replace")
            else:
                xml_content = xml_input
            root = ET.fromstring(xml_content)
        except (ET.ParseError, OSError, ValueError) as exc:
            reason = f"XML parse error: {exc}" if isinstance(exc, ET.ParseError) else str(exc)
            return {"error": True, "reason": reason, "file": str(xml_path or "inline_xml")}

        file_name = xml_path.name if xml_path else "inline_xml"
        elements = list(root.iter())
        id_index = {e.get("id"): e for e in elements if e.get("id")}
        designs = self._find_designs(root)
        report = {
            "file": file_name,
            "document": {
                "root_tag": root.tag,
                "root_attributes": dict(root.attrib),
                "element_count": len(elements),
                "distinct_tag_count": len({e.tag for e in elements}),
                "design_count": len(designs),
                "namespaces": self._namespaces(xml_content),
            },
            "inventory": self._inventory(root),
            "objects": self._objects(root, designs),
            "connections": self._connections(root, id_index),
            "designs": [self._design_summary(d, id_index) for d in designs],
        }
        report["design_comparison"] = self._compare_designs(report["designs"])
        report["related_code_files"] = self._related_files(root, report["objects"])
        report["scenarios"] = self._scenarios(file_name, root, report)
        report["recommendations"] = self._recommendations(report)
        # Keep a small compatibility layer for consumers of the older output.
        report["scenario"] = {**self._identify_scenario(file_name, root, report["objects"]),
                              **report["scenarios"]["primary"]}
        report["objects_inventory"] = report["inventory"]
        report["connectivity_graph"] = report["connections"]
        report["suggestions"] = {
            "suggested_additional_objects": report["recommendations"]["objects_to_consider"],
            "potential_future_scenarios": report["recommendations"]["scenario_ideas"],
        }
        return report

    @staticmethod
    def _namespaces(xml_content: str) -> List[Dict[str, str]]:
        try:
            return [{"prefix": prefix or "default", "uri": uri}
                    for _, (prefix, uri) in ET.iterparse(StringIO(xml_content), events=("start-ns",))]
        except (ET.ParseError, ValueError):
            return []

    @staticmethod
    def _find_designs(root: ET.Element) -> List[ET.Element]:
        designs = [e for e in root.iter() if XmlAnalyzer._local_tag(e.tag).lower() in {"logicaldesign", "design"}]
        # Avoid treating a nested design node as another independent snapshot.
        return [d for d in designs if not any(a in designs for a in list(d.iter())[1:])]

    def _inventory(self, root: ET.Element) -> Dict[str, Any]:
        counts = Counter(self._local_tag(e.tag) for e in root.iter())
        return {
            "total_elements": sum(counts.values()),
            "distinct_tags_count": len(counts),
            "tag_counts": dict(counts.most_common()),
            "domain_tag_counts": {k: v for k, v in counts.items() if k.lower() in self._DOMAIN_TAGS},
            "infrastructure_tag_counts": {k: v for k, v in counts.items() if k.lower() in self._INFRA_TAGS},
        }

    def _objects(self, root: ET.Element, designs: List[ET.Element]) -> Dict[str, Any]:
        records = []
        parents = {id(child): parent for parent in root.iter() for child in parent}
        design_by_element = {
            id(child): design.get("name") or design.get("id")
            for design in designs for child in design.iter()
        }
        for elem in root.iter():
            tag = self._local_tag(elem.tag).lower()
            if tag in self._INFRA_TAGS or tag.endswith("mgr") or tag.endswith("dictionary"):
                continue
            attrs = dict(elem.attrib)
            if not attrs and tag not in self._DOMAIN_TAGS:
                continue
            parent = parents.get(id(elem))
            records.append({
                "tag": elem.tag,
                "id": elem.get("id"),
                "name": elem.get("name"),
                "type": elem.get("type") or elem.get("typename"),
                "attributes": attrs,
                "text": (elem.text or "").strip() or None,
                "parent": self._node_label(parent) if parent is not None else None,
                "design": design_by_element.get(id(elem)),
                "child_tags": [child.tag for child in elem],
            })
        return {
            "count": len(records),
            "by_tag": dict(Counter(self._local_tag(r["tag"]) for r in records)),
            "instances": records,
        }

    @staticmethod
    def _node_label(elem: Optional[ET.Element]) -> Optional[Dict[str, Any]]:
        if elem is None:
            return None
        return {"tag": elem.tag, "id": elem.get("id"), "name": elem.get("name")}

    def _connections(self, root: ET.Element, id_index: Dict[str, ET.Element]) -> Dict[str, Any]:
        links = []
        empty_attributes = []
        unresolved = []
        external = []
        external_ref_names = {"libraryref", "footprintref", "symbolref", "partref", "catalogref"}
        for elem in root.iter():
            for key, value in elem.attrib.items():
                if not self._REF_RE.search(key) or key.lower() in {"id", "baseid"}:
                    continue
                if not value:
                    empty_attributes.append({"source": self._node_label(elem), "attribute": key})
                    continue
                target = id_index.get(value)
                ref_kind = "internal" if target is not None else (
                    "external" if key.lower() in external_ref_names else "unresolved_internal_or_external"
                )
                link = {
                    "source": self._node_label(elem),
                    "attribute": key,
                    "target_id": value,
                    "target": self._node_label(target),
                    "resolution": ref_kind,
                }
                links.append(link)
                if ref_kind == "external":
                    external.append(link)
                elif target is None:
                    unresolved.append(link)
        containment = []
        for elem in root.iter():
            if self._local_tag(elem.tag).lower() in self._DOMAIN_TAGS:
                for child in elem:
                    if self._local_tag(child.tag).lower() in self._DOMAIN_TAGS:
                        containment.append({"parent": self._node_label(elem), "child": self._node_label(child), "relationship": "contains"})
        return {
            "reference_count": len(links),
            "internal_reference_count": sum(1 for x in links if x["resolution"] == "internal"),
            "external_reference_count": len(external),
            "unresolved_reference_count": len(unresolved),
            "empty_reference_attribute_count": len(empty_attributes),
            "references": links,
            "containment": containment,
            "external_references": external,
            "unresolved_references": unresolved,
            "empty_reference_attributes": empty_attributes,
        }

    def _design_summary(self, design: ET.Element, id_index: Dict[str, ET.Element]) -> Dict[str, Any]:
        instances = []
        for elem in design.iter():
            if elem is design or self._local_tag(elem.tag).lower() not in self._DOMAIN_TAGS:
                continue
            if self._local_tag(elem.tag).lower() in {"diagram", "dcpinmap", "designusages"} and not elem.get("name"):
                continue
            instance = {"tag": elem.tag, "id": elem.get("id"), "name": elem.get("name"), "attributes": dict(elem.attrib)}
            instances.append(instance)
        relationships = []
        ids = {obj["id"] for obj in instances if obj["id"]}
        for obj in instances:
            elem = id_index.get(obj["id"]) if obj["id"] else None
            if elem is None:
                continue
            for key, value in elem.attrib.items():
                if self._REF_RE.search(key) and key.lower() not in {"baseid", "id"}:
                    relationships.append({"source": obj["name"] or obj["id"], "attribute": key, "target_id": value,
                                          "target_in_design": value in ids, "target": self._node_label(id_index.get(value))})
        return {
            "name": design.get("name"), "id": design.get("id"), "version": design.get("version"),
            "release_level_ref": design.get("releaselevelref"), "created": design.get("created"),
            "modified": design.get("modificationtimestamp"), "author": design.get("author"),
            "modified_by": design.get("modificationuser"), "dtd_version": design.get("dtdversion"),
            "attributes": dict(design.attrib), "object_count": len(instances), "objects": instances,
            "relationships": relationships,
            "object_counts": dict(Counter(self._local_tag(o["tag"]) for o in instances)),
            "hierarchy": self._hierarchy(design),
            "flat_paths": self._flat_paths(design),
        }

    def _key_attrs(self, elem: ET.Element) -> Dict[str, str]:
        return {k: elem.get(k) for k in self._KEY_ATTRS if elem.get(k) not in (None, "", " ")}

    def _hierarchy(self, elem: ET.Element) -> List[Dict[str, Any]]:
        """Nested domain-object tree (device → connector → pin/backshell → termination)."""
        nodes = []
        for child in elem:
            tag = self._local_tag(child.tag).lower()
            sub = self._hierarchy(child)
            if tag in self._DOMAIN_TAGS and tag not in {"designusages"}:
                node = {"tag": self._local_tag(child.tag), "name": child.get("name"), **self._key_attrs(child)}
                if sub:
                    node["children"] = sub
                nodes.append(node)
            else:
                nodes.extend(sub)
        return nodes

    def _flat_paths(self, design: ET.Element) -> Dict[str, List[Dict[str, Any]]]:
        """Map 'parent path | tag' -> child objects, used for paired before/after diffs."""
        out: Dict[str, List[Dict[str, Any]]] = defaultdict(list)

        def walk(elem: ET.Element, path: str):
            for child in elem:
                tag = self._local_tag(child.tag).lower()
                if tag in self._DOMAIN_TAGS and tag not in {"designusages", "diagram", "dcpinmap"}:
                    out[f"{path or '/'}|{tag}"].append({"name": child.get("name"), **self._key_attrs(child)})
                    walk(child, f"{path}/{tag}:{child.get('name')}")
                else:
                    walk(child, path)
        walk(design, "")
        return dict(out)

    @staticmethod
    def _paired_changes(before: Dict[str, List[Dict[str, Any]]],
                        after: Dict[str, List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
        changes = []
        for key in sorted(set(before) | set(after)):
            parent, tag = key.rsplit("|", 1)
            b = {o["name"]: o for o in before.get(key, [])}
            a = {o["name"]: o for o in after.get(key, [])}
            for name in sorted(set(b) & set(a), key=str):
                diff = {k: {"from": b[name].get(k), "to": a[name].get(k)}
                        for k in set(b[name]) | set(a[name]) if k != "name" and b[name].get(k) != a[name].get(k)}
                if diff:
                    changes.append({"change": "modified", "tag": tag, "name": name, "parent": parent, "fields": diff})
            removed = sorted(set(b) - set(a), key=str)
            added = sorted(set(a) - set(b), key=str)
            while removed and added:
                old, new = removed.pop(0), added.pop(0)
                changes.append({"change": "replaced", "tag": tag, "parent": parent, "from": old, "to": new})
            changes += [{"change": "removed", "tag": tag, "parent": parent, "name": n} for n in removed]
            changes += [{"change": "added", "tag": tag, "parent": parent, "name": n} for n in added]
        # Children that simply moved with a replaced parent are "carried over", not add+remove.
        renames = {f"/{c['tag']}:{c['from']}": f"/{c['tag']}:{c['to']}" for c in changes if c["change"] == "replaced"}

        def remap(path: str) -> str:
            parts = re.split(r"(?=/)", path)
            return "".join(renames.get(p, p) for p in parts)
        added_keys = {(c["tag"], c["name"], c["parent"]) for c in changes if c["change"] == "added"}
        carried = {(c["tag"], c["name"], remap(c["parent"])) for c in changes
                   if c["change"] == "removed" and (c["tag"], c["name"], remap(c["parent"])) in added_keys}
        result = []
        for c in changes:
            if c["change"] == "removed" and (c["tag"], c["name"], remap(c["parent"])) in carried:
                continue
            if c["change"] == "added" and (c["tag"], c["name"], c["parent"]) in carried:
                c = {**c, "change": "carried_over"}
            result.append(c)
        return result

    @staticmethod
    def _compare_designs(designs: List[Dict[str, Any]]) -> Dict[str, Any]:
        if len(designs) < 2:
            return {"available": False, "reason": "Only one logical design snapshot is present."}
        paired = [{"from": b["name"], "to": a["name"],
                   "changes": XmlAnalyzer._paired_changes(b.get("flat_paths", {}), a.get("flat_paths", {}))}
                  for b, a in zip(designs, designs[1:])]
        snapshots = []
        for design in designs:
            sigs = {(o["tag"], o.get("name"), o.get("attributes", {}).get("partnumber"),
                     o.get("attributes", {}).get("libraryref")) for o in design["objects"]}
            snapshots.append((design["name"], sigs))
        changes = []
        for (before_name, before), (after_name, after) in zip(snapshots, snapshots[1:]):
            changes.append({"from": before_name, "to": after_name,
                            "added": [list(x) for x in sorted(after - before, key=str)],
                            "removed": [list(x) for x in sorted(before - after, key=str)]})
        return {"available": True, "comparison_basis": "object tag, name, part number, and library reference",
                "consecutive_deltas": changes, "paired_changes": paired}

    def _related_files(self, root: ET.Element, objects: Dict[str, Any]) -> List[Dict[str, Any]]:
        if not self.search_engine:
            return []
        tags = list(objects["by_tag"])
        terms = [tag for tag in tags if tag.lower() in self._DOMAIN_TAGS
                 and tag.lower() not in {"project", "logicaldesign", "diagram", "designusages", "dcpinmap"}]
        # Keep searches specific and evidence based; avoid flooding results with generic tags.
        terms = terms[:8]
        matches = defaultdict(list)
        for term in terms:
            try:
                result = self.search_engine.search(query=term, max_results=5)
            except Exception:
                continue
            for item in result.get("results", []):
                path = item.get("file")
                if path:
                    for hit in item.get("matches", []):
                        matches[path].append({"xml_tag": term, "line": hit.get("line"),
                                              "match": hit.get("match"), "context": hit.get("context", [])})
        return [{"file": path,
                 "matched_xml_tags": sorted({hit["xml_tag"] for hit in hits}),
                 "match_count": len(hits),
                 "evidence": hits[:10]}
                for path, hits in sorted(matches.items(),
                                         key=lambda x: (-len({hit["xml_tag"] for hit in x[1]}), x[0]))[:15]]

    def _scenarios(self, file_name: str, root: ET.Element, report: Dict[str, Any]) -> Dict[str, Any]:
        tags = {tag.lower() for tag in report["inventory"]["tag_counts"]}
        objects = report["objects"]["instances"]
        names = {str(o.get("name", "")).lower() for o in objects}
        filename = file_name.lower()
        candidates = []
        if "removelibpart" in filename or "removelibrarypart" in filename:
            candidates.append({"scenario": "Remove or detach a library part from an in-design device/connector/backshell",
                               "evidence": [f"Filename includes {file_name!r}", "Review libraryref/partnumber fields on the serialized objects to confirm the exact target and outcome."],
                               "confidence": "filename-derived; XML state must confirm"})
        if "device" in tags and "deviceconnector" in tags and "backshell" in tags:
            candidates.append({"scenario": "Manage device connectors and their attached backshells",
                               "evidence": ["Device, deviceconnector, and backshell instances are present", "Backshell nodes are nested beneath device connectors in the design data."],
                               "confidence": "high"})
        if len(report["designs"]) > 1:
            candidates.append({"scenario": "Compare multiple saved logical-design states or variants",
                               "evidence": [f"{len(report['designs'])} logical design snapshots are embedded", "Per-snapshot objects and consecutive deltas are included in the report."],
                               "confidence": "high"})
        if "cavity" in tags or "dcpinmap" in tags:
            candidates.append({"scenario": "Validate connector cavity and pin mapping changes",
                               "evidence": ["Cavity or device-connector pin-map structures occur in the XML."], "confidence": "medium"})
        if "prefentry" in tags or "preferencemgr" in tags:
            candidates.append({"scenario": "Inspect project preference and rule configuration",
                               "evidence": ["Preference entries/managers are included in the project export."], "confidence": "high"})
        primary = candidates[0] if candidates else {"scenario": "Inspect or compare a Capital design/project export",
                                                    "evidence": ["Scenario inferred from the actual XML structure."], "confidence": "low"}
        primary = {"file_name": file_name, **primary}
        observed = []
        for delta in report.get("design_comparison", {}).get("paired_changes", []):
            for c in delta["changes"]:
                observed.append(f"{delta['from']} → {delta['to']}: {self._describe_change(c)}")
        if observed:
            primary["evidence"] = primary["evidence"] + ["Observed state changes between snapshots:"] + observed
            if "filename-derived" in primary.get("confidence", "") and any(
                    "partnumber" in o or "libraryref" in o or "replaced" in o for o in observed):
                primary["confidence"] = "medium-high (filename supported by observed part/library changes)"
        return {"primary": primary, "other_detected": candidates[1:],
                "observed_changes": observed,
                "limitations": ["The XML is a serialized state, not an execution trace; a filename alone cannot prove which command was run."]}

    @staticmethod
    def _describe_change(c: Dict[str, Any]) -> str:
        where = c.get("parent", "/").strip("/").replace(":", " ") or "design root"
        if c["change"] == "replaced":
            return f"{c['tag']} {c['from']!r} replaced by {c['to']!r} under {where}"
        if c["change"] == "modified":
            fields = ", ".join(f"{k} {v['from']!r} → {v['to']!r}" for k, v in sorted(c["fields"].items()))
            return f"{c['tag']} {c['name']!r} under {where} modified ({fields})"
        if c["change"] == "carried_over":
            return f"{c['tag']} {c['name']!r} retained on new parent {where}"
        return f"{c['tag']} {c['name']!r} {c['change']} under {where}"

    @staticmethod
    def _recommendations(report: Dict[str, Any]) -> Dict[str, Any]:
        tags = {tag.lower() for tag in report["inventory"]["tag_counts"]}
        objects = report["objects"]["instances"]
        suggestions = []
        objects_to_consider = []
        def add(scenario: str, why: str, leads_to: str, uses: List[str]):
            suggestions.append({"scenario": scenario, "basis": why, "what_it_enables": leads_to, "downstream_uses": uses})
        def suggest_object(name: str, reason: str, scenario: str, leads_to: str, uses: List[str]):
            objects_to_consider.append({"object": name, "condition": reason,
                                        "scenario_unlocked": scenario, "what_it_enables": leads_to,
                                        "downstream_uses": uses})
        if "deviceconnector" in tags and "backshell" not in tags:
            suggest_object("BACKSHELL", "Device connectors are present without any backshell instances.",
                           "Backshell attachment, replacement, and connector compatibility.",
                           "Exercise protection/termination attachment and resulting BOM changes.",
                           ["Connector assembly checks", "BOM impact analysis"])
        if "deviceconnector" in tags and ("pin" in tags or "dcpinmap" in tags) and "cavityseal" not in tags:
            suggest_object("CAVITYSEAL", "Connector pin/cavity mapping exists but no cavity seal object was detected; add only where sealing is required.",
                           "Weatherproofed connector assembly and seal coverage validation.",
                           "Check sealed versus unsealed cavities and DRC behavior after library-part edits.",
                           ["Weatherproofing DRC", "Cavity coverage reports", "Seal selection tests"])
        if "deviceconnector" in tags and "dcpinmap" not in tags:
            suggest_object("DCPINMAP", "Device connectors are present without an explicit pin-map object.",
                           "Pin-to-cavity mapping and connector pin assignment checks.",
                           "Test connector replacement while preserving or rebuilding pin mapping.",
                           ["Pin-map completeness reports", "Connector substitution regression tests"])
        if "backshell" in tags and "termination" not in tags:
            suggest_object("TERMINATION", "Backshells exist without associated termination objects.",
                           "Backshell termination and wire/shield attachment validation.",
                           "Check termination retention and connector/backshell compatibility.",
                           ["Termination compatibility rules", "Assembly/BOM validation"])
        if {"device", "deviceconnector", "backshell"}.issubset(tags):
            add("Library-reference removal/replacement and reattachment", "Device → connector → backshell containment plus library/part fields are present.",
                "Verify reference cleanup, retained instance properties, and correct relinking after replacement.",
                ["Regression tests for remove/undo/redo", "Broken-reference detection", "Before/after design diffs"])
            add("Backshell swap and connector compatibility", "Backshells are attached to device connectors.",
                "Test compatible/incompatible swaps, preservation of termination data, and BOM changes.",
                ["Compatibility-rule coverage", "BOM delta reports", "Connector assembly validation"])
        if report["designs"] and any(len(d["objects"]) > 2 for d in report["designs"]):
            add("Multi-connector and shared-device impact", "At least one design has multiple component instances under the device.",
                "Exercise targeted versus bulk updates and ensure each connector retains its intended backshell/pin map.",
                ["Per-connector change auditing", "Bulk-edit safety tests", "Impact analysis across design variants"])
        if "cavity" in tags or "pin" in tags or "dcpinmap" in tags:
            add("Cavity, seal, plug, and pin-map validation", "Pin/cavity-related structures appear in the XML.",
                "Check unassigned pins/cavities, sealing, plugs, and mappings after library-part edits.",
                ["Automated DRC preflight", "Weatherproofing checks", "Pin-map completeness reports"])
        if len(report["designs"]) > 1:
            add("Cross-snapshot migration and consistency checks", "The file contains multiple logical-design snapshots.",
                "Compare instances and library references between states or project versions.",
                ["Migration regression suites", "Design drift reports", "Change-impact summaries"])
        if not suggestions:
            add("Schema-aware validation and test generation", "The export includes structured Capital objects and attributes.",
                "Turn observed containment and references into checks and reproducible test fixtures.",
                ["Reference-integrity reports", "Automated XML regression tests", "Documentation generation"])
        general_uses = [
            "Generate an object/relationship inventory for review or documentation",
            "Build a test matrix from object combinations and state changes",
            "Trace XML object types to source handlers and identify missing code coverage",
            "Compare exported design variants and report changed library references",
        ]
        for item in objects_to_consider:
            add(item["scenario_unlocked"], item["condition"], item["what_it_enables"], item["downstream_uses"])
        return {"objects_to_consider": objects_to_consider, "scenario_ideas": suggestions, "additional_data_uses": general_uses,
                "note": "Recommendations are conditional on observed XML objects; they are test/design ideas, not claims that those objects are missing or required."}

    def _find_related_code_files(self, root: ET.Element, objects: Dict[str, Any]) -> List[str]:
        """Compatibility helper retained for callers of the previous implementation."""
        return [item["file"] for item in self._related_files(root, objects)]

    @staticmethod
    def _identify_scenario(file_name: str, root: ET.Element, objects: Dict[str, Any]) -> Dict[str, Any]:
        """Compatibility helper; prefer the evidence-based report in analyze_xml()."""
        filename = file_name.lower()
        action = "Design Representation"
        domain = "Capital System / Design Export"
        if "removelibpart" in filename or "removelibrarypart" in filename:
            action, domain = "Library Part Removal / Refactoring", "Capital Library & Device Backshell Management"
        return {"file_name": file_name, "inferred_scenario": f"{action} in {domain}", "primary_domain": domain, "action_type": action}

    # ------------------------------------------------------------------ output shaping
    def _compact(self, report: Dict[str, Any]) -> Dict[str, Any]:
        """Keep every section, but trim raw per-instance/per-reference dumps to samples."""
        n = self._SAMPLE_LIMIT
        conn = report["connections"]
        compact_conn = {k: v for k, v in conn.items() if k.endswith("_count")}
        for k in ("references", "containment", "external_references", "unresolved_references",
                  "empty_reference_attributes"):
            compact_conn[f"{k}_sample"] = conn[k][:n]
        objs = report["objects"]
        domain = [o for o in objs["instances"] if self._local_tag(o["tag"]).lower() in self._DOMAIN_TAGS]
        compact_objs = {
            "count": objs["count"], "by_tag": objs["by_tag"],
            "domain_instances": [{"tag": o["tag"], "name": o["name"], "design": o["design"],
                                  "parent": (o["parent"] or {}).get("name") or (o["parent"] or {}).get("tag"),
                                  **{k: o["attributes"][k] for k in self._KEY_ATTRS
                                     if o["attributes"].get(k) not in (None, "", " ")}}
                                 for o in domain][:200],
            "note": "Compact view. Call with detail='full' for every instance with all attributes.",
        }
        designs = [{k: v for k, v in d.items() if k not in {"objects", "relationships", "flat_paths", "attributes"}}
                   | {"relationship_count": len(d["relationships"])} for d in report["designs"]]
        out = dict(report)
        out.update({
            "objects": compact_objs,
            "connections": compact_conn,
            "designs": designs,
            "objects_inventory": {k: v for k, v in report["inventory"].items() if k != "tag_counts"},
            "connectivity_graph": {k: v for k, v in compact_conn.items() if k.endswith("_count")},
            "detail": "summary",
        })
        return out

    def _markdown(self, r: Dict[str, Any]) -> str:
        L: List[str] = []
        doc, sc = r["document"], r["scenarios"]["primary"]
        L.append(f"# XML Design Analysis — {r['file']}")
        L.append(f"Root `<{doc['root_tag']}>` · {doc['element_count']} elements · "
                 f"{doc['distinct_tag_count']} distinct tags · {doc['design_count']} logical design(s)")
        L.append("\n## 1. Scenario")
        L.append(f"**{sc['scenario']}** (confidence: {sc['confidence']})")
        L += [f"- {e}" for e in sc["evidence"]]
        if r["scenarios"]["other_detected"]:
            L.append("\nOther detected scenarios:")
            L += [f"- {o['scenario']} ({o['confidence']})" for o in r["scenarios"]["other_detected"]]
        L.append("\n## 2. Object inventory")
        dom = r["inventory"]["domain_tag_counts"]
        L.append("| Object | Count |\n|---|---|")
        L += [f"| {k} | {v} |" for k, v in sorted(dom.items(), key=lambda x: -x[1])]
        infra = r["inventory"]["infrastructure_tag_counts"]
        if infra:
            L.append("\nInfrastructure/bookkeeping tags: " +
                     ", ".join(f"{k}×{v}" for k, v in sorted(infra.items(), key=lambda x: -x[1])[:15]))
        L.append("\n## 3. Logical designs")
        for d in r["designs"]:
            meta = ", ".join(f"{k}={d[k]}" for k in ("version", "author", "modified_by") if d.get(k))
            L.append(f"\n### {d['name']}" + (f" ({meta})" if meta else ""))
            L.append("```")
            L += self._tree_lines(d["hierarchy"])
            L.append("```")
        comp = r["design_comparison"]
        L.append("\n## 4. Changes between snapshots")
        if not comp.get("available"):
            L.append(comp.get("reason", "Not available."))
        else:
            for delta in comp["paired_changes"]:
                L.append(f"\n**{delta['from']} → {delta['to']}**")
                L += [f"- {self._describe_change(c)}" for c in delta["changes"]] or ["- No object-level change detected."]
        c = r["connections"]
        L.append("\n## 5. Connectivity & references")
        L.append(f"- References: {c['reference_count']} (internal {c['internal_reference_count']}, "
                 f"external {c['external_reference_count']}, unresolved {c['unresolved_reference_count']}, "
                 f"empty {c['empty_reference_attribute_count']})")
        L.append(f"- Containment links: {len(c['containment'])}")
        real_unresolved = [u for u in c["unresolved_references"] if u["attribute"].lower() != "nameref"]
        if len(real_unresolved) != len(c["unresolved_references"]):
            L.append(f"- {len(c['unresolved_references']) - len(real_unresolved)} unresolved are `nameref` "
                     "attribute-name labels (not object IDs) and are expected.")
        for u in real_unresolved[:10]:
            L.append(f"  - unresolved `{u['attribute']}` on {u['source']['tag']} "
                     f"{u['source'].get('name') or u['source'].get('id')} → {u['target_id']}")
        L.append("\n## 6. Related source files")
        if r["related_code_files"]:
            L += [f"- `{f['file']}` — matches {', '.join(f['matched_xml_tags'])} ({f['match_count']} hits)"
                  for f in r["related_code_files"]]
        else:
            L.append("- No source matches found (search engine unavailable or no hits).")
        rec = r["recommendations"]
        L.append("\n## 7. Objects to consider adding")
        L += [f"- **{o['object']}** — {o['condition']} → unlocks: {o['scenario_unlocked']} "
              f"(uses: {', '.join(o['downstream_uses'])})" for o in rec["objects_to_consider"]] or ["- None suggested."]
        L.append("\n## 8. Scenario ideas & downstream uses")
        for s in rec["scenario_ideas"]:
            L.append(f"- **{s['scenario']}** — {s['basis']}\n  - Enables: {s['what_it_enables']}\n"
                     f"  - Uses: {', '.join(s['downstream_uses'])}")
        L.append("\n## 9. Other uses of this data")
        L += [f"- {u}" for u in rec["additional_data_uses"]]
        L.append(f"\n> {rec['note']} " + " ".join(r["scenarios"]["limitations"]))
        return "\n".join(L)

    @classmethod
    def _tree_lines(cls, nodes: List[Dict[str, Any]], prefix: str = "") -> List[str]:
        lines = []
        for i, n in enumerate(nodes):
            last = i == len(nodes) - 1
            extras = ", ".join(f"{k}={n[k]}" for k in ("partnumber", "typecode", "pintype") if n.get(k))
            label = f"{n['tag']} {n.get('name') or ''}".strip() + (f" [{extras}]" if extras else "")
            lines.append(f"{prefix}{'└─ ' if last else '├─ '}{label}")
            lines += cls._tree_lines(n.get("children", []), prefix + ("   " if last else "│  "))
        return lines
    def _discover_reference_samples(self) -> List[str]:
        """Automatically load XML reference files from the local training folder."""
        samples: List[str] = []
        candidates = []
        ref_dir = self.repo_path / ".copilot-xml-reference"
        if ref_dir.exists():
            candidates.extend(sorted(ref_dir.rglob("*.xml")))
            candidates.extend(sorted(ref_dir.rglob("*.XML")))
        for p in sorted(self.repo_path.glob("*.xml")):
            if p.name.startswith(".copilot-xml-reference") or p.name.endswith(".xml"):
                candidates.append(p)
        seen = set()
        for path in candidates:
            if str(path) in seen:
                continue
            seen.add(str(path))
            try:
                if path.is_file() and path.stat().st_size <= 50 * 1024 * 1024:
                    samples.append(path.read_text(encoding="utf-8", errors="replace"))
            except OSError:
                continue
        return samples[:20]

    def learn_design_patterns(self, xml_examples: str = "") -> Dict[str, Any]:
        """Learn a Capital-like XML schema from sample exports and return a reusable generation profile."""
        examples = self._collect_xml_examples(xml_examples) if xml_examples else self._discover_reference_samples()
        if not examples:
            return self._default_generation_profile()

        tag_counts: Counter = Counter()
        tag_attributes: Dict[str, Counter] = defaultdict(Counter)
        hierarchy_paths: Dict[str, int] = defaultdict(int)
        root_tags: Counter = Counter()
        observed_objects: set = set()

        for xml_text in examples:
            try:
                if len(xml_text.encode("utf-8", errors="ignore")) > 50 * 1024 * 1024:
                    continue
                root = ET.fromstring(xml_text)
            except (ET.ParseError, OverflowError, ValueError, MemoryError):
                continue
            root_tags[self._local_tag(root.tag).lower()] += 1
            for elem in root.iter():
                tag = self._local_tag(elem.tag).lower()
                if not tag:
                    continue
                tag_counts[tag] += 1
                observed_objects.add(tag)
                for attr_name in elem.attrib:
                    tag_attributes[tag][attr_name.lower()] += 1
                if tag in self._DOMAIN_TAGS:
                    path = self._path_signature(elem)
                    if path:
                        hierarchy_paths[path] += 1

        ranked_tags = [
            {"tag": tag, "count": count, "common_attributes": sorted(tag_attributes.get(tag, {}).items(), key=lambda kv: (-kv[1], kv[0]))[:8]}
            for tag, count in tag_counts.most_common(20)
        ]
        hierarchy = [
            {"path": path, "count": count}
            for path, count in sorted(hierarchy_paths.items(), key=lambda kv: (-kv[1], kv[0]))[:12]
        ]
        generated_schema = {
            "root_tags": dict(root_tags),
            "common_tags": ranked_tags,
            "hierarchy_paths": hierarchy,
            "likely_design_nodes": sorted(t for t in observed_objects if t in self._DOMAIN_TAGS),
            "generation_hints": self._generation_hints(ranked_tags),
        }
        return {
            "status": "ok",
            "example_count": len(examples),
            "schema": generated_schema,
            "summary": "Learned object-and-hierarchy patterns from the provided XML examples. These patterns can be used to synthesize a matching project skeleton or to adapt a new design description.",
        }

    def generate_design_xml_from_requirements(self, requirements: str, xml_examples: str = "") -> Dict[str, Any]:
        """Translate natural-language design requirements into a Capital-style XML project file."""
        learned = self.learn_design_patterns(xml_examples) if xml_examples else self.learn_design_patterns()
        req = (requirements or "").strip()
        if not req:
            req = "Generate a generic harness project with 1 device, 2 connectors, and 8 signal pins."

        project_name = self._extract_name(req)
        device_count = self._extract_count(req, ["device", "module", "assembly"])
        connector_count = self._extract_count(req, ["connector", "plug", "receptacle"]) or max(device_count, 1)
        pin_count = self._extract_count(req, ["pin", "cavity", "terminal"]) or max(connector_count * 2, 4)
        bundle_count = self._extract_count(req, ["bundle", "harness", "cable", "wire"]) or 1
        signal_count = self._extract_count(req, ["signal", "net", "wire"]) or max(pin_count, 8)

        project = ET.Element("project", name=project_name or "GeneratedProject")
        design = ET.SubElement(project, "logicaldesign", {"name": f"{project_name or 'Generated'}Design", "id": "ld-1", "version": "1.0"})
        if bundle_count > 0:
            for idx in range(1, bundle_count + 1):
                bundle = ET.SubElement(design, "bundle", {"name": f"{project_name or 'Harness'}_bundle_{idx}", "id": f"bundle-{idx}", "type": "harness"})
                if idx == 1 and signal_count:
                    for signal_idx in range(1, min(signal_count, 12) + 1):
                        ET.SubElement(bundle, "signal", {"name": f"signal_{signal_idx}", "id": f"signal-{idx}-{signal_idx}", "type": "electrical"})

        for device_idx in range(1, max(device_count, 1) + 1):
            device = ET.SubElement(design, "device", {"name": f"{project_name or 'Device'}_{device_idx}", "id": f"device-{device_idx}", "partnumber": f"DEV-{device_idx:03d}", "libraryref": f"LIB-{device_idx:03d}"})
            for connector_idx in range(1, max(connector_count, 1) + 1):
                connector = ET.SubElement(device, "deviceconnector", {"name": f"connector_{device_idx}_{connector_idx}", "id": f"deviceconnector-{device_idx}-{connector_idx}", "type": "male", "partnumber": f"CON-{device_idx:03d}-{connector_idx:02d}"})
                for pin_idx in range(1, max(pin_count, 1) + 1):
                    ET.SubElement(connector, "pin", {"name": f"pin_{device_idx}_{connector_idx}_{pin_idx}", "id": f"pin-{device_idx}-{connector_idx}-{pin_idx}", "pintype": "signal"})

        if "ground" in req.lower() or "shield" in req.lower():
            ground = ET.SubElement(design, "ground", {"name": f"{project_name or 'Ground'}_return", "id": "ground-1"})
            ET.SubElement(ground, "signal", {"name": "ground_signal", "id": "ground-signal-1"})

        pretty = self._pretty_print_xml(ET.tostring(project, encoding="unicode"))
        generated_dir = self.repo_path / ".copilot-xml-reference" / "generated"
        generated_dir.mkdir(parents=True, exist_ok=True)
        output_file = generated_dir / f"{project_name or 'generated_project'}.xml"
        output_file.write_text(pretty, encoding="utf-8")
        return {"status": "ok", "project_name": project_name or "GeneratedProject", "confidence": "medium", "learned_schema": learned, "design_summary": {"device_count": max(device_count, 1), "connector_count": max(connector_count, 1), "pin_count": max(pin_count, 1), "bundle_count": max(bundle_count, 1)}, "output_file": str(output_file), "notes": ["The XML project file was written to .copilot-xml-reference/generated.", "Add part numbers, library references, and completion details for a production-ready export."]}

    @staticmethod
    def _collect_xml_examples(xml_examples: str) -> List[str]:
        if not xml_examples or not xml_examples.strip():
            return []
        candidates = [piece.strip() for piece in re.split(r"[\r\n,;]+", xml_examples) if piece.strip()]
        samples: List[str] = []
        for candidate in candidates:
            if "<" in candidate:
                if len(candidate.encode("utf-8", errors="ignore")) <= 50 * 1024 * 1024:
                    samples.append(candidate)
                continue
            path = Path(candidate)
            if path.exists() and path.is_file():
                try:
                    if path.stat().st_size > 50 * 1024 * 1024:
                        continue
                    samples.append(path.read_text(encoding="utf-8", errors="replace"))
                except OSError:
                    pass
        return samples

    @staticmethod
    def _path_signature(elem: ET.Element) -> str:
        parts = []
        current = elem
        while current is not None:
            tag = XmlAnalyzer._local_tag(current.tag).lower()
            if tag:
                parts.append(tag)
            current = current.getparent() if hasattr(current, 'getparent') else None
        return " > ".join(reversed(parts))

    @staticmethod
    def _extract_name(requirements: str) -> str:
        patterns = [
            r"(?:project|design)\s+(?:name\s+)?['\"]?([A-Za-z0-9_][A-Za-z0-9_ -]*?)(?=\s+(?:with|and|for|using|including|containing|having|version|of)|$)",
            r"create\s+(?:a\s+)?(?:project|design)\s+(?:called\s+)?['\"]?([A-Za-z0-9_][A-Za-z0-9_ -]*?)(?=\s+(?:with|and|for|using|including|containing|having|version|of)|$)",
        ]
        for pattern in patterns:
            match = re.search(pattern, requirements, flags=re.IGNORECASE)
            if match:
                value = match.group(1).strip()
                cleaned = re.sub(r"\s+", " ", value).strip()
                if cleaned and cleaned.lower() not in {"project", "design"}:
                    return cleaned
        fallback = re.sub(r"[^a-zA-Z0-9_ -]+", " ", requirements.lower()).strip()
        fallback = re.sub(r"\s+", " ", fallback)
        if fallback and len(fallback.split()) <= 5:
            return fallback.title().replace(" ", "_")
        return "GeneratedProject"

    @staticmethod
    def _extract_count(requirements: str, keywords: List[str]) -> int:
        text = requirements.lower()
        for keyword in keywords:
            match = re.search(rf"(\d+)\s+{keyword}s?\b", text)
            if match:
                return int(match.group(1))
            match = re.search(rf"{keyword}s?\s*(?:of\s*)?(\d+)", text)
            if match:
                return int(match.group(1))
        for match in re.finditer(r"(\d+)\s+([a-z]+)", text):
            qty, noun = match.groups()
            if noun in {k[:-1] if k.endswith("s") else k for k in keywords}:
                return int(qty)
        return 0

    @staticmethod
    def _generation_hints(tags: List[Dict[str, Any]]) -> List[str]:
        hints = ["Use project → logicaldesign → device → deviceconnector → pin hierarchy for a canonical harness layout."]
        if any(t["tag"] == "bundle" for t in tags):
            hints.append("Bundle and signal objects are a good fit for cable/harness-level wiring definitions.")
        if any(t["tag"] == "ground" for t in tags):
            hints.append("Ground or shield objects can be added when the design includes return paths or protective shielding.")
        return hints

    def _default_generation_profile(self) -> Dict[str, Any]:
        return {"status": "ok", "example_count": 0, "schema": {"root_tags": {"project": 1}, "common_tags": [{"tag": "project", "count": 1, "common_attributes": ["name"]}, {"tag": "logicaldesign", "count": 1, "common_attributes": ["name", "version"]}, {"tag": "device", "count": 1, "common_attributes": ["name", "partnumber", "libraryref"]}, {"tag": "deviceconnector", "count": 1, "common_attributes": ["name", "type", "partnumber"]}, {"tag": "pin", "count": 1, "common_attributes": ["name", "pintype"]}, {"tag": "bundle", "count": 1, "common_attributes": ["name", "type"]}], "hierarchy_paths": [{"path": "project > logicaldesign > device > deviceconnector > pin", "count": 1}, {"path": "project > logicaldesign > bundle > signal", "count": 1}], "likely_design_nodes": ["project", "logicaldesign", "device", "deviceconnector", "pin", "bundle", "signal"], "generation_hints": ["Use project → logicaldesign → device → deviceconnector → pin hierarchy for a canonical harness layout.", "Bundle and signal objects are a good fit for cable and harness-level wiring definitions."]}, "summary": "No sample XML was provided, so the tool used the built-in Capital XML conventions for a default skeleton."}

    @staticmethod
    def _pretty_print_xml(xml_text: str) -> str:
        try:
            parsed = minidom.parseString(xml_text)
            return parsed.toprettyxml(indent="  ").replace("\n\n", "\n")
        except Exception:
            return xml_text


