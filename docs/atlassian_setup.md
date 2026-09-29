# Atlassian Setup Guide — What to Provide & How to Get It

This guide explains exactly what information CoPilotLens needs to connect to Jira, Confluence,
and Bitbucket, and step-by-step how to get each piece.

---

## What CoPilotLens Uses Atlassian For

### Jira
- Look up open defects/issues linked to a file you are about to modify
- Show you which Jira bugs have been filed against hotspot files
- Optionally create a Jira task from a CoPilotLens finding (dead code, health score drop, etc.)

### Confluence
- One-time: writes an Architecture & Code Health knowledge base to a Confluence space
- You re-run the script manually whenever you want to refresh it
- Copilot can then retrieve relevant docs via `get_confluence_page(topic)` during conversations

### Bitbucket
- Annotate pull requests with blast radius analysis, health score, and recommended tests
- Detect if a file being modified is already in an open PR
- Retrieve PR diff context for analysis

---

## Part 1: Jira + Confluence API Token

Jira and Confluence share the same API token (Atlassian uses one account for both).

### Step 1 — Get your API Token

1. Go to: https://id.atlassian.com/manage-profile/security/api-tokens
   (You must be logged into your Atlassian account)

2. Click **"Create API token"**

3. Give it a label like `CoPilotLens`

4. Click **Create** — the token will be shown ONCE. Copy it immediately.

5. Store it somewhere safe (password manager). You cannot view it again.

### Step 2 — Find your values

| Value | Where to find it | Example |
|---|---|---|
| `ATLASSIAN_BASE_URL` | Your Jira browser URL up to `.net` | `https://yourcompany.atlassian.net` |
| `ATLASSIAN_EMAIL` | The email you use to log into Jira | `aryan@yourcompany.com` |
| `ATLASSIAN_API_TOKEN` | From Step 1 above | `ATATTxxxx...` |
| `ATLASSIAN_JIRA_PROJECT` | The letters before `-` in any issue number | `PROJ` (from `PROJ-123`) |
| `ATLASSIAN_CONFLUENCE_SPACE` | In the URL: `/wiki/spaces/SPACEKEY/pages/...` | `ARCH` or `ENG` |

### Step 3 — Set environment variables

On Windows PowerShell (temporary, for testing):
```powershell
$env:ATLASSIAN_BASE_URL = "https://yourcompany.atlassian.net"
$env:ATLASSIAN_EMAIL = "you@yourcompany.com"
$env:ATLASSIAN_API_TOKEN = "ATAT..."
$env:ATLASSIAN_JIRA_PROJECT = "PROJ"
$env:ATLASSIAN_CONFLUENCE_SPACE = "SPACE"
```

For persistent setup, add to your PowerShell profile or Windows System Environment Variables.

Alternatively, create a `.env` file in `c:\CoPilotLens\` (it is gitignored):
```
ATLASSIAN_BASE_URL=https://yourcompany.atlassian.net
ATLASSIAN_EMAIL=you@yourcompany.com
ATLASSIAN_API_TOKEN=ATATTxxxx
ATLASSIAN_JIRA_PROJECT=PROJ
ATLASSIAN_CONFLUENCE_SPACE=SPACE
```

### Step 4 — Verify the connection (test script)

Once Phase 4 is implemented, run:
```bash
python mcp_server/integrations/atlassian/test_connection.py
```
This will print "Jira OK", "Confluence OK" or specific error messages.

---

## Part 2: Bitbucket Credentials

Bitbucket Cloud (bitbucket.org) and Bitbucket Server (self-hosted) use different auth methods.

### If you use Bitbucket Cloud (bitbucket.org)

1. Go to: https://bitbucket.org/account/settings/app-passwords/new
2. Give it a label: `CoPilotLens`
3. Enable these permissions:
   - Repositories: **Read**
   - Pull requests: **Read**, **Write** (Write only needed for PR annotation)
4. Click **Create** — copy the app password immediately.

| Value | Where to find it | Example |
|---|---|---|
| `BITBUCKET_BASE_URL` | Always this | `https://api.bitbucket.org` |
| `BITBUCKET_USERNAME` | Your Bitbucket username (not email) | `aryan_c` |
| `BITBUCKET_APP_PASSWORD` | From step 4 above | `ATBBxxxx...` |
| `BITBUCKET_WORKSPACE` | In your repo URL: `bitbucket.org/WORKSPACE/repo` | `myteam` |
| `BITBUCKET_REPO` | Your repository slug (last part of URL) | `my-java-app` |

### If you use Bitbucket Server (self-hosted, e.g. bitbucket.mycompany.com)

1. Log in to your self-hosted Bitbucket
2. Go to your profile → **Personal access tokens** → **Create token**
3. Set permissions: Repositories: Read, Pull Requests: Read + Write

| Value | Where to find it | Example |
|---|---|---|
| `BITBUCKET_BASE_URL` | Your server URL | `https://bitbucket.mycompany.com` |
| `BITBUCKET_USERNAME` | Your username | `aryan` |
| `BITBUCKET_APP_PASSWORD` | Personal access token from step 3 | `NTM...` |
| `BITBUCKET_WORKSPACE` | Project key in Bitbucket Server | `PROJ` |
| `BITBUCKET_REPO` | Repository slug | `my-java-app` |

Set environment variables the same way as Jira above.

---

## What Information to Send When Asking for Help

If you are asking an AI assistant to help configure Atlassian integration, share:
1. Your `ATLASSIAN_BASE_URL` (safe to share — this is public)
2. Whether you use Bitbucket Cloud or Server
3. Your `ATLASSIAN_JIRA_PROJECT` key
4. Your `ATLASSIAN_CONFLUENCE_SPACE` key

**Never share** your API token, app password, or personal access token with anyone.

---

## Confluence Knowledge Base — What Gets Created

When you run `python mcp_server/integrations/atlassian/build_knowledge_base.py`, it creates
a structured set of pages in your Confluence space:

```
[Your Space]
└── CoPilotLens Architecture Docs/
    ├── Overview — repo health summary + grade
    ├── Hotspot Files — top 20 high-risk files with git history
    ├── Module Ownership Map — who owns what
    ├── Dependency Architecture — hub files, circular deps
    ├── Dead Code Inventory — confirmed unused symbols
    └── Test Coverage Gaps — files with no test coverage
```

These pages are tagged and cross-linked. Copilot references them via:
```
get_confluence_page("hotspots")
get_confluence_page("dependency architecture")
```

This is a ONE-TIME write. Re-run the script any time you want to refresh the docs.
