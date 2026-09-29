"""
Atlassian API Client Base
Handles HTTP requests for Jira, Confluence, and Bitbucket.
Supports both Data Center / Server (Bearer PAT) and Cloud (Basic Auth) setups.
"""

import base64
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


def load_env_file():
    """Loads environment variables from .env if present."""
    # Look for .env in project root or current working dir
    possible_paths = [
        Path(__file__).resolve().parents[3] / ".env",  # c:\CoPilotLens\.env
        Path.cwd() / ".env",
    ]
    for env_path in possible_paths:
        if env_path.exists():
            try:
                for line in env_path.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, val = line.split("=", 1)
                        key = key.strip()
                        val = val.strip().strip("'\"")
                        if key and key not in os.environ:
                            os.environ[key] = val
                break
            except Exception:
                pass


# Auto-load on import
load_env_file()


class AtlassianClient:
    """Base HTTP client for Atlassian REST APIs."""

    def __init__(self, service: str):
        """
        service: 'jira', 'confluence', or 'bitbucket'
        """
        self.service = service.lower()

    def get_auth_headers(self) -> dict:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "CoPilotLens-MCP/2.0",
        }

        # Check for service-specific PATs (Data Center / Server setup)
        if self.service == "jira" and os.getenv("JIRA_PAT"):
            headers["Authorization"] = f"Bearer {os.getenv('JIRA_PAT').strip()}"
            return headers

        if self.service == "confluence" and os.getenv("CONFLUENCE_PAT"):
            headers["Authorization"] = f"Bearer {os.getenv('CONFLUENCE_PAT').strip()}"
            return headers

        if self.service == "bitbucket" and os.getenv("BITBUCKET_TOKEN"):
            headers["Authorization"] = f"Bearer {os.getenv('BITBUCKET_TOKEN').strip()}"
            return headers

        # Check for Atlassian Cloud / Unified API Token
        api_token = os.getenv("ATLASSIAN_API_TOKEN") or os.getenv("BITBUCKET_APP_PASSWORD")
        email = os.getenv("ATLASSIAN_EMAIL") or os.getenv("BITBUCKET_USERNAME")

        if api_token and email:
            cred_bytes = f"{email}:{api_token}".encode("utf-8")
            b64_creds = base64.b64encode(cred_bytes).decode("utf-8")
            headers["Authorization"] = f"Basic {b64_creds}"
        elif api_token:
            headers["Authorization"] = f"Bearer {api_token.strip()}"

        return headers

    def get_base_url(self) -> str:
        if self.service == "jira":
            url = os.getenv("JIRA_BASE_URL") or os.getenv("ATLASSIAN_BASE_URL")
        elif self.service == "confluence":
            url = os.getenv("CONFLUENCE_BASE_URL") or os.getenv("ATLASSIAN_BASE_URL")
        elif self.service == "bitbucket":
            url = os.getenv("BITBUCKET_BASE_URL") or "https://api.bitbucket.org"
        else:
            url = None

        if not url:
            raise ValueError(f"No Base URL configured for {self.service}. Check your .env file.")

        return url.rstrip("/")

    def request(self, method: str, endpoint: str, data: dict = None, params: dict = None) -> dict:
        base_url = self.get_base_url()
        full_url = f"{base_url}{endpoint}"

        if params:
            query_string = urllib.parse.urlencode(params)
            full_url = f"{full_url}?{query_string}"

        headers = self.get_auth_headers()
        body = json.dumps(data).encode("utf-8") if data else None

        req = urllib.request.Request(full_url, data=body, headers=headers, method=method.upper())

        try:
            with urllib.request.urlopen(req, timeout=15) as response:
                resp_text = response.read().decode("utf-8")
                if resp_text:
                    return json.loads(resp_text)
                return {"status": "success", "code": response.status}
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8") if e.fp else ""
            try:
                err_json = json.loads(err_body)
            except Exception:
                err_json = {"raw_error": err_body or str(e)}
            return {"error": True, "code": e.code, "reason": e.reason, "details": err_json}
        except Exception as e:
            return {"error": True, "reason": str(e)}
