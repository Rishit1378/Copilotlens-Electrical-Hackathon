import sys
sys.path.insert(0, 'mcp_server')
from analyzers.why_analyzer import WhyAnalyzer
from analyzers.search_analyzer import CodebaseSearch
from analyzers.git_analyzer import GitAnalyzer
from analyzers.dependency import DependencyAnalyzer

repo = '.'

print('--- Feature 1: get_why ---')
w = WhyAnalyzer(repo)
r = w.get_why('mcp_server/server.py')
print('  commits analyzed:', r['total_commits_analyzed'])
print('  decision types:', r['decision_breakdown'])
print('  narrative:', r['narrative'][:120])

print()
print('--- Feature 2: search_codebase ---')
s = CodebaseSearch(repo)
r = s.search('get_file_health', search_type='symbol', max_results=5, file_extension='.py')
print('  matches:', r['total_matches'], 'in', r['files_with_matches'], 'files')
if r['results']:
    print('  first match file:', r['results'][0]['file'])

print()
print('--- Feature 3: co_change_pairs ---')
g = GitAnalyzer(repo)
pairs = g.get_co_change_pairs(min_co_changes=1)
print('  pairs found:', len(pairs))
if pairs:
    p = pairs[0]
    print('  top pair:', p['file_a'], '+', p['file_b'], '|', p['co_change_count'], 'co-changes |', p['coupling_strength'])

print()
print('--- Feature 4: get_named_imports ---')
d = DependencyAnalyzer(repo)
r = d.get_named_imports('mcp_server/server.py')
print('  named symbol imports:', r.get('total_named_symbols', 0))
print('  insight:', r.get('insight', ''))
if r.get('named_imports'):
    ni = r['named_imports'][0]
    print('  example: from', ni['from'], '->', ni['symbols'][:3])

print()
print('=== ALL 4 NEW FEATURES WORKING ===')
