"""
Centralized Confluence Integration
Handles all Confluence operations (search, read, publish, edit) for CoPilotLens.
"""

import os
from .client import AtlassianClient


class ConfluenceManager:
    """Centralized manager for all Confluence REST API interactions."""

    def __init__(self):
        self.client = AtlassianClient("confluence")

    def get_page(self, title_or_id: str, space_key: str = None) -> dict:
        """Retrieves full content of a Confluence page by exact numeric ID or title search."""
        if str(title_or_id).isdigit():
            page_id = str(title_or_id)
            res = self.client.request("GET", f"/rest/api/content/{page_id}", params={"expand": "body.storage,version,space"})
            if not res.get("error"):
                return {
                    "id": res.get("id"),
                    "title": res.get("title"),
                    "space": res.get("space", {}).get("key"),
                    "url": f"{self.client.get_base_url()}{res.get('_links', {}).get('webui', '')}",
                    "content_storage": res.get("body", {}).get("storage", {}).get("value", ""),
                    "version": res.get("version", {}).get("number")
                }

        space = space_key or os.getenv("CONFLUENCE_SPACE_KEY") or os.getenv("ATLASSIAN_CONFLUENCE_SPACE")
        cql = f'title ~ "{title_or_id}"'
        if space:
            cql = f'space = "{space}" AND {cql}'

        res = self.client.request("GET", "/rest/api/content/search", params={"cql": cql, "limit": 1, "expand": "body.storage,version,space"})
        if res.get("error") or not res.get("results"):
            return self.search_pages(title_or_id, space_key)

        page = res["results"][0]
        return {
            "id": page.get("id"),
            "title": page.get("title"),
            "space": page.get("space", {}).get("key"),
            "url": f"{self.client.get_base_url()}{page.get('_links', {}).get('webui', '')}",
            "content_storage": page.get("body", {}).get("storage", {}).get("value", ""),
            "version": page.get("version", {}).get("number")
        }

    def search_pages(self, query: str, space_key: str = None, limit: int = 10) -> dict:
        """Searches Confluence using CQL."""
        space = space_key or os.getenv("CONFLUENCE_SPACE_KEY") or os.getenv("ATLASSIAN_CONFLUENCE_SPACE")
        cql = f'text ~ "{query}"'
        if space:
            cql = f'space = "{space}" AND {cql}'

        res = self.client.request("GET", "/rest/api/content/search", params={"cql": cql, "limit": limit, "expand": "body.storage,version,space"})
        if res.get("error"):
            return {"query": query, "results": [], "error": res}

        results = []
        for page in res.get("results", []):
            results.append({
                "id": page.get("id"),
                "title": page.get("title"),
                "space": page.get("space", {}).get("key"),
                "url": f"{self.client.get_base_url()}{page.get('_links', {}).get('webui', '')}",
                "snippet": page.get("body", {}).get("storage", {}).get("value", "")[:400]
            })
        return {"query": query, "total": len(results), "results": results}

    def publish_page(self, title: str, html_content: str, space_key: str = None, parent_id: str = None) -> dict:
        """Creates or updates a Confluence page."""
        space = space_key or os.getenv("CONFLUENCE_SPACE_KEY") or os.getenv("ATLASSIAN_CONFLUENCE_SPACE")
        if not space:
            return {"error": True, "reason": "No Confluence space key specified."}

        existing = self.get_page(title, space_key=space)
        if existing.get("id") and not existing.get("error"):
            page_id = existing["id"]
            version_num = (existing.get("version") or 1) + 1
            payload = {
                "version": {"number": version_num},
                "title": title,
                "type": "page",
                "body": {"storage": {"value": html_content, "representation": "storage"}}
            }
            res = self.client.request("PUT", f"/rest/api/content/{page_id}", data=payload)
        else:
            payload = {
                "title": title,
                "type": "page",
                "space": {"key": space},
                "body": {"storage": {"value": html_content, "representation": "storage"}}
            }
            if parent_id:
                payload["ancestors"] = [{"id": parent_id}]
            res = self.client.request("POST", "/rest/api/content", data=payload)

        return res

    def update_page(self, title_or_id: str, prepend_html: str = None, append_html: str = None, new_html: str = None, space_key: str = None) -> dict:
        """Edits an existing Confluence page by prepending, appending, or replacing HTML storage content."""
        page = self.get_page(title_or_id, space_key)
        if page.get("error") or not page.get("id"):
            return {"error": True, "reason": f"Could not find Confluence page '{title_or_id}' to update."}

        page_id = page["id"]
        title = page["title"]
        space = page.get("space") or space_key
        version_num = (page.get("version") or 1) + 1
        existing_html = page.get("content_storage") or ""

        if new_html:
            final_html = new_html
        else:
            final_html = existing_html
            if prepend_html:
                final_html = f"{prepend_html}\n{final_html}"
            if append_html:
                final_html = f"{final_html}\n{append_html}"

        payload = {
            "version": {"number": version_num},
            "title": title,
            "type": "page",
            "space": {"key": space},
            "body": {"storage": {"value": final_html, "representation": "storage"}}
        }

        res = self.client.request("PUT", f"/rest/api/content/{page_id}", data=payload)
        if res.get("error"):
            return {"id": page_id, "title": title, "error": res}

        return {"success": True, "id": page_id, "title": title, "version": version_num, "url": page.get("url")}


# Module instance for easy import
confluence_manager = ConfluenceManager()
