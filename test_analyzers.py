import sys
sys.path.insert(0, '.')
from mcp_server.analyzers.code_health import CodeHealthScorer
from mcp_server.analyzers.git_analyzer import GitAnalyzer

repo = '.'
print('=== CopilotLens Analyzer Verification ===')
print()

# ── Health Score ──────────────────────────────────────────────
print('[1/2] Health scoring (limit 200 files)...')
h = CodeHealthScorer(repo)
summary = h.get_summary()
avg = summary['avg_score']
grade = summary['grade']
total = summary['total_files']
dist = summary['distribution']
print(f'  Score  : {avg}/100  Grade: {grade}')
print(f'  Files  : {total} scored')
print(f'  Dist   : critical={dist.get("critical",0)}  poor={dist.get("poor",0)}  fair={dist.get("fair",0)}  good={dist.get("good",0)}  excellent={dist.get("excellent",0)}')
print()
print('  WORST FILES:')
for f in summary.get('worst_files', [])[:8]:
    issues = ', '.join(m['id'] for m in f.get('markers',[]) if m['impact'] < 0)[:60]
    print(f'    [{f["score"]:>3}/100 {f["grade"]}] {f["path"]}')
    if issues:
        print(f'           issues: {issues}')
print()

# ── Git Hotspots ──────────────────────────────────────────────
print('[2/2] Git hotspot analysis...')
g = GitAnalyzer(repo)
gs = g.get_repo_summary()
print(f'  Commits (last 50)  : {gs["total_commits"]}')
print(f'  Files changed      : {gs["total_files_changed"]}')
contribs = gs.get("active_contributors_90d", [])
print(f'  Contributors       : {len(contribs)}')
if contribs:
    print(f'  Top contributor    : {contribs[0]["name"]} ({contribs[0]["commits"]} commits)')
print()

hotspots = g.get_hotspots(10)
print('  TOP 10 HOTSPOTS:')
for h in hotspots:
    print(f'    [{h["risk_level"]:>8}]  {h["commit_count"]:>3} commits  {h["path"]}')
print()

print('=== DONE ===')
