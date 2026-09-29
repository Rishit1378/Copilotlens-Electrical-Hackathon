# 🚀 CopilotLens — Work Laptop Setup Guide

This guide explains step-by-step how to get **CopilotLens** running on your work laptop, connected to your company's **Bitbucket** repository inside **IntelliJ IDEA + GitHub Copilot**.

---

## 💡 How It Works (Overview)

```
┌──────────────────────────────────────────────────────────┐
│                      Work Laptop                         │
│                                                          │
│  1. Your Bitbucket Repo (Cloned locally)                │
│     C:\work\my-company-project                           │
│                                                          │
│  2. CopilotLens MCP Server (Cloned from GitHub)         │
│     C:\tools\copilotlens                                 │
│                                                          │
│  3. IntelliJ IDEA (GitHub Copilot Plugin)                │
│     Talks to CopilotLens via MCP Protocol                │
└──────────────────────────────────────────────────────────┘
```

> 🔑 **Key Takeaway:** CopilotLens does NOT connect to GitHub or Bitbucket cloud APIs. It runs **100% locally** on the local folder where your Bitbucket repo is cloned. 

---

## 📋 Prerequisites on Work Laptop

1. **Python 3.9+** installed (`python --version` in terminal).
2. **Git CLI** installed (`git --version`).
3. **IntelliJ IDEA** (version 2024.3 or newer recommended).
4. **GitHub Copilot Plugin** installed and active in IntelliJ.

---

## 🛠️ Step-by-Step Setup

### Step 1: Clone your Bitbucket repo & CopilotLens

1. **Clone your company's Bitbucket repo** as you normally do:
   ```bash
   git clone https://bitbucket.mycompany.com/projects/PROJ/repos/my-app.git C:\work\my-app
   ```
2. **Clone CopilotLens** (pushed from your personal GitHub):
   ```bash
   git clone https://github.com/your-username/copilotlens.git C:\tools\copilotlens
   ```

---

### Step 2: Install Python Dependencies

Open PowerShell or Command Prompt on your work laptop and run:

```bash
cd C:\tools\copilotlens
pip install mcp gitpython
```

*(Note: If your company requires a corporate proxy for `pip`, use: `pip install --proxy http://your-proxy:8080 mcp gitpython`)*

---

### Step 3: Test CopilotLens Standalone (Verify it works)

Before configuring IntelliJ, verify CopilotLens can analyze your local Bitbucket repo:

```bash
python run_dashboard.py --repo "C:\work\my-app"
```

1. It will run a 5-step analysis on your Bitbucket repository.
2. It will auto-open **http://localhost:8765** in your browser.
3. Use the **chat box** on the right side of the dashboard to test queries like:
   - *"What are the riskiest files?"*
   - *"Show co-change pairs"*

---

### Step 4: Configure IntelliJ IDEA to use CopilotLens via MCP

Now hook CopilotLens into IntelliJ so GitHub Copilot can invoke it directly.

#### Option A: Global Configuration (Applies to all projects)

1. Open File Explorer and navigate to your user home directory:
   `C:\Users\<Your-Username>\`
2. Create the missing folders if they don't exist:
   `C:\Users\<Your-Username>\.config\github-copilot\intellij\`
3. Create a file named `mcp.json` inside that folder:
   `C:\Users\<Your-Username>\.config\github-copilot\intellij\mcp.json`

4. Paste the following JSON (replace paths with your actual Windows paths, using forward slashes `/`):

```json
{
  "servers": {
    "copilotlens": {
      "command": "python",
      "args": [
        "C:/tools/copilotlens/mcp_server/server.py",
        "--repo",
        "${workspaceFolder}"
      ],
      "env": {
        "COPILOTLENS_PORT": "8765"
      }
    }
  }
}
```

---

### Step 5: (Optional) Configure Integrations in `.env`

Create a `.env` file in the root of CopilotLens (`C:\tools\copilotlens\.env`) to enable Atlassian, Neo4j, and IntelliJ PSI tools:

```env
# Atlassian Integrations (Jira, Confluence, Bitbucket)
ATLASSIAN_BASE_URL=https://ies-iesd-jira.ies.mentorg.com
ATLASSIAN_EMAIL=your.name@company.com
ATLASSIAN_API_TOKEN=your_pat_or_api_token
ATLASSIAN_JIRA_PROJECT=PROJ
ATLASSIAN_CONFLUENCE_SPACE=SPACE
BITBUCKET_BASE_URL=https://ies-iesd-bitbucket.ies.mentorg.com

# Neo4j Enterprise Code Graph
NEO4J_URI=bolt://10.103.236.11
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=your_password
NEO4J_DATABASE=neo4j

# IntelliJ PSI Tools (running in IntelliJ)
PSI_TOOLS_HOST=localhost
PSI_TOOLS_PORT=3000
PSI_TOOLS_INSPECTION_PORT=3001
```

---

### Step 6: Enable & Test in IntelliJ GitHub Copilot

1. **Open your Bitbucket repository in IntelliJ IDEA** (`C:\work\my-app`).
2. Restart IntelliJ if it was open.
3. Open **GitHub Copilot Chat** window (usually on the right sidebar).
4. Switch Copilot Chat mode from *Ask* to **Agent mode** (or enable Tools/MCP in Copilot settings).
5. Click the 🔧 **Tools / MCP** icon in the Copilot chat window and verify **`copilotlens`** is listed and enabled with 79 tools.

6. **Test a query in Copilot Chat:**
   ```text
   What are the top hotspots in this repository and why are they risky?
   ```
   Copilot will autonomously invoke `copilotlens:get_hotspots` and return an analysis based on your Bitbucket git history!

---

## ⚡ Pro-Tips for Hackathon Demo / Work Laptop

* **Pre-warm the cache:** Run `python run_dashboard.py --repo "C:\work\my-app"` once before presenting. All analytical results will be saved to `.copilotlens_cache.json` in your project folder, ensuring instant (<1s) answers during your demo.
* **No IDE? No problem:** If Copilot token limits are an issue on your work laptop, run `python run_dashboard.py --repo "C:\work\my-app"` and use the **dashboard's built-in web chat** for your demo! It uses the exact same underlying tools.

---

## 🔧 Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `ModuleNotFoundError: mcp` | Dependencies not installed | Run `pip install mcp gitpython` in command prompt |
| Copilot doesn't call tools | `mcp.json` path is incorrect or invalid JSON | Double check forward slashes `/` in path inside `mcp.json` |
| Port 8765 in use | Another dashboard process is running | Change `"COPILOTLENS_PORT": "8766"` in `mcp.json` |
| No git history data | Git repository depth is too shallow | Run `git fetch --unshallow` inside your Bitbucket repo |
| PSI tools connection refused | IntelliJ PSI Tools plugin not running | Verify IntelliJ is running and PSI daemon listens on ports 3000/3001 |
| Neo4j connection failure | VPN/Network access issue | Ensure active connection to corporate network/VPN for `bolt://10.103.236.11` |

