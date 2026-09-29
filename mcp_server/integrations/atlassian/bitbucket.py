"""
Centralized Bitbucket Integration
Handles all Bitbucket operations (PR context, PR listing, comments/annotations) for CoPilotLens.
"""

import os
from .client import AtlassianClient


class BitbucketManager:
    """Centralized manager for all Bitbucket REST API interactions."""

    def __init__(self):
        self.client = AtlassianClient("bitbucket")

    def _is_server(self) -> bool:
        url = os.getenv("BITBUCKET_BASE_URL", "")
        return "bitbucket.org" not in url.lower()

    def get_recent_prs(self, limit: int = 5, project_key: str = None, repo_slug: str = None) -> dict:
        """Fetches the last N Pull Requests opened or merged on Bitbucket."""
        proj = project_key or os.getenv("BITBUCKET_PROJECT_KEY") or os.getenv("BITBUCKET_WORKSPACE") or "PROJ"
        repo = repo_slug or os.getenv("BITBUCKET_REPO_SLUG") or os.getenv("BITBUCKET_REPO") or "repo"

        prs = []
        if self._is_server():
            endpoint = f"/rest/api/1.0/projects/{proj}/repos/{repo}/pull-requests"
            res = self.client.request("GET", endpoint, params={"limit": limit, "state": "ALL"})
            if res.get("error"):
                res = self.client.request("GET", "/rest/api/1.0/dashboard/pull-requests", params={"limit": limit})
            if res.get("error"):
                return {"prs": [], "error": res}

            for item in res.get("values", [])[:limit]:
                author_obj = item.get("author", {}).get("user") or {}
                prs.append({
                    "id": item.get("id"),
                    "title": item.get("title"),
                    "description": item.get("description", "")[:200],
                    "state": item.get("state"),
                    "author": author_obj.get("displayName") or author_obj.get("name"),
                    "created": item.get("createdDate"),
                    "source_branch": (item.get("fromRef") or {}).get("displayId"),
                    "target_branch": (item.get("toRef") or {}).get("displayId"),
                    "url": (item.get("links", {}).get("self", [{}])[0] or {}).get("href")
                })
        else:
            endpoint = f"/2.0/repositories/{proj}/{repo}/pullrequests"
            res = self.client.request("GET", endpoint, params={"pagelen": limit})
            if res.get("error"):
                return {"prs": [], "error": res}

            for item in res.get("values", [])[:limit]:
                prs.append({
                    "id": item.get("id"),
                    "title": item.get("title"),
                    "description": item.get("summary", {}).get("raw", "")[:200],
                    "state": item.get("state"),
                    "author": (item.get("author") or {}).get("display_name"),
                    "created": item.get("created_on"),
                    "url": item.get("links", {}).get("html", {}).get("href")
                })

        return {"total": len(prs), "prs": prs}

    def get_pr_context(self, pr_id: str, project_key: str = None, repo_slug: str = None) -> dict:
        """Fetches Pull Request details (author, branch, modified files, title, description)."""
        proj = project_key or os.getenv("BITBUCKET_PROJECT_KEY") or os.getenv("BITBUCKET_WORKSPACE") or "PROJ"
        repo = repo_slug or os.getenv("BITBUCKET_REPO_SLUG") or os.getenv("BITBUCKET_REPO") or "repo"

        if self._is_server():
            endpoint = f"/rest/api/1.0/projects/{proj}/repos/{repo}/pull-requests/{pr_id}"
            res = self.client.request("GET", endpoint)
            if res.get("error"):
                return {"pr_id": pr_id, "error": res}

            changes_res = self.client.request("GET", f"{endpoint}/changes")
            files_modified = []
            if not changes_res.get("error"):
                for change in changes_res.get("values", []):
                    path_info = change.get("path", {})
                    files_modified.append(path_info.get("toString") or path_info.get("name"))

            return {
                "pr_id": pr_id,
                "title": res.get("title"),
                "description": res.get("description"),
                "state": res.get("state"),
                "author": (res.get("author", {}).get("user") or {}).get("displayName"),
                "source_branch": (res.get("fromRef") or {}).get("displayId"),
                "target_branch": (res.get("toRef") or {}).get("displayId"),
                "files_modified": files_modified,
                "url": (res.get("links", {}).get("self", [{}])[0] or {}).get("href")
            }
        else:
            endpoint = f"/2.0/repositories/{proj}/{repo}/pullrequests/{pr_id}"
            res = self.client.request("GET", endpoint)
            if res.get("error"):
                return {"pr_id": pr_id, "error": res}

            return {
                "pr_id": pr_id,
                "title": res.get("title"),
                "description": res.get("description"),
                "state": res.get("state"),
                "author": (res.get("author") or {}).get("display_name"),
                "source_branch": (res.get("source", {}).get("branch") or {}).get("name"),
                "target_branch": (res.get("destination", {}).get("branch") or {}).get("name"),
                "url": res.get("links", {}).get("html", {}).get("href")
            }

    def annotate_pr(self, pr_id: str, comment_markdown: str, project_key: str = None, repo_slug: str = None) -> dict:
        """Posts a review comment or code health analysis to a Pull Request."""
        proj = project_key or os.getenv("BITBUCKET_PROJECT_KEY") or os.getenv("BITBUCKET_WORKSPACE") or "PROJ"
        repo = repo_slug or os.getenv("BITBUCKET_REPO_SLUG") or os.getenv("BITBUCKET_REPO") or "repo"

        if self._is_server():
            endpoint = f"/rest/api/1.0/projects/{proj}/repos/{repo}/pull-requests/{pr_id}/comments"
            res = self.client.request("POST", endpoint, data={"text": comment_markdown})
        else:
            endpoint = f"/2.0/repositories/{proj}/{repo}/pullrequests/{pr_id}/comments"
            res = self.client.request("POST", endpoint, data={"content": {"raw": comment_markdown}})

        if res.get("error"):
            return {"pr_id": pr_id, "success": False, "error": res}
        return {"pr_id": pr_id, "success": True, "comment_id": res.get("id")}


# Module instance for easy import
bitbucket_manager = BitbucketManager()
