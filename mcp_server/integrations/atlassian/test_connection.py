"""
Test script to verify Jira, Confluence, and Bitbucket connection using centralized managers.
Run via:
    python mcp_server/integrations/atlassian/test_connection.py
"""

import sys
from pathlib import Path

server_dir = Path(__file__).resolve().parents[2]
if str(server_dir) not in sys.path:
    sys.path.insert(0, str(server_dir))

from integrations.atlassian.client import load_env_file
from integrations.atlassian.jira import jira_manager
from integrations.atlassian.confluence import confluence_manager
from integrations.atlassian.bitbucket import bitbucket_manager

def main():
    load_env_file()
    print("=" * 60)
    print("CoPilotLens -- Atlassian Connection Diagnostic")
    print("=" * 60)

    # 1. Jira
    print("\n[1/3] Testing Jira Connection...")
    try:
        url = jira_manager.client.get_base_url()
        res = jira_manager.client.request("GET", "/rest/api/2/myself")
        if res.get("error"):
            print(f"  [FAIL] Jira Error: {res.get('reason')}")
        else:
            name = res.get("displayName") or res.get("name")
            print(f"  [SUCCESS] Jira Connection Successful! Logged in as: {name} ({url})")
    except Exception as e:
        print(f"  [ERROR] Jira Exception: {e}")

    # 2. Confluence
    print("\n[2/3] Testing Confluence Connection...")
    try:
        url = confluence_manager.client.get_base_url()
        res = confluence_manager.client.request("GET", "/rest/api/user/current")
        if res.get("error"):
            print(f"  [FAIL] Confluence Error: {res.get('reason')}")
        else:
            name = res.get("displayName") or res.get("username")
            print(f"  [SUCCESS] Confluence Connection Successful! Logged in as: {name} ({url})")
    except Exception as e:
        print(f"  [ERROR] Confluence Exception: {e}")

    # 3. Bitbucket
    print("\n[3/3] Testing Bitbucket Connection...")
    try:
        url = bitbucket_manager.client.get_base_url()
        res = bitbucket_manager.get_recent_prs(limit=1)
        if res.get("error"):
            print(f"  [FAIL] Bitbucket Error: {res.get('error')}")
        else:
            print(f"  [SUCCESS] Bitbucket Connection Successful! ({url})")
    except Exception as e:
        print(f"  [ERROR] Bitbucket Exception: {e}")

    print("\n" + "=" * 60)

if __name__ == "__main__":
    main()
