"""
CopilotLens - Policy Repository & Copilot Interaction Analyzer
================================================================
Extracts rules, developer corrections, and conventions from Copilot interactions,
stores them in a local policy repository, and synchronizes approved rules to
.github/copilot-instructions.md for IntelliJ IDEA and VS Code.
"""

import json
import re
import time
from pathlib import Path
from typing import Dict, List, Any, Optional


class PolicyRepository:
    """Local policy repository stored in .copilot-policy/policy.json."""

    def __init__(self, repo_path: str):
        self.repo_path = Path(repo_path).resolve()
        self.policy_dir = self.repo_path / ".copilot-policy"
        self.policy_file = self.policy_dir / "policy.json"
        self._ensure_storage()

    def _ensure_storage(self):
        """Ensure policy directory and file exist."""
        try:
            self.policy_dir.mkdir(parents=True, exist_ok=True)
            if not self.policy_file.exists():
                initial_data = {
                    "version": "1.0",
                    "repo": str(self.repo_path),
                    "rules": []
                }
                self.policy_file.write_text(json.dumps(initial_data, indent=2), encoding="utf-8")
        except Exception as e:
            print(f"[PolicyRepo] Storage setup warning: {e}")

    def load_rules(self) -> List[Dict[str, Any]]:
        """Load all rules from policy storage."""
        if not self.policy_file.exists():
            return []
        try:
            content = self.policy_file.read_text(encoding="utf-8")
            data = json.loads(content)
            return data.get("rules", [])
        except Exception:
            return []

    def save_rules(self, rules: List[Dict[str, Any]]):
        """Save rules back to policy storage."""
        try:
            data = {
                "version": "1.0",
                "repo": str(self.repo_path),
                "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "rules": rules
            }
            self.policy_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception as e:
            print(f"[PolicyRepo] Save rules error: {e}")

    def add_rule(
        self,
        rule: str,
        preferred_approach: str = "",
        scope: str = "project",
        rationale: str = "",
        source_interaction: str = "",
        confidence_level: str = "HIGH",
        status: str = "PENDING"
    ) -> Dict[str, Any]:
        """Add a new rule to the repository."""
        rules = self.load_rules()
        rule_id = f"rule-{int(time.time())}-{len(rules) + 1}"
        new_rule = {
            "id": rule_id,
            "rule": rule.strip(),
            "preferred_approach": preferred_approach.strip() or rule.strip(),
            "scope": scope.strip() or "project",
            "rationale": rationale.strip() or "Developer correction / convention",
            "source_interaction": source_interaction.strip() or "Explicit input",
            "confidence_level": confidence_level,
            "status": status,  # PENDING, APPROVED, REJECTED
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        }
        rules.append(new_rule)
        self.save_rules(rules)
        if status == "APPROVED":
            self.sync_to_copilot_instructions()
        return new_rule

    def list_rules(self, status_filter: str = "all", scope_filter: str = "") -> List[Dict[str, Any]]:
        """List rules with optional filtering."""
        rules = self.load_rules()
        filtered = []
        for r in rules:
            if status_filter != "all" and r.get("status", "").upper() != status_filter.upper():
                continue
            if scope_filter and scope_filter.lower() not in r.get("scope", "").lower() and r.get("scope") != "project":
                continue
            filtered.append(r)
        return filtered

    def update_rule_status(
        self,
        rule_id: str,
        action: str,
        preferred_approach: str = "",
        scope: str = ""
    ) -> Dict[str, Any]:
        """Approve, reject, edit, or delete a rule."""
        rules = self.load_rules()
        updated = None
        action_lower = action.lower()

        if action_lower == "delete":
            rules = [r for r in rules if r.get("id") != rule_id]
            self.save_rules(rules)
            self.sync_to_copilot_instructions()
            return {"status": "DELETED", "id": rule_id}

        for r in rules:
            if r.get("id") == rule_id:
                if action_lower == "approve":
                    r["status"] = "APPROVED"
                elif action_lower == "reject":
                    r["status"] = "REJECTED"
                elif action_lower == "edit":
                    if preferred_approach:
                        r["preferred_approach"] = preferred_approach
                    if scope:
                        r["scope"] = scope
                r["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                updated = r
                break

        if updated:
            self.save_rules(rules)
            self.sync_to_copilot_instructions()
            return updated
        return {"error": f"Rule '{rule_id}' not found"}

    def get_approved_rules(self, scope: str = "") -> List[Dict[str, Any]]:
        """Get all approved rules relevant to a given scope or project."""
        return self.list_rules(status_filter="APPROVED", scope_filter=scope)

    def sync_to_copilot_instructions(self) -> str:
        """Sync approved rules into .github/copilot-instructions.md."""
        approved = self.get_approved_rules()
        output_path = self.repo_path / ".github" / "copilot-instructions.md"
        
        # Read existing content if file exists
        existing_text = ""
        if output_path.exists():
            try:
                existing_text = output_path.read_text(encoding="utf-8")
            except Exception:
                existing_text = ""

        rules_markdown = ["## 📜 Approved Project Conventions & Local Policy Rules"]
        if not approved:
            rules_markdown.append("- No custom rules configured yet.")
        else:
            for r in approved:
                rules_markdown.append(f"- **[{r['scope']}]** {r['rule']}")
                if r.get('preferred_approach'):
                    rules_markdown.append(f"  - *Preferred Approach*: {r['preferred_approach']}")
                if r.get('rationale'):
                    rules_markdown.append(f"  - *Rationale*: {r['rationale']}")

        rules_section = "\n".join(rules_markdown)

        # Merge with existing file or create new
        if "## 📜 Approved Project Conventions" in existing_text:
            parts = existing_text.split("## 📜 Approved Project Conventions")
            header = parts[0]
            # preserve rest if there was content after
            rest_parts = parts[1].split("\n\n## ", 1)
            tail = ("\n\n## " + rest_parts[1]) if len(rest_parts) > 1 else ""
            new_content = header.rstrip() + "\n\n" + rules_section + tail
        elif existing_text.strip():
            new_content = existing_text.rstrip() + "\n\n" + rules_section
        else:
            new_content = f"# GitHub Copilot Instructions\n\n{rules_section}\n"

        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(new_content, encoding="utf-8")
            return f"Synced {len(approved)} approved rules to {output_path.relative_to(self.repo_path)}"
        except Exception as e:
            return f"Error syncing instructions: {e}"


class CopilotInteractionAnalyzer:
    """Analyzes developer interactions and extracts rules."""

    def __init__(self, repo_path: str):
        self.policy_repo = PolicyRepository(repo_path)

    def analyze_interaction(self, text: str, auto_approve_high_confidence: bool = False) -> Dict[str, Any]:
        """
        Analyzes a Copilot prompt or chat interaction text and extracts rules.
        Example text: "Do not update server.py directly" or "Remember this rule: Always use async/await"
        """
        extracted_rules = self._extract_rule_candidates(text)
        results = []

        for candidate in extracted_rules:
            status = "APPROVED" if (auto_approve_high_confidence and candidate["confidence_level"] == "HIGH") else "PENDING"
            rule_entry = self.policy_repo.add_rule(
                rule=candidate["rule"],
                preferred_approach=candidate["preferred_approach"],
                scope=candidate["scope"],
                rationale=candidate["rationale"],
                source_interaction=text[:200],
                confidence_level=candidate["confidence_level"],
                status=status
            )
            results.append(rule_entry)

        return {
            "source_text": text,
            "extracted_count": len(results),
            "rules": results
        }

    def _extract_rule_candidates(self, text: str) -> List[Dict[str, Any]]:
        candidates = []
        lines = [line.strip() for line in text.splitlines() if line.strip()]

        # Pattern 1: Explicit command "Remember this rule: ..."
        for match in re.finditer(r"(?:remember\s+this\s+rule|rule)[:\s]+(.+)", text, re.I):
            rule_body = match.group(1).strip()
            scope = self._detect_scope(rule_body)
            candidates.append({
                "rule": rule_body,
                "preferred_approach": rule_body,
                "scope": scope,
                "rationale": "Explicitly requested by developer",
                "confidence_level": "HIGH"
            })

        # Pattern 2: Negative directives ("Do not...", "Don't...", "Never...", "Avoid...")
        neg_matches = re.finditer(r"\b(do\s+not|don'?t|never|avoid)\s+([^\!\n]+?)(?=(?:\.\s|\!|\n|$))", text, re.I)
        for m in neg_matches:
            verb_phrase = m.group(2).strip()
            rule_text = f"Do not {verb_phrase}"
            scope = self._detect_scope(verb_phrase)
            candidates.append({
                "rule": rule_text,
                "preferred_approach": f"Avoid {verb_phrase}. Seek approved project pattern.",
                "scope": scope,
                "rationale": "Developer correction prohibiting specific action",
                "confidence_level": "HIGH" if scope != "project" else "MEDIUM"
            })

        # Pattern 3: Positive conventions ("Always use...", "Prefer...", "Follow pattern...", "Must use...")
        pos_matches = re.finditer(r"\b(always\s+use|prefer|must\s+use|follow\s+pattern)\s+([^\!\n]+?)(?=(?:\.\s|\!|\n|$))", text, re.I)
        for m in pos_matches:
            convention_phrase = m.group(2).strip()
            rule_text = f"Always use {convention_phrase}" if "always" not in m.group(1).lower() else m.group(0).strip()
            scope = self._detect_scope(convention_phrase)
            candidates.append({
                "rule": rule_text,
                "preferred_approach": convention_phrase,
                "scope": scope,
                "rationale": "Project architectural/coding convention",
                "confidence_level": "HIGH"
            })

        # Fallback if no specific regex matched but text is short command
        if not candidates and len(text) < 150:
            candidates.append({
                "rule": text.strip(),
                "preferred_approach": text.strip(),
                "scope": self._detect_scope(text),
                "rationale": "Submitted developer rule",
                "confidence_level": "MEDIUM"
            })

        return candidates

    def _detect_scope(self, text: str) -> str:
        """Infer file path, language, or folder scope from text."""
        # File path match
        file_match = re.search(r"[\w\/\.\-]+\.(?:py|js|ts|jsx|tsx|java|json|md|html|css)", text)
        if file_match:
            return file_match.group(0)

        # Folder match
        folder_match = re.search(r"\b(?:in|under|inside)\s+([\w\/\-]+)", text)
        if folder_match:
            return folder_match.group(1)

        # Language match
        for lang in ("python", "javascript", "typescript", "java", "react"):
            if lang in text.lower():
                return lang

        return "project"
