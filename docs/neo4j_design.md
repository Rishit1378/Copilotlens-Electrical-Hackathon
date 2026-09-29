# Neo4j Knowledge Graph — Design Document (Deferred)

**Status: NOT IMPLEMENTING — documented for future reference**

User decision (2026-09-27): Skip Neo4j for now. Revisit after Phases 1-4 are complete.

---

## What Neo4j Would Add

Neo4j would turn CoPilotLens from a file-by-file analyzer into a system that understands
relationships across all entities: files, symbols, tests, Jira issues, authors, dependencies.

This enables queries that are impossible with current flat analysis:
- "Which tests cover symbols that were changed AND have historically been linked to Jira bugs?"
- "Which external dependency is imported by the most files AND has open CVEs?"
- "Who has written code that calls PaymentGateway?"
- "Show all circular dependency chains at the module level across 10,000 files"

---

## Graph Schema

### Node Types

```cypher
(:File {
  path: String,          // relative path from repo root
  language: String,      // java, python, js, ts
  health_score: Float,   // 0-100 from code_health.py
  churn: Integer,        // commit count in last 90 days
  is_hotspot: Boolean,
  is_hub: Boolean        // imported by 5+ other files
})

(:Symbol {
  name: String,
  type: String,          // method, class, interface, field
  file_path: String,
  line_start: Integer,
  line_end: Integer,
  is_public: Boolean,
  is_test: Boolean
})

(:Test {
  name: String,          // fully qualified test method name
  file_path: String,
  framework: String,     // junit4, junit5, pytest, jest
  last_result: String,   // PASSED, FAILED, SKIPPED
  last_run: DateTime
})

(:JiraIssue {
  key: String,           // e.g. PROJ-123
  summary: String,
  status: String,        // Open, In Progress, Resolved
  priority: String,      // Critical, High, Medium, Low
  issue_type: String,    // Bug, Task, Story
  created: DateTime,
  resolved: DateTime
})

(:Author {
  email: String,
  name: String
})

(:Dependency {
  name: String,          // e.g. spring-core, guava
  version: String,
  group_id: String,      // Maven groupId
  artifact_id: String,   // Maven artifactId
  has_cve: Boolean
})
```

### Relationship Types

```cypher
(:File)-[:IMPORTS]->(:File)
(:File)-[:DEFINES]->(:Symbol)
(:Symbol)-[:CALLS]->(:Symbol)
(:Symbol)-[:TESTED_BY]->(:Test)
(:Test)-[:LINKED_TO]->(:JiraIssue)   // via Jira issue key in commit message
(:File)-[:CHANGED_BY {commit_count: Int}]->(:Author)
(:File)-[:DEPENDS_ON]->(:Dependency)
(:JiraIssue)-[:AFFECTS]->(:File)
(:Author)-[:OWNS]->(:File)            // primary contributor by commit count
```

---

## Cypher Queries

### Regression Risk: Tests to run after changing a file
```cypher
MATCH (f:File {path: $changed_file})-[:DEFINES]->(s:Symbol)
      <-[:CALLS*1..3]-(caller:Symbol)
      <-[:DEFINES]-(test_file:File)
      -[:DEFINES]->(t:Test)
WHERE test_file.path STARTS WITH 'test'
RETURN t.name, t.file_path, count(caller) AS coverage_paths
ORDER BY coverage_paths DESC
LIMIT 20
```

### Highest-risk Coverity defects (impact + churn + no test)
```cypher
MATCH (f:File)
WHERE f.churn > 10 AND NOT (f)<-[:DEPENDS_ON]-(:Test)
RETURN f.path, f.churn, f.health_score
ORDER BY f.churn DESC
```

### Author expertise: who knows PaymentGateway?
```cypher
MATCH (a:Author)-[:CHANGED_BY]-(f:File)-[:DEFINES]->(s:Symbol)
WHERE s.name CONTAINS 'PaymentGateway'
RETURN a.email, a.name, count(s) AS symbols_touched
ORDER BY symbols_touched DESC
```

### Circular dependency chains
```cypher
MATCH path = (f:File)-[:IMPORTS*2..5]->(f)
RETURN [n IN nodes(path) | n.path] AS cycle
LIMIT 20
```

---

## Implementation Plan (When Ready to Implement)

### Step 1: Infrastructure
```bash
# Option A: Local Docker
docker run -p 7474:7474 -p 7687:7687 -e NEO4J_AUTH=neo4j/password neo4j:5

# Option B: Neo4j Aura free tier
# https://neo4j.com/cloud/platform/aura-graph-database/
```

Required env vars:
```
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=password
```

### Step 2: New files to create
```
mcp_server/integrations/neo4j/
  __init__.py
  graph_builder.py      <- Populates Neo4j from AST + git + Jira data
  query_engine.py       <- Pre-defined Cypher queries exposed as MCP tools
  schema.py             <- Creates constraints + indexes
```

New pip deps:
```
neo4j>=5.0.0
```

### Step 3: New MCP tools
- `query_code_graph(natural_language_query)` — translates to Cypher via pattern matching
- `get_regression_risk(changed_files)` — graph-powered risk analysis
- `get_dependency_risks()` — vulnerable/outdated deps with file-level impact
- `build_code_graph()` — admin tool to (re)populate the Neo4j graph

### Step 4: Graph population command
```bash
python mcp_server/integrations/neo4j/build_graph.py --repo /path/to/repo
```
Takes 5-30 minutes for a large Java codebase. Run overnight or CI.

---

## Prerequisites Before Starting Neo4j Phase

1. Phase 1 (Tree-sitter) must be complete — graph_builder.py uses AST data
2. Phase 3 (Test Intelligence) should be complete — test-to-symbol mapping goes into graph
3. Phase 4 (Atlassian) should be complete — JiraIssue nodes link to File/Symbol nodes
4. Neo4j instance (Docker or Aura) must be running
5. neo4j pip package installed
