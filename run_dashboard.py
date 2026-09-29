"""
CopilotLens - Dashboard-only runner
Starts the HTTP server INSTANTLY and loads analysis in the background or from cache.
Usage: python run_dashboard.py --repo demo_project
"""

import sys
import os
import json
import time
import argparse
import threading
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from mcp_server.analyzers.code_health import CodeHealthScorer
from mcp_server.analyzers.git_analyzer import GitAnalyzer
from mcp_server.analyzers.dependency import DependencyAnalyzer
from mcp_server.analyzers.dead_code import DeadCodeDetector

# ── Args ───────────────────────────────────────────────────────────────────────
parser = argparse.ArgumentParser(description="CopilotLens Dashboard")
parser.add_argument("--repo", default="demo_project", help="Path to the repo to analyze")
parser.add_argument("--port", type=int, default=8765, help="Dashboard port")
args = parser.parse_args()

REPO = args.repo
PORT = args.port

DASHBOARD_DATA = {"status": "loading", "repo_path": REPO}
DASHBOARD_DIR = Path(__file__).parent / "dashboard"

# ── Background Analyzer Thread ────────────────────────────────────────────────
def run_analysis():
    global DASHBOARD_DATA
    print(f"\n{'='*55}")
    print(f"  CopilotLens Dashboard Engine Starting")
    print(f"  Repo: {REPO}")
    print(f"{'='*55}\n")

    print("[ ] Step 1/5 -- Scoring code health...")
    health_scorer = CodeHealthScorer(REPO)
    health_data = health_scorer.get_summary()
    print(f"[+] {health_data['total_files']} files scored -- avg {health_data['avg_score']}/100")

    print("[ ] Step 2/5 -- Analyzing git history...")
    git_analyzer = GitAnalyzer(REPO)
    repo_summary = git_analyzer.get_repo_summary()
    hotspots = git_analyzer.get_hotspots(15)
    print(f"[+] {repo_summary['total_commits']} commits, {len(hotspots)} hotspots found")

    print("[ ] Step 3/5 -- Building dependency graph...")
    dep_analyzer = DependencyAnalyzer(REPO)
    dep_graph = dep_analyzer.build_graph()
    print(f"[+] {len(dep_graph['nodes'])} nodes, {len(dep_graph['edges'])} edges")

    print("[ ] Step 4/5 -- Detecting dead code...")
    dead_detector = DeadCodeDetector(REPO)
    dead_code = dead_detector.find_dead_code()
    print(f"[+] {len(dead_code)} dead code candidates found")

    print("[ ] Step 5/6 -- Finding co-change pairs...")
    co_change_pairs = git_analyzer.get_co_change_pairs(min_co_changes=3)
    print(f"[+] {len(co_change_pairs)} co-change pairs found")

    print("[ ] Step 6/6 -- Calculating Blast Radius for key files...")
    from mcp_server.analyzers.blast_radius import BlastRadiusAnalyzer
    blast_analyzer = BlastRadiusAnalyzer(REPO, dep_analyzer, git_analyzer)
    blast_radius_data = []
    
    # Pick files from co-change pairs and hotspots that have real connections
    target_sample = []
    for pair in co_change_pairs[:3]:
        target_sample.append(pair["file_a"])
    for h in hotspots[:3]:
        if h["path"] not in target_sample:
            target_sample.append(h["path"])

    for target_path in target_sample[:5]:
        b = blast_analyzer.calculate_blast_radius(target_path)
        blast_radius_data.append(b)
    print(f"[+] Calculated {len(blast_radius_data)} blast radius sets")

    print("[ ] Step 7/7 -- Running Coverity static analysis rule checks...")
    from mcp_server.analyzers.coverity_analyzer import CoverityAnalyzer
    coverity_analyzer = CoverityAnalyzer(REPO)
    coverity_summary = coverity_analyzer.get_summary()
    print(f"[+] {coverity_summary['total_defects']} Coverity defects found across {coverity_summary['affected_files_count']} files (Compliance: {coverity_summary['rule_compliance_score']}%)")

    module_owners = git_analyzer.get_module_owners()
    print(f"[+] {len(module_owners)} module owners tracked")

    DASHBOARD_DATA = {
        "status": "ready",
        "repo_path": REPO,
        "health": health_data,
        "hotspots": hotspots,
        "dead_code": dead_code,
        "coverity": coverity_summary,
        "module_owners": module_owners,
        "dependency_graph": {
            "nodes": dep_graph["nodes"],
            "edges": dep_graph["edges"],
            "circular": dep_graph.get("circular_dependencies", []),
            "orphans": dep_graph.get("orphan_files", [])
        },
        "co_change_pairs": co_change_pairs,
        "blast_radius": blast_radius_data,
        "repo_summary": repo_summary
    }
    try:
        cache_path = Path(REPO) / ".dashboard_cache.json"
        cache_path.write_text(json.dumps(DASHBOARD_DATA, indent=2))
        print(f"[+] Dashboard data cached at {cache_path}")
    except Exception as e:
        print(f"[-] Failed to cache dashboard data")

    print(f"\n[+] Analysis complete! Dashboard fully populated at http://localhost:{PORT}\n")

# ── HTTP Handler ───────────────────────────────────────────────────────────────
class DashboardHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        if "/api/" in self.path:
            print(f"   [{time.strftime('%H:%M:%S')}] {self.requestline}")

    def do_POST(self):
        length = int(self.headers.get('Content-Length', 0))
        body_data = self.rfile.read(length).decode('utf-8') if length > 0 else "{}"
        try:
            req_json = json.loads(body_data) if body_data else {}
        except Exception:
            req_json = {}

        if self.path == "/api/sync-instructions":
            from mcp_server.server import generate_copilot_instructions
            result = generate_copilot_instructions()
            self._json(json.loads(result))
        elif self.path == "/api/coverity/import":
            from mcp_server.analyzers.coverity_analyzer import CoverityAnalyzer
            cov = CoverityAnalyzer(REPO)
            res = cov.load_coverity_json(req_json.get("json_content", req_json.get("json_path", "")))
            DASHBOARD_DATA["coverity"] = cov.get_summary()
            self._json(res)
        elif self.path == "/api/coverity/scan":
            from mcp_server.analyzers.coverity_analyzer import CoverityAnalyzer
            cov = CoverityAnalyzer(REPO)
            res = cov.run_scan()
            DASHBOARD_DATA["coverity"] = res
            self._json({"status": "SUCCESS", "summary": res})
        else:
            self._text(404, "Not found")

    def do_GET(self):
        next_out_dir = Path(__file__).parent / "dashboard-next" / "out"
        dash_dir = next_out_dir if next_out_dir.exists() else DASHBOARD_DIR

        if self.path == "/api/data":
            self._json(DASHBOARD_DATA)
        elif self.path == "/api/sync-instructions":
            from mcp_server.server import generate_copilot_instructions
            result = generate_copilot_instructions()
            self._json(json.loads(result))
        else:
            rel_path = self.path.lstrip("/")
            if not rel_path or rel_path == "index.html":
                target_file = dash_dir / "index.html"
            else:
                target_file = dash_dir / rel_path

            if target_file.exists() and target_file.is_file():
                content_type = "text/html; charset=utf-8"
                if target_file.suffix == ".css":
                    content_type = "text/css"
                elif target_file.suffix == ".js":
                    content_type = "application/javascript"
                elif target_file.suffix == ".json":
                    content_type = "application/json"
                elif target_file.suffix == ".svg":
                    content_type = "image/svg+xml"

                self._file(target_file, content_type)
            else:
                self._text(404, "Not found")

    def _json(self, obj):
        body = json.dumps(obj).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def _file(self, path, content_type):
        if Path(path).exists():
            body = Path(path).read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", len(body))
            self.end_headers()
            self.wfile.write(body)
        else:
            self._text(404, f"File not found: {path}")

    def _text(self, code, msg):
        body = msg.encode()
        self.send_response(code)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)


# ── Start Server Immediately ─────────────────────────────────────────────────
server = HTTPServer(("localhost", PORT), DashboardHandler)

print(f"\n{'='*55}")
print(f"  CopilotLens Dashboard Server Running!")
print(f"  Open in browser: http://localhost:{PORT}")
print(f"{'='*55}\n")

# Start background calculation thread
threading.Thread(target=run_analysis, daemon=True).start()

# Auto-open browser
def open_browser():
    time.sleep(0.5)
    webbrowser.open(f"http://localhost:{PORT}")

threading.Thread(target=open_browser, daemon=True).start()

try:
    server.serve_forever()
except KeyboardInterrupt:
    print("\n\nDashboard stopped.")
