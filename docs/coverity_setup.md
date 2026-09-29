# Coverity Integration Setup

## What CoPilotLens Does With Coverity Output

CoPilotLens reads your existing Coverity scan results (a JSON file you export from Coverity)
and combines them with its own analysis to produce higher-quality prioritization:

- **Composite risk score** = Coverity severity + git churn rate of the file
  (a NULL_DEREFERENCE in a file changed 40 times in 90 days is much more urgent than
   the same issue in a file nobody touches)

- **Hotspot overlap**: Which Coverity defects are in git hotspot files? Those are your
  highest-priority fixes.

- **Test gap overlay**: Which Coverity defects are in files with no test coverage?

- **Fix hints**: Built-in canonical fix patterns per checker type — no LLM call needed.

---

## Step 1 — Export Coverity Results as JSON

Coverity **does** support JSON export via `cov-format-errors`. Run this command with your
Coverity installation:

```bash
cov-format-errors --dir <coverity-output-dir> --json-output-v8 coverity_report.json
```

Replace `<coverity-output-dir>` with the directory Coverity wrote its analysis to
(the `idir` or `output` folder from `cov-build` / `cov-analyze`).

This produces a `coverity_report.json` file. Save it somewhere accessible, e.g.:
```
C:\work\my-java-app\coverity_report.json
```

---

## Step 2 — Set the Environment Variable

```powershell
$env:COVERITY_REPORT_PATH = "C:\work\my-java-app\coverity_report.json"
```

Or add to your `.env` file in `c:\CoPilotLens\`:
```
COVERITY_REPORT_PATH=C:/work/my-java-app/coverity_report.json
```

---

## Expected JSON Structure

CoPilotLens expects the standard `cov-format-errors --json-output-v8` format:

```json
{
  "issues": [
    {
      "mergeKey": "abc123def456",
      "checkerName": "NULL_RETURNS",
      "subcategory": "null_return",
      "type": "Error",
      "impact": "High",
      "file": "src/com/example/service/UserService.java",
      "line": 142,
      "description": "Variable 'user' returned from method may be null",
      "events": [
        {
          "eventDescription": "Returned null",
          "filePathname": "src/com/example/service/UserService.java",
          "lineNumber": 138
        }
      ]
    }
  ]
}
```

Key fields CoPilotLens uses:
- `checkerName` — type of defect (NULL_RETURNS, RESOURCE_LEAK, etc.)
- `impact` — High/Medium/Low (from Coverity)
- `file` — relative path to source file
- `line` — line number of the defect

---

## Coverity Checker Reference

These are the typical Coverity checker categories (Black Duck / Synopsys) that
CoPilotLens understands and can provide fix hints for:

| Checker | Category | What It Means |
|---|---|---|
| `NULL_RETURNS` | Null handling | A method may return null; caller doesn't check |
| `FORWARD_NULL` | Null handling | Pointer/ref used after a null-returning call |
| `DEREFERENCE` | Null handling | Dereferencing a potentially-null pointer |
| `RESOURCE_LEAK` | Resource management | Stream/connection opened but not closed |
| `USE_AFTER_FREE` | Memory | Memory used after `free()` |
| `OVERRUN` | Memory | Buffer/array index out of bounds |
| `DEADCODE` | Logic | Code that can never be reached |
| `DIVIDE_BY_ZERO` | Arithmetic | Division where denominator may be 0 |
| `UNINIT` | Initialization | Variable used before being assigned |
| `COPY_PASTE_ERROR` | Logic | Likely copy-paste mistake (same condition on both branches) |
| `UNCHECKED_RETURN_VALUE` | Error handling | Return value of a function not checked |
| `TAINTED_SCALAR` | Security | User-controlled data used unsafely |
| `OS_CMD_INJECTION` | Security | Shell command injection risk |
| `SQL_INJECTION` | Security | SQL injection risk |
| `INTEGER_OVERFLOW` | Arithmetic | Integer wraps around unexpectedly |

---

## Coverity Data Store (`.coverity_store.json`)

### Why a Separate Store?

The raw Coverity JSON is just a flat defect list. CoPilotLens ingests it once, enriches it,
and writes a persistent **Coverity-specific data store** that:

- Does **not** expire (unlike the general `AnalysisCache` which has a 5-min TTL)
- Contains composite risk scores, git context, and fix hints per issue
- Is queryable by file, checker type, risk score, or merge key
- Can track issue acknowledgement status (`open` / `fixed` / `wontfix`)

### Store Schema

```json
{
  "generated_at": "2026-09-27T14:30:00Z",
  "source_file": "coverity_report.json",
  "source_hash": "sha256:abc123...",
  "summary": {
    "total": 142,
    "high_risk": 23,
    "checkers": {
      "NULL_RETURNS": 41,
      "RESOURCE_LEAK": 28,
      "FORWARD_NULL": 19
    }
  },
  "issues": [
    {
      "merge_key": "abc123",
      "checker": "FORWARD_NULL",
      "impact": "High",
      "file": "src/service/UserService.java",
      "line": 142,
      "description": "Variable 'user' may be null here",
      "git_churn_90d": 38,
      "has_test_coverage": false,
      "composite_risk_score": 9.2,
      "fix_hint": "Check return value of getUserById() before use. Pattern: if (user == null) { throw new NotFoundException(...); }",
      "status": "open",
      "acknowledged_by": null
    }
  ],
  "fix_hints": {
    "FORWARD_NULL": "...",
    "NULL_RETURNS": "...",
    "RESOURCE_LEAK": "..."
  }
}
```

### Composite Risk Score

```
composite_risk_score = (impact_weight * severity) + (churn_factor * git_churn_90d)

impact_weight:  High=3, Medium=2, Low=1
churn_factor:   files changed >30x in 90d get a multiplier boost
```

### Data Store vs. General Cache

| | `AnalysisCache` (`.copilotlens_cache.json`) | Coverity Store (`.coverity_store.json`) |
|---|---|---|
| TTL | 5 minutes | None — manual refresh |
| Data | Git/code analysis | Coverity defects + enrichment |
| Populated | On demand, per query | At startup or on explicit reload |
| Fix hints | No | Yes — built-in per checker |
| Status tracking | No | Yes — open/fixed/wontfix |

---

## Built-in Fix Hints (Per Checker)

These patterns are embedded directly in the store — no LLM call required.

### `FORWARD_NULL` / `NULL_RETURNS`
```
Check the return value immediately after the call before using it.

Java:
  User user = repo.findById(id);
  if (user == null) { throw new NotFoundException("User not found: " + id); }
  // or: Optional<User> user = repo.findById(id); user.orElseThrow(...);

C/C++:
  char *buf = malloc(size);
  if (buf == NULL) { perror("malloc"); return -1; }
```

### `RESOURCE_LEAK`
```
Ensure every resource is closed on all exit paths.

Java:
  try (InputStream is = new FileInputStream(path)) {
      // use is
  }  // auto-closed

C:
  FILE *f = fopen(path, "r");
  if (!f) { return -1; }
  // ... use f ...
  fclose(f);   // must be on ALL return paths, including error paths
```

### `DEREFERENCE`
```
Add a null guard before every dereference.

Java:
  if (obj != null) { obj.doSomething(); }
  // or use Objects.requireNonNull(obj, "obj must not be null")

C++:
  if (ptr) { ptr->method(); }
  // or use smart pointers: std::unique_ptr / std::shared_ptr
```

### `UNCHECKED_RETURN_VALUE`
```
Always inspect return codes or errno.
Only cast to (void) if ignoring is truly intentional and documented.

C:  if (write(fd, buf, len) < 0) { perror("write"); }
Java: check boolean return of collection mutators, File.delete(), etc.
```

### `RESOURCE_LEAK` (locks/mutexes)
```
Ensure mutexes are unlocked on all paths including exceptions.

Java:  Use try/finally or java.util.concurrent.locks.Lock with try-finally.
C++:   Use std::lock_guard<std::mutex> or std::unique_lock (RAII).
```

### `DIVIDE_BY_ZERO`
```
Guard the denominator before division.
  if (denominator == 0) { /* handle */ return; }
  result = numerator / denominator;
```

### `UNINIT`
```
Always initialize variables at declaration.
  int count = 0;
  char *buf = NULL;
```

### `INTEGER_OVERFLOW`
```
Use wider types or check bounds before arithmetic.
Java: use long or BigInteger for large values.
C:   cast to a wider type before the operation, or use __builtin_add_overflow().
```

### `TAINTED_SCALAR` / `OS_CMD_INJECTION` / `SQL_INJECTION`
```
Never pass user-controlled data directly to system calls, shell commands, or SQL.
- Validate and sanitize all input at the boundary.
- Use parameterized queries / prepared statements for SQL.
- Use ProcessBuilder (Java) or execv (C) with explicit argument arrays — never shell=True.
```

---

## Planned Architecture (Phase 6)

### New Files to Implement

| File | Purpose |
|---|---|
| `mcp_server/analyzers/coverity_analyzer.py` | Load raw JSON, enrich with git data, compute risk scores, write store |
| `mcp_server/analyzers/coverity_fix_hints.py` | Static dict of fix patterns keyed by `checkerName` |
| `.coverity_store.json` | The persistent enriched data store (add to `.gitignore`) |

### Data Flow

```
Coverity JSON (raw, from cov-format-errors)
        │
        ▼
  coverity_analyzer.py
        ├─ merges git churn  (git_analyzer.py)
        ├─ merges test coverage gaps (code_health.py)
        ├─ attaches fix hints (coverity_fix_hints.py)
        └─ computes composite_risk_score
        │
        ▼
  .coverity_store.json   (persisted to disk)
        │
        ▼
  MCP Tools (server.py)
```

---

## MCP Tools (Planned)

Once Phase 6 is implemented and `COVERITY_REPORT_PATH` is set:

```
get_coverity_findings("src/com/example/service/UserService.java")
  -> All Coverity defects in that file, sorted by composite_risk_score

get_coverity_summary()
  -> Total counts by checker, top-10 highest-risk files

get_high_risk_coverity()
  -> Issues where file is ALSO a git hotspot (churn >30 in 90d)
  -> These are your highest-priority fixes

get_fix_hint("FORWARD_NULL")
  -> Returns the built-in fix pattern for that checker

get_coverity_by_checker("RESOURCE_LEAK")
  -> All RESOURCE_LEAK issues across the codebase, sorted by risk

get_coverity_issue("abc123def456")
  -> Deep-dive on one specific defect by mergeKey
```

---

## Coverity Connect API (Alternative Input)

If your team uses Coverity Connect (web UI), you can pull findings via the REST API instead
of a local file. This is optional — local JSON file is sufficient for now.

When ready to implement: set `COVERITY_CONNECT_URL` and `COVERITY_CONNECT_TOKEN` instead of
`COVERITY_REPORT_PATH`. The analyzer will automatically use the API if these are set.

---

## Refreshing Coverity Data

CoPilotLens reads the JSON file at startup and writes `.coverity_store.json`. To refresh:

1. Re-run your Coverity scan: `cov-build`, `cov-analyze`, `cov-format-errors`
2. Export the new JSON to the same path
3. Restart the MCP server, or call `reload_coverity()` once that tool is implemented

The store hash (`source_hash`) is checked on startup — if the source JSON hasn't changed,
the existing store is reused without re-processing.
