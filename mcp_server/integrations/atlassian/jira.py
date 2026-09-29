"""
Centralized Jira Integration
Handles all Jira operations (search, read, create, update) for CoPilotLens.
"""

import os
from pathlib import Path
from .client import AtlassianClient


class JiraManager:
    """Centralized manager for all Jira REST API interactions."""

    def __init__(self):
        self.client = AtlassianClient("jira")

    def get_issues_for_file(self, file_path: str) -> dict:
        """Finds open Jira issues (Bugs/Tasks) referencing a specific source file."""
        filename = Path(file_path).name
        project_key = os.getenv("JIRA_PROJECT_KEY") or os.getenv("ATLASSIAN_JIRA_PROJECT")

        jql = f'text ~ "{filename}" AND statusCategory != Done'
        if project_key:
            jql = f'project = "{project_key}" AND {jql}'

        res = self.client.request("GET", "/rest/api/2/search", params={"jql": jql, "maxResults": 10})
        if res.get("error"):
            return {"file": file_path, "issues": [], "error": res}

        issues = []
        for raw in res.get("issues", []):
            fields = raw.get("fields", {})
            issues.append({
                "key": raw.get("key"),
                "summary": fields.get("summary"),
                "status": fields.get("status", {}).get("name"),
                "priority": fields.get("priority", {}).get("name"),
                "type": fields.get("issuetype", {}).get("name"),
                "assignee": (fields.get("assignee") or {}).get("displayName", "Unassigned"),
                "url": f"{self.client.get_base_url()}/browse/{raw.get('key')}"
            })

        return {"file": file_path, "total_matched": len(issues), "issues": issues}

    def get_issue(self, issue_key: str) -> dict:
        """Fetches complete details for a specific Jira issue (e.g. 'PVC-4464')."""
        res = self.client.request("GET", f"/rest/api/2/issue/{issue_key}")
        if res.get("error"):
            return {"key": issue_key, "error": res}

        fields = res.get("fields", {})
        return {
            "key": res.get("key"),
            "summary": fields.get("summary"),
            "description": fields.get("description"),
            "status": fields.get("status", {}).get("name"),
            "priority": fields.get("priority", {}).get("name"),
            "type": fields.get("issuetype", {}).get("name"),
            "assignee": (fields.get("assignee") or {}).get("displayName", "Unassigned"),
            "url": f"{self.client.get_base_url()}/browse/{res.get('key')}"
        }

    def search_issues(self, query_or_jql: str, limit: int = 10) -> dict:
        """Searches Jira issues using text search or custom JQL."""
        jql = query_or_jql if " " in query_or_jql and ("=" in query_or_jql or "ORDER" in query_or_jql) else f'text ~ "{query_or_jql}" ORDER BY created DESC'
        res = self.client.request("GET", "/rest/api/2/search", params={"jql": jql, "maxResults": limit})
        if res.get("error"):
            return {"query": query_or_jql, "issues": [], "error": res}

        issues = []
        for raw in res.get("issues", []):
            fields = raw.get("fields", {})
            issues.append({
                "key": raw.get("key"),
                "summary": fields.get("summary"),
                "status": fields.get("status", {}).get("name"),
                "url": f"{self.client.get_base_url()}/browse/{raw.get('key')}"
            })
        return {"total": res.get("total", len(issues)), "issues": issues}

    def create_issue(self, summary: str, description: str, issue_type: str = "Bug", project_key: str = None) -> dict:
        """Creates a new Jira issue."""
        proj = project_key or os.getenv("JIRA_PROJECT_KEY") or os.getenv("ATLASSIAN_JIRA_PROJECT")
        if not proj:
            return {"error": True, "reason": "No Jira project specified. Set JIRA_PROJECT_KEY in .env or pass project_key."}

        payload = {
            "fields": {
                "project": {"key": proj},
                "summary": summary,
                "description": description,
                "issuetype": {"name": issue_type}
            }
        }
        res = self.client.request("POST", "/rest/api/2/issue", data=payload)
        if res.get("error"):
            return {"error": True, "details": res}

        key = res.get("key")
        return {"success": True, "key": key, "url": f"{self.client.get_base_url()}/browse/{key}"}

    def update_issue(self, issue_key: str, description: str = None, summary: str = None, append_description: str = None) -> dict:
        """Updates summary or appends/replaces description of an existing Jira issue."""
        fields_update = {}
        if summary:
            fields_update["summary"] = summary

        if description:
            fields_update["description"] = description
        elif append_description:
            existing = self.get_issue(issue_key)
            old_desc = existing.get("description") or ""
            fields_update["description"] = f"{old_desc}\n\n{append_description}".strip()

        if not fields_update:
            return {"error": True, "reason": "No fields to update provided."}

        res = self.client.request("PUT", f"/rest/api/2/issue/{issue_key}", data={"fields": fields_update})
        if res.get("error"):
            return {"key": issue_key, "error": res}

        return {"success": True, "key": issue_key, "url": f"{self.client.get_base_url()}/browse/{issue_key}"}


# Module instance for easy import
jira_manager = JiraManager()
