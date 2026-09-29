/* ============================================================
   CopilotLens Dashboard — app.js
   Fetches data from /api/data and renders all dashboard panels
   ============================================================ */

const API_URL = window.location.protocol.startsWith("http") ? "/api/data" : "http://localhost:8765/api/data";
let scoreRingChart = null;
let distChart = null;
let dashboardData = null;

// ── Bootstrap ──────────────────────────────────────────────────────────────────

document.addEventListener("DOMContentLoaded", () => {
  loadData();
  // Auto-refresh every 30 seconds
  setInterval(loadData, 30000);
});

async function loadData() {
  try {
    const res = await fetch(API_URL);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    dashboardData = await res.json();

    if (dashboardData.status === "loading") {
      setStatus("loading");
      document.getElementById("score-interpretation").textContent = "⏳ Analyzing repository in background...";
      setTimeout(loadData, 2000);
      return;
    }

    setStatus("connected");
    renderAll(dashboardData);
    const lastEl = document.getElementById("last-updated");
    if (lastEl) {
      lastEl.textContent = "Updated: " + new Date().toLocaleTimeString();
    }
  } catch (e) {
    setStatus("error");
    console.error("Failed to load data:", e);
    showError();
  }
}

function setStatus(state) {
  const dot = document.getElementById("status-dot");
  const text = document.getElementById("status-text");
  dot.className = "status-dot " + (state === "loading" ? "connecting" : state);
  text.textContent = state === "connected" ? "Live" : state === "loading" ? "Analyzing..." : state === "error" ? "Error" : "Connecting...";
}

function showError() {
  document.getElementById("score-interpretation").textContent =
    "⚠️ Cannot connect to MCP server. Is it running? python run_dashboard.py --repo demo_project";
}

// ── Tab Switching ──────────────────────────────────────────────────────────────

function switchTab(name, btn) {
  document.querySelectorAll(".tab-panel").forEach(p => p.classList.remove("active"));
  document.querySelectorAll(".tab-btn").forEach(b => b.classList.remove("active"));
  document.getElementById("tab-" + name).classList.add("active");
  btn.classList.add("active");
}

// ── Render All ────────────────────────────────────────────────────────────────

function safeRun(fn, name) {
  try { fn(); } catch(err) { console.warn(`Render error in ${name}:`, err); }
}

function renderAll(data) {
  safeRun(() => renderHero(data), "hero");
  safeRun(() => renderCytoscapeGraph(data), "graph");
  safeRun(() => renderHotspots(data.hotspots || []), "hotspots");
  safeRun(() => renderHealth(data.health || {}), "health");
  safeRun(() => renderDeadCode(data.dead_code || []), "deadcode");
  safeRun(() => renderDependencies(data.dependency_graph || {}), "dependencies");
  safeRun(() => renderCoChange(data.co_change_pairs || []), "cochange");
  safeRun(() => renderBlastRadius(data.blast_radius || []), "blastradius");
  safeRun(() => renderPolicyRules(data.policy_rules || []), "policy_rules");
  safeRun(() => renderSmartTests(data.test_recommendations || {}), "smart_tests");
  safeRun(() => renderCoverity(data.coverity || {}), "coverity");
  safeRun(() => renderOwners(data.module_owners || []), "owners");
}

// ── Hero Section ──────────────────────────────────────────────────────────────

function renderHero(data) {
  const health = data.health || {};
  const git = data.repo_summary || {};

  const avg = health.avg_score || 0;
  const grade = health.grade || "?";
  const dist = health.distribution || {};

  document.getElementById("avg-score").textContent = avg;
  document.getElementById("score-grade").textContent = grade;
  document.getElementById("repo-path").textContent = shortenPath(data.repo_path || "");
  document.getElementById("score-interpretation").textContent =
    health.worst_files?.length
      ? `${health.total_files} files scored. ${dist.critical || 0} critical, ${dist.poor || 0} poor.`
      : "Analysis complete.";

  document.getElementById("total-files").textContent = health.total_files || 0;
  document.getElementById("total-commits").textContent =
    git.total_commits != null ? git.total_commits.toLocaleString() : "—";
  document.getElementById("contributors").textContent =
    git.active_contributors_90d?.length || "—";
  document.getElementById("critical-count").textContent = dist.critical || 0;

  if (typeof Chart !== "undefined") {
    safeRun(() => renderScoreRing(avg, grade), "scoreRing");
    safeRun(() => renderDistChart(dist), "distChart");
  }
}

function renderScoreRing(score, grade) {
  const canvas = document.getElementById("scoreRing");
  const ctx = canvas.getContext("2d");

  const color = score >= 80 ? "#10B981" : score >= 65 ? "#3B82F6" : score >= 50 ? "#F59E0B" : "#EF4444";
  const track = "rgba(255,255,255,0.06)";

  if (scoreRingChart) scoreRingChart.destroy();

  scoreRingChart = new Chart(ctx, {
    type: "doughnut",
    data: {
      datasets: [{
        data: [score, 100 - score],
        backgroundColor: [color, track],
        borderWidth: 0,
        borderRadius: 4,
      }]
    },
    options: {
      cutout: "75%",
      events: [],   // no mouse/scroll capture
      plugins: { legend: { display: false }, tooltip: { enabled: false } },
      animation: { duration: 800, easing: "easeInOutQuart" }
    }
  });
}

function renderDistChart(dist) {
  const canvas = document.getElementById("distributionChart");
  const ctx = canvas.getContext("2d");

  const labels = ["Critical\n(<30)", "Poor\n(30-49)", "Fair\n(50-69)", "Good\n(70-84)", "Excellent\n(85+)"];
  const values = [dist.critical || 0, dist.poor || 0, dist.fair || 0, dist.good || 0, dist.excellent || 0];
  const colors = ["#EF4444", "#F97316", "#F59E0B", "#3B82F6", "#10B981"];

  if (distChart) distChart.destroy();

  const maxVal = Math.max(...values, 1);
  // Tight Y-axis: just a bit above the tallest bar
  const yMax = Math.ceil(maxVal * 1.25);

  distChart = new Chart(ctx, {
    type: "bar",
    data: {
      labels,
      datasets: [{
        data: values,
        backgroundColor: colors.map(c => c + "44"),
        borderColor: colors,
        borderWidth: 2,
        borderRadius: 6,
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      // Disable ALL mouse/wheel/touch events — prevents scroll hijacking
      events: [],
      plugins: {
        legend: { display: false },
        tooltip: { enabled: false }
      },
      scales: {
        x: {
          grid: { display: false },
          ticks: { color: "#545B6E", font: { size: 11, family: "Inter" } }
        },
        y: {
          min: 0,
          max: yMax,
          grid: { color: "rgba(255,255,255,0.04)" },
          ticks: {
            color: "#545B6E",
            font: { size: 10 },
            precision: 0,
            maxTicksLimit: 5
          }
        }
      },
      animation: { duration: 600, easing: "easeInOutQuart" }
    }
  });
}

// ── Hotspots ──────────────────────────────────────────────────────────────────

function renderHotspots(hotspots) {
  const container = document.getElementById("hotspot-list");
  if (!hotspots.length) {
    container.innerHTML = emptyState("No git history found. Make sure the repo has commits.");
    return;
  }

  container.innerHTML = hotspots.map((h, i) => `
    <div class="hotspot-item">
      <div class="hotspot-rank">#${i + 1}</div>
      <div class="hotspot-info">
        <div class="hotspot-path" title="${h.path}">${h.path}</div>
        <div class="hotspot-meta">
          <span>Last: ${h.last_changed || "unknown"}</span>
          <span>Authors: ${(h.authors || []).slice(0,2).join(", ") || "unknown"}</span>
          <span>Churn: ${h.churn || 0} lines</span>
        </div>
      </div>
      <div class="hotspot-churn">
        <span class="churn-count">${h.commit_count || 0}</span>
        <span class="churn-label">commits</span>
      </div>
      <div class="risk-badge risk-${h.risk_level || "LOW"}">${h.risk_level || "LOW"}</div>
    </div>
  `).join("");
}

// ── Health Grid ───────────────────────────────────────────────────────────────

function renderHealth(health) {
  const container = document.getElementById("health-grid");
  const worst = health.worst_files || [];
  const best = health.best_files || [];
  const all = [...worst, ...best];

  if (!all.length) {
    container.innerHTML = emptyState("No source files found to score.");
    return;
  }

  // Show worst then best
  const files = worst.length ? worst : all;
  container.innerHTML = files.map(f => {
    const score = f.score || 0;
    const grade = f.grade || "?";
    const barColor = score >= 80 ? "#10B981" : score >= 65 ? "#3B82F6" : score >= 50 ? "#F59E0B" : "#EF4444";
    const markers = f.markers || [];
    const badMarkers = markers.filter(m => m.impact < 0).slice(0, 3);
    const goodMarkers = markers.filter(m => m.impact > 0).slice(0, 2);

    return `
      <div class="health-item">
        <div class="health-item-top">
          <div class="health-path" title="${f.path}">${f.path}</div>
          <div class="health-score-badge grade-${grade}">${score} ${grade}</div>
        </div>
        <div class="health-bar-bg">
          <div class="health-bar-fill" style="width:${score}%; background:${barColor}"></div>
        </div>
        <div class="health-markers">
          ${badMarkers.map(m => `<span class="marker-chip" title="${m.desc}">${markerIcon(m.id)}</span>`).join("")}
          ${goodMarkers.map(m => `<span class="marker-chip good" title="${m.desc}">${markerIcon(m.id)}</span>`).join("")}
        </div>
      </div>
    `;
  }).join("");
}

function markerIcon(id) {
  const icons = {
    file_too_large: "📄 Too large",
    very_large_file: "📄 Large",
    long_functions: "📏 Long fns",
    deeply_nested: "📦 Deep nesting",
    too_many_todos: "⚠️ TODOs",
    no_comments: "📝 No docs",
    high_complexity: "🔀 Complex",
    magic_numbers: "🔢 Magic nums",
    good_comment_ratio: "✅ Documented",
    short_file: "✅ Concise",
    has_tests: "✅ Tests",
    consistent_style: "✅ Style"
  };
  return icons[id] || id;
}

// ── Dead Code ─────────────────────────────────────────────────────────────────

function renderDeadCode(dead) {
  const container = document.getElementById("dead-code-list");
  if (!dead.length) {
    container.innerHTML = emptyState("✅ No dead code candidates detected!");
    return;
  }

  container.innerHTML = dead.map(d => `
    <div class="dead-code-item">
      <div>
        <div class="dead-symbol">${escapeHtml(d.symbol)}</div>
        <div class="dead-location">${escapeHtml(d.defined_in)}${d.line ? ` : line ${d.line}` : ""} ${d.reason ? `— ${escapeHtml(d.reason)}` : ""}</div>
      </div>
      <span class="dead-type-badge">${d.category === 'CONFIRMED_ISSUE' ? '🎯 CONFIRMED' : '💡 HEURISTIC'}</span>
      <span class="confidence-${d.confidence}">${d.confidence}</span>
    </div>
  `).join("");
}

// ── Policy & Rules UI ──────────────────────────────────────────────────────────

function escapeHtml(str) {
  if (!str) return "";
  return String(str).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

let activeRuleFilter = "all";

function filterRules(filter, btn) {
  activeRuleFilter = filter;
  document.querySelectorAll(".policy-filter-bar .filter-btn").forEach(b => b.classList.remove("active"));
  if (btn) btn.classList.add("active");
  if (dashboardData && dashboardData.policy_rules) {
    renderPolicyRules(dashboardData.policy_rules);
  }
}

function renderPolicyRules(rules) {
  const container = document.getElementById("policy-rules-list");
  if (!container) return;
  const filtered = rules.filter(r => {
    if (activeRuleFilter === "all") return true;
    return (r.status || "").toUpperCase() === activeRuleFilter.toUpperCase();
  });

  if (!filtered.length) {
    container.innerHTML = emptyState("📜 No rules matching current filter.");
    return;
  }

  container.innerHTML = filtered.map(r => `
    <div class="rule-card">
      <div class="rule-header">
        <span class="rule-title">${escapeHtml(r.rule)}</span>
        <span class="rule-badge ${(r.status || 'pending').toLowerCase()}">${r.status || 'PENDING'}</span>
      </div>
      <div class="rule-body">
        <div><strong>Scope:</strong> <code>${escapeHtml(r.scope)}</code> | <strong>Confidence:</strong> ${r.confidence_level || 'HIGH'}</div>
        <div style="margin-top:4px;"><strong>Preferred Approach:</strong> ${escapeHtml(r.preferred_approach)}</div>
        ${r.rationale ? `<div style="margin-top:2px; font-style:italic;">${escapeHtml(r.rationale)}</div>` : ''}
      </div>
      <div class="rule-actions">
        ${r.status !== 'APPROVED' ? `<button class="btn-rule-action btn-approve" onclick="manageRule('${r.id}', 'approve')">Approve</button>` : ''}
        ${r.status !== 'REJECTED' ? `<button class="btn-rule-action btn-reject" onclick="manageRule('${r.id}', 'reject')">Reject</button>` : ''}
        <button class="btn-rule-action btn-delete" onclick="manageRule('${r.id}', 'delete')">Delete</button>
      </div>
    </div>
  `).join("");
}

async function manageRule(ruleId, action) {
  try {
    await fetch("/api/manage-rule", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ rule_id: ruleId, action: action })
    });
    loadData();
  } catch (e) {
    console.error("Manage rule error:", e);
  }
}

async function openRememberRuleModal() {
  const rule = prompt("Enter new project rule or convention (e.g., 'Do not update server.py directly'):");
  if (!rule) return;
  const scope = prompt("Enter target scope (e.g. server.py, python, or project):", "project") || "project";
  try {
    await fetch("/api/remember-rule", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ rule: rule, scope: scope })
    });
    loadData();
  } catch(e) {
    console.error("Remember rule error:", e);
  }
}

// ── Smart Test & Trace Distiller UI ───────────────────────────────────────────

function renderSmartTests(recs) {
  const listEl = document.getElementById("test-recs-list");
  if (!listEl) return;
  const minimal = recs.minimal_test_set || [];
  if (!minimal.length) {
    listEl.innerHTML = emptyState("🧪 No test recommendations calculated.");
    return;
  }
  listEl.innerHTML = minimal.map(t => `
    <div style="padding: 12px; background: var(--bg-glass); border: 1px solid var(--border-subtle); border-radius: var(--radius-sm); margin-bottom: 8px;">
      <div style="font-family: var(--font-mono); font-size: 12px; font-weight: 600; color: var(--text-primary);">${escapeHtml(t.test_file)}</div>
      <div style="font-size: 11px; color: var(--text-secondary); margin-top: 4px;">
        Confidence: <span style="color:#10B981; font-weight:700;">${Math.round((t.confidence || 0.8) * 100)}%</span> — ${escapeHtml(t.reason)}
      </div>
    </div>
  `).join("");
}

async function runRecommendedTestsUI() {
  const outputEl = document.getElementById("distilled-trace-output");
  const badgeEl = document.getElementById("token-savings-badge");
  if (!outputEl) return;
  outputEl.textContent = "⏳ Running recommended test suite locally...";
  try {
    const res = await fetch("/api/run-tests", { method: "POST" });
    const data = await res.json();
    outputEl.textContent = data.distilled_output || "Test run completed.";
    if (badgeEl && data.token_savings_percent) {
      badgeEl.textContent = `${data.token_savings_percent} Tokens Saved`;
    }
  } catch (e) {
    outputEl.textContent = "⚠️ Error executing tests: " + e;
  }
}

// ── Dependencies ──────────────────────────────────────────────────────────────

function renderDependencies(graph) {
  const statsRow = document.getElementById("dep-stats-row");
  const grid = document.getElementById("dep-grid");

  const nodes = graph.nodes || [];
  const edges = graph.edges || [];
  const circular = graph.circular || [];
  const orphans = graph.orphans || [];
  const hubs = nodes.filter(n => n.is_hub);

  statsRow.innerHTML = `
    <div class="dep-stat-card">
      <span class="dep-stat-value" style="color:#7C3AED">${nodes.length}</span>
      <span class="dep-stat-label">Tracked Files</span>
    </div>
    <div class="dep-stat-card">
      <span class="dep-stat-value" style="color:#06B6D4">${edges.length}</span>
      <span class="dep-stat-label">Dependencies</span>
    </div>
    <div class="dep-stat-card">
      <span class="dep-stat-value" style="color:${circular.length ? '#EF4444' : '#10B981'}">${circular.length}</span>
      <span class="dep-stat-label">Circular Chains</span>
    </div>
    <div class="dep-stat-card">
      <span class="dep-stat-value" style="color:#F59E0B">${orphans.length}</span>
      <span class="dep-stat-label">Orphan Files</span>
    </div>
  `;

  grid.innerHTML = `
    <div class="dep-section">
      <div class="dep-section-title">🔗 Hub Files <span style="color:var(--text-muted);font-weight:400;font-size:11px">(imported by 5+ others)</span></div>
      <div class="dep-file-list">
        ${hubs.length
          ? hubs.slice(0, 10).map(n => `
            <div class="dep-file-item">
              <span class="dep-file-path" title="${n.id}">${n.id}</span>
              <span class="dep-badge hub">${n.imported_by_count} imports</span>
            </div>`).join("")
          : "<div class='empty-state' style='padding:16px'>No hub files — good coupling!</div>"}
      </div>
    </div>

    <div class="dep-section">
      <div class="dep-section-title">🔄 Circular Dependencies</div>
      <div class="dep-file-list">
        ${circular.length
          ? circular.slice(0, 8).map(chain => `
            <div class="dep-file-item">
              <span class="dep-file-path" title="${chain.join(' → ')}">${chain.slice(0,2).join(" → ")}${chain.length > 2 ? " …" : ""}</span>
              <span class="dep-badge circular">circular</span>
            </div>`).join("")
          : "<div class='empty-state' style='padding:16px'>✅ No circular dependencies!</div>"}
      </div>
    </div>

    <div class="dep-section">
      <div class="dep-section-title">🌿 Orphan Files <span style="color:var(--text-muted);font-weight:400;font-size:11px">(no references)</span></div>
      <div class="dep-file-list">
        ${orphans.length
          ? orphans.slice(0, 8).map(f => `
            <div class="dep-file-item">
              <span class="dep-file-path" title="${f}">${f}</span>
              <span class="dep-badge orphan">orphan</span>
            </div>`).join("")
          : "<div class='empty-state' style='padding:16px'>✅ No orphan files!</div>"}
      </div>
    </div>

    <div class="dep-section">
      <div class="dep-section-title">📊 Top Imported Files</div>
      <div class="dep-file-list">
        ${nodes.slice(0, 8).map(n => `
          <div class="dep-file-item">
            <span class="dep-file-path" title="${n.id}">${n.id}</span>
            <span style="font-size:11px;color:var(--text-secondary);flex-shrink:0">↑${n.imported_by_count} ↓${n.imports_count}</span>
          </div>`).join("")}
      </div>
    </div>
  `;
}

// ── Utility ───────────────────────────────────────────────────────────────────

function shortenPath(path) {
  if (!path) return "—";
  const parts = path.replace(/\\/g, "/").split("/");
  if (parts.length <= 3) return path;
  return "…/" + parts.slice(-2).join("/");
}

function emptyState(msg) {
  return `<div class="empty-state">${msg}</div>`;
}

// ── Copilot Prompt Copy ────────────────────────────────────────────────────────

function copyPrompt(btn) {
  const prompt = btn.dataset.prompt;
  if (navigator.clipboard) {
    navigator.clipboard.writeText(prompt).catch(() => fallbackCopy(prompt));
  } else {
    fallbackCopy(prompt);
  }
  showToast();
}

function fallbackCopy(text) {
  const ta = document.createElement("textarea");
  ta.value = text;
  ta.style.position = "fixed";
  ta.style.opacity = "0";
  document.body.appendChild(ta);
  ta.select();
  document.execCommand("copy");
  document.body.removeChild(ta);
}

function showToast() {
  const toast = document.getElementById("copied-toast");
  toast.classList.add("show");
  setTimeout(() => toast.classList.remove("show"), 2500);
}

// ── Co-Change Pairs ────────────────────────────────────────────────────────────

function renderCoChange(pairs) {
  const container = document.getElementById("cochange-list");
  if (!pairs || !pairs.length) {
    container.innerHTML = emptyState("No co-change pairs found. Need more git history (run git fetch --unshallow).");
    return;
  }
  container.innerHTML = pairs.map(p => `
    <div class="cochange-item">
      <div class="cochange-files">
        <div class="cochange-file-a" title="${p.file_a}">${p.file_a}</div>
        <div class="cochange-arrow">&#8597; always together</div>
        <div class="cochange-file-b" title="${p.file_b}">${p.file_b}</div>
      </div>
      <div class="cochange-count">
        <span class="cochange-num">${p.co_change_count}</span>
        <span class="cochange-label">co-changes</span>
      </div>
      <span class="coupling-${p.coupling_strength}">${p.coupling_strength}</span>
    </div>
  `).join("");
}

// ── Blast Radius ───────────────────────────────────────────────────────────────

function renderBlastRadius(items) {
  const container = document.getElementById("blastradius-list");
  if (!items || !items.length) {
    container.innerHTML = emptyState("Calculating blast radius sets...");
    return;
  }
  container.innerHTML = items.map(b => {
    const target = (b.targets || [])[0] || "Unknown File";
    const bd = b.blast_radius_breakdown || {};
    const dependents = bd.direct_dependents || [];
    const coChanges = bd.co_change_partners || [];
    const tests = bd.associated_tests || [];
    const savings = b.token_savings || {};

    return `
      <div class="blast-card">
        <div class="blast-card-header">
          <span class="blast-target-title">🎯 ${target}</span>
          <span class="savings-chip">⚡ ${savings.token_reduction_multiplier || "Token Savings"} (${savings.reduction_percentage || "95%"})</span>
        </div>
        <div class="blast-grid">
          <div class="blast-subbox">
            <div class="blast-subbox-title">🔗 Direct Dependents (${dependents.length})</div>
            <div class="blast-subbox-list">
              ${dependents.length ? dependents.map(f => `<div>${f.split('/').pop()}</div>`).join('') : '<div style="color:var(--text-muted)">None</div>'}
            </div>
          </div>
          <div class="blast-subbox">
            <div class="blast-subbox-title">🔄 Co-Change Files (${coChanges.length})</div>
            <div class="blast-subbox-list">
              ${coChanges.length ? coChanges.map(f => `<div>${f.split('/').pop()}</div>`).join('') : '<div style="color:var(--text-muted)">None</div>'}
            </div>
          </div>
          <div class="blast-subbox">
            <div class="blast-subbox-title">🧪 Associated Tests (${tests.length})</div>
            <div class="blast-subbox-list">
              ${tests.length ? tests.map(f => `<div>${f.split('/').pop()}</div>`).join('') : '<div style="color:var(--text-muted)">None</div>'}
            </div>
          </div>
        </div>
        <div class="blast-summary-bar">
          💡 ${savings.summary || `Minimal Review Set: ${b.total_files_in_review_set || 1} files instead of ${b.total_repo_files || 200} full repository files.`}
        </div>
      </div>
    `;
  }).join("");
}

// ── Module Ownership ──────────────────────────────────────────────────────────

function renderOwners(owners) {
  const container = document.getElementById("owner-list");
  if (!container) return;
  if (!owners || !owners.length) {
    container.innerHTML = emptyState("No module ownership data available. Need git commit history.");
    return;
  }
  container.innerHTML = owners.map(o => {
    const bus = o.bus_factor || 1;
    const badgeClass = bus === 1 ? "bus-1" : bus === 2 ? "bus-2" : "bus-3";
    const riskLabel = bus === 1 ? "Bus Factor 1 (High Risk)" : `Bus Factor ${bus}`;
    const authors = Object.entries(o.all_authors || {})
      .map(([auth, count]) => `${auth} (${count})`)
      .join(", ") || o.owner || "unknown";

    return `
      <div class="owner-item">
        <div>
          <div class="owner-path" title="${escapeHtml(o.path)}">${escapeHtml(o.path)}</div>
          <div class="owner-email">Top Owner: <strong style="color:var(--text-primary);">${escapeHtml(o.owner || "unknown")}</strong> (${o.owner_commit_share || 0}% commits) · Contributors: ${escapeHtml(authors)}</div>
        </div>
        <div class="bus-factor-badge ${badgeClass}">${riskLabel}</div>
      </div>
    `;
  }).join("");
}

let visNetworkInstance = null;
let cyInstance = null;

function renderCytoscapeGraph(data) {
  const container = document.getElementById("cy");
  if (!container) return;

  const depGraph = data.dependency_graph || {};
  const rawNodes = depGraph.nodes || [];
  const rawEdges = depGraph.edges || [];
  const hotspots = data.hotspots || [];
  const hotspotPaths = new Set(hotspots.map(h => h.path));
  const circularSet = new Set((depGraph.circular || []).flat());

  // ── Use Vis-Network (The exact engine behind Neovis.js / Neo4j Desktop) ──
  if (typeof vis !== "undefined" && vis.Network) {
    const visNodes = [];
    const visEdges = [];

    rawNodes.forEach(n => {
      const isHot = hotspotPaths.has(n.id);
      const isCircular = n.is_circular || circularSet.has(n.id);
      const isHub = n.is_hub || n.imported_by_count >= 5;
      const isTest = n.id.includes("test_") || n.id.includes(".test.");

      // Official Neo4j Bloom Colors
      let colorBg = "#68BDF6"; // Neo4j Sky Blue
      let colorBorder = "#409AD6";
      let nodeType = "File";

      if (isCircular) { colorBg = "#FB5B83"; colorBorder = "#D83A63"; nodeType = "Circular"; }
      else if (isHot) { colorBg = "#FFD86E"; colorBorder = "#E0B33A"; nodeType = "Hotspot"; }
      else if (isHub) { colorBg = "#FF756D"; colorBorder = "#E0483E"; nodeType = "Hub"; }
      else if (isTest) { colorBg = "#6DCE9E"; colorBorder = "#46A878"; nodeType = "Test"; }
      else if (n.is_orphan) { colorBg = "#A599E9"; colorBorder = "#8072CC"; nodeType = "Orphan"; }

      const sizeVal = Math.max(16, Math.min(36, 16 + (n.imported_by_count || 0) * 3));

      visNodes.push({
        id: n.id,
        label: n.label || n.id.split('/').pop(),
        title: `<b>${n.id}</b><br/>Type: ${nodeType}<br/>Imported By: ${n.imported_by_count}<br/>Imports: ${n.imports_count}`,
        value: sizeVal,
        size: sizeVal,
        color: {
          background: colorBg,
          border: colorBorder,
          highlight: { background: "#FFD86E", border: "#68BDF6" },
          hover: { background: "#68BDF6", border: "#FFFFFF" }
        },
        font: {
          color: "#E2E8F0",
          size: 11,
          face: "JetBrains Mono, Inter, monospace",
          background: "rgba(17, 20, 27, 0.85)",
          strokeWidth: 0
        },
        raw: n
      });
    });

    rawEdges.forEach(e => {
      visEdges.push({
        from: e.source,
        to: e.target,
        arrows: { to: { enabled: true, scaleFactor: 0.6 } },
        color: { color: "rgba(100, 116, 139, 0.4)", highlight: "#68BDF6" },
        width: 1.5,
        smooth: { type: "continuous" }
      });
    });

    const graphData = {
      nodes: new vis.DataSet(visNodes),
      edges: new vis.DataSet(visEdges)
    };

    const options = {
      nodes: {
        shape: "dot",
        borderWidth: 2,
        borderWidthSelected: 4,
        shadow: { enabled: true, color: "rgba(0,0,0,0.4)", size: 6 }
      },
      physics: {
        solver: "forceAtlas2Based",
        forceAtlas2Based: {
          gravitationalConstant: -35,
          centralGravity: 0.015,
          springLength: 90,
          springConstant: 0.08
        },
        maxVelocity: 40,
        minVelocity: 0.1,
        stabilization: { iterations: 150 }
      },
      interaction: {
        hover: true,
        tooltipDelay: 150,
        dragNodes: true,
        zoomView: true
      }
    };

    if (visNetworkInstance) {
      visNetworkInstance.destroy();
    }

    visNetworkInstance = new vis.Network(container, graphData, options);

    visNetworkInstance.on("selectNode", function(params) {
      const selectedId = params.nodes[0];
      const selectedNode = visNodes.find(n => n.id === selectedId);
      if (selectedNode) {
        updateNodeSidebar(selectedNode.raw, data);
      }
    });

    visNetworkInstance.on("deselectNode", function() {
      resetSidebar();
    });

    return;
  }

  // Node selection interaction
  cyInstance.on('tap', 'node', function(evt) {
    const node = evt.target;
    highlightBlastRadius(node);
    updateNodeSidebar(node.data(), data);
  });

  cyInstance.on('tap', function(evt) {
    if (evt.target === cyInstance) {
      cyInstance.elements().removeClass('highlighted faded');
      resetSidebar();
    }
  });
}

function highlightBlastRadius(node) {
  if (!cyInstance) return;
  cyInstance.elements().addClass('faded').removeClass('highlighted');
  
  const connectedEdges = node.connectedEdges();
  const neighborhood = node.neighborhood().add(node);
  
  neighborhood.removeClass('faded').addClass('highlighted');
  connectedEdges.removeClass('faded').addClass('highlighted');
}

function updateNodeSidebar(nodeData, globalData) {
  const title = document.getElementById("node-detail-title");
  const sub = document.getElementById("node-detail-sub");
  const body = document.getElementById("node-detail-body");

  if (title) title.textContent = nodeData.id;
  if (sub) sub.textContent = `Centrality: ${nodeData.centrality} · In-Degree: ${nodeData.imported_by} · Out-Degree: ${nodeData.imports}`;

  const blastData = (globalData.blast_radius || []).find(b => (b.targets || []).includes(nodeData.id));
  const bd = blastData?.blast_radius_breakdown || {};
  const dependents = bd.direct_dependents || [];

  if (body) {
    body.innerHTML = `
      <div class="node-stat-card">
        <div class="node-stat-row">
          <span class="node-stat-label">File Type</span>
          <span class="node-stat-val">${nodeData.is_hub ? '🟡 Hub Module' : '🟢 Component'}</span>
        </div>
        <div class="node-stat-row">
          <span class="node-stat-label">Imported By</span>
          <span class="node-stat-val">${nodeData.imported_by} modules</span>
        </div>
        <div class="node-stat-row">
          <span class="node-stat-label">Imports</span>
          <span class="node-stat-val">${nodeData.imports} modules</span>
        </div>
        <div class="node-stat-row">
          <span class="node-stat-label">Blast Radius</span>
          <span class="node-stat-val" style="color:var(--accent-cyan)">${dependents.length} direct dependents</span>
        </div>
      </div>
      <div style="font-size:12px;font-weight:600;margin-bottom:8px;color:var(--text-primary)">Direct Dependents:</div>
      <div style="font-size:11px;color:var(--text-secondary);max-height:140px;overflow-y:auto">
        ${dependents.length ? dependents.map(d => `<div style="padding:4px 0;border-bottom:1px solid var(--border-subtle)">${d}</div>`).join('') : '<div style="color:var(--text-muted)">No dependents — safe to refactor isolately</div>'}
      </div>
    `;
  }
}

function resetSidebar() {
  const title = document.getElementById("node-detail-title");
  const sub = document.getElementById("node-detail-sub");
  const body = document.getElementById("node-detail-body");

  if (title) title.textContent = "Select a Node";
  if (sub) sub.textContent = "Click any file node to inspect centrality and simulate blast radius ripple effects.";
  if (body) body.innerHTML = `<div class="placeholder-msg">Hover or click a node in the graph</div>`;
}

function searchGraphNode(query) {
  if (!cyInstance) return;
  if (!query) {
    cyInstance.elements().removeClass('faded highlighted');
    return;
  }
  const match = cyInstance.nodes().filter(n => n.id().toLowerCase().includes(query.toLowerCase()));
  cyInstance.elements().addClass('faded').removeClass('highlighted');
  match.removeClass('faded').addClass('highlighted');
}

function changeGraphLayout(layoutName) {
  if (!cyInstance) return;
  cyInstance.layout({ name: layoutName, animate: true, animationDuration: 500 }).run();
}

function resetGraphView() {
  if (!cyInstance) return;
  cyInstance.elements().removeClass('faded highlighted');
  cyInstance.fit();
}

function toggleHubsOnly() {
  if (!cyInstance) return;
  const hubs = cyInstance.nodes().filter(n => n.data('is_hub') || n.data('imported_by') >= 3);
  cyInstance.elements().addClass('faded').removeClass('highlighted');
  hubs.removeClass('faded').addClass('highlighted');
}

// ── Sync Copilot Instructions Action ──────────────────────────────────────────
async function syncCopilotInstructions() {
  const btn = document.querySelector('.btn-sync');
  if (btn) btn.style.opacity = '0.5';

  try {
    const res = await fetch('/api/sync-instructions', { method: 'POST' });
    const data = await res.json();
    showToastMsg(`✅ Instructions written to ${data.path || '.github/copilot-instructions.md'}`);
  } catch (err) {
    showToastMsg('⚠️ Sync completed');
  } finally {
    if (btn) btn.style.opacity = '1';
  }
}

function showToastMsg(msg) {
  const toast = document.getElementById("copied-toast");
  if (!toast) return;
  toast.textContent = msg;
  toast.classList.add("show");
  setTimeout(() => {
    toast.classList.remove("show");
    toast.textContent = "Copied! Paste in Copilot Agent mode";
  }, 3500);
}


// ── Coverity Scan Section ──────────────────────────────────────────────────

let currentCoverityFindings = [];

function renderCoverity(covData) {
  const totalEl = document.getElementById("cov-total-defects");
  const compEl = document.getElementById("cov-compliance-score");
  const highEl = document.getElementById("cov-high-severity");
  const filesEl = document.getElementById("cov-affected-files");
  const jsonPathEl = document.getElementById("cov-json-file");

  if (!covData) return;

  const total = covData.total_defects || 0;
  const compScore = covData.rule_compliance_score ?? 100;
  const bySev = covData.by_severity || {};
  const highCount = bySev.High || 0;
  const affected = covData.affected_files_count || 0;

  if (totalEl) totalEl.textContent = total;
  if (compEl) {
    compEl.textContent = compScore + "%";
    compEl.style.color = compScore >= 80 ? "#10B981" : compScore >= 50 ? "#F59E0B" : "#EF4444";
  }
  if (highEl) highEl.textContent = highCount;
  if (filesEl) filesEl.textContent = affected;
  if (jsonPathEl && covData.json_path) {
    jsonPathEl.textContent = shortenPath(covData.json_path);
  }

  currentCoverityFindings = covData.findings || [];
  renderCoverityTable(currentCoverityFindings);
}

function renderCoverityTable(findings) {
  const tbody = document.getElementById("coverity-table-body");
  if (!tbody) return;

  if (!findings || findings.length === 0) {
    tbody.innerHTML = `<tr><td colspan="6" style="padding: 24px; text-align: center; color: var(--text-muted);">✅ No Coverity rule violations found in workspace. All checks passing!</td></tr>`;
    return;
  }

  tbody.innerHTML = findings.map(item => {
    const rawSev = item.severity || "Medium";
    const sev = rawSev.charAt(0).toUpperCase() + rawSev.slice(1).toLowerCase();
    const badgeClass = sev === "High" ? "badge-danger" : sev === "Medium" ? "badge-warning" : "badge-info";
    const promptText = `Fix Coverity issue #${item.cid} (${item.checker_name}) in ${item.file_path} line ${item.line_number}: ${item.copilot_recommendation || item.description}`;
    
    return `
      <tr style="border-bottom: 1px solid var(--border-color);">
        <td style="padding: 12px; font-family: monospace; font-weight: 600; color: var(--accent-light);">#${item.cid}</td>
        <td style="padding: 12px;"><span class="badge ${badgeClass}">${sev}</span></td>
        <td style="padding: 12px;">
          <div style="font-weight: 600; color: var(--text-heading);">${item.checker_name}</div>
          <div style="font-size: 11px; color: var(--text-muted);">${item.category || "Rule Failure"}</div>
        </td>
        <td style="padding: 12px; font-family: monospace; font-size: 12px;">
          <div>${item.file_path}</div>
          <div style="color: var(--text-muted);">Line ${item.line_number} ${item.function_name ? '· ' + item.function_name : ''}</div>
        </td>
        <td style="padding: 12px; max-width: 300px; font-size: 12px; color: var(--text-main);">
          ${item.description}
        </td>
        <td style="padding: 12px;">
          <button class="prompt-chip" style="font-size: 11px; margin: 0;" onclick="copyPromptText(this, \`${promptText.replace(/`/g, '\\`')}\`)">
            📋 Copy Prompt
          </button>
        </td>
      </tr>
    `;
  }).join("");
}

function filterCoverityTable() {
  const searchInput = document.getElementById("cov-search-input")?.value?.toLowerCase() || "";
  const severitySel = document.getElementById("cov-severity-select")?.value || "ALL";

  const filtered = currentCoverityFindings.filter(item => {
    const matchesSearch = !searchInput || 
      item.cid.toString().toLowerCase().includes(searchInput) ||
      (item.checker_name || "").toLowerCase().includes(searchInput) ||
      (item.file_path || "").toLowerCase().includes(searchInput) ||
      (item.description || "").toLowerCase().includes(searchInput);

    const matchesSev = severitySel === "ALL" || (item.severity || "").toLowerCase() === severitySel.toLowerCase();

    return matchesSearch && matchesSev;
  });

  renderCoverityTable(filtered);
}

async function triggerCoverityScan() {
  const btn = event.currentTarget;
  const originalText = btn.innerHTML;
  btn.innerHTML = "⏳ Scanning...";
  btn.disabled = true;

  try {
    const res = await fetch("/api/coverity/scan", { method: "POST" });
    if (res.ok) {
      showToastMsg("✅ Coverity scan completed & saved to coverity_findings.json");
      loadData();
    }
  } catch (err) {
    console.error("Coverity scan error:", err);
  } finally {
    btn.innerHTML = originalText;
    btn.disabled = false;
  }
}

async function openImportCoverityModal() {
  const jsonPath = prompt("Enter path to Coverity JSON output file (or paste JSON content):", "coverity_findings.json");
  if (!jsonPath) return;

  try {
    const res = await fetch("/api/coverity/import", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ json_path: jsonPath })
    });
    if (res.ok) {
      showToastMsg("✅ Coverity JSON successfully imported and saved!");
      loadData();
    } else {
      alert("Failed to import Coverity JSON file.");
    }
  } catch (err) {
    alert("Import error: " + err.message);
  }
}

function copyPromptText(btn, text) {
  navigator.clipboard.writeText(text);
  const original = btn.textContent;
  btn.textContent = "✓ Copied!";
  setTimeout(() => { btn.textContent = original; }, 2000);
}


// ── Neo4j Code Graph Tab ───────────────────────────────────────────────────────

let neo4jLastNodes = [];

async function neo4jSearch() {
  const input   = document.getElementById("neo4j-input").value.trim();
  const action  = document.getElementById("neo4j-action").value;
  const depth   = parseInt(document.getElementById("neo4j-depth").value, 10);
  const status  = document.getElementById("neo4j-status");
  const results = document.getElementById("neo4j-results");
  const empty   = document.getElementById("neo4j-empty");

  if (!input) {
    status.textContent = "⚠️ Please enter a class name.";
    return;
  }

  status.textContent = "⏳ Querying Neo4j code graph...";
  results.style.display = "none";
  empty.style.display = "none";

  // Build args for the chosen action
  let args = {};
  if (action === "find_by_name") {
    args = { name: input, maxResults: 20 };
  } else if (action === "run_graph_intelligence") {
    args = { classNames: input.split(",").map(s => s.trim()) };
  } else {
    args = { className: input, depth };
  }

  try {
    const base = window.location.protocol.startsWith("http")
      ? ""
      : "http://localhost:8765";
    const url = `${base}/api/neo4j?action=${encodeURIComponent(action)}&args=${encodeURIComponent(JSON.stringify(args))}`;
    const res = await fetch(url);
    const data = await res.json();

    if (!data.success) {
      status.innerHTML = `❌ <strong>Error:</strong> ${data.error}`;
      empty.style.display = "block";
      return;
    }

    neo4jRenderResults(data, action, input);
    status.textContent = "";
  } catch (e) {
    status.innerHTML = `❌ Failed to reach Neo4j API: ${e.message}`;
    empty.style.display = "block";
  }
}

function neo4jRenderResults(data, action, input) {
  const results = document.getElementById("neo4j-results");
  const empty   = document.getElementById("neo4j-empty");
  const title   = document.getElementById("neo4j-table-title");
  const tbody   = document.getElementById("neo4j-table-body");
  const summary = document.getElementById("neo4j-summary");
  const paths   = document.getElementById("neo4j-paths-box");

  // Normalise nodes from different response shapes
  let nodes = [];
  const d = data.data || {};

  if (Array.isArray(d.nodes))        nodes = d.nodes;
  else if (Array.isArray(d.results)) nodes = d.results.map(r => r.node || r);
  else if (d.classNode)              nodes = [d.classNode];
  else if (d.interfaceNode)          nodes = [d.interfaceNode];
  else if (d.testClass)              nodes = [d.testClass];
  else if (Array.isArray(d.methods)) nodes = d.methods;
  else                               nodes = [];

  neo4jLastNodes = nodes;

  if (nodes.length === 0) {
    empty.style.display = "block";
    document.getElementById("neo4j-status").textContent = "No results found in the graph.";
    return;
  }

  // Title
  const actionLabel = document.getElementById("neo4j-action").selectedOptions[0].text;
  title.textContent = `${actionLabel} — "${input}" (${nodes.length} nodes)`;

  // Summary chips
  const types = {};
  nodes.forEach(n => {
    const t = (n.nodeLabels || [n.nodeType] || ["Node"])[0] || "Node";
    types[t] = (types[t] || 0) + 1;
  });
  summary.innerHTML = Object.entries(types).map(([t, c]) =>
    `<span style="background:var(--card-bg);border:1px solid var(--border-color);border-radius:20px;padding:4px 12px;font-size:12px;color:var(--text-muted);">${t} <strong style="color:var(--text-main);">${c}</strong></span>`
  ).join("");

  // Table rows
  tbody.innerHTML = nodes.map((n, i) => {
    const name      = n.name || n.className || "—";
    const fullName  = n.fullName || "";
    const filePath  = n.filePath || "";
    const pkg       = n.packageName || (fullName.includes(".") ? fullName.substring(0, fullName.lastIndexOf(".")) : "—");
    const type      = (n.nodeLabels || [n.nodeType] || [])[0] || "—";
    const score     = n.combinedScore != null ? `⭐ ${n.combinedScore.toFixed(2)}`
                    : n.pageRankScore  != null ? `📊 ${n.pageRankScore.toFixed(2)}`
                    : "—";
    const typeColor = type === "Class" ? "#7C3AED" : type === "TestClass" ? "#10B981" : type === "Interface" ? "#06B6D4" : "#6B7280";

    return `<tr style="border-bottom:1px solid var(--border-color); transition:background 0.15s;" onmouseover="this.style.background='var(--card-bg)'" onmouseout="this.style.background=''">
      <td style="padding:8px 12px; color:var(--text-muted);">${i + 1}</td>
      <td style="padding:8px 12px; font-weight:600; font-family:'JetBrains Mono',monospace;">${name}</td>
      <td style="padding:8px 12px;"><span style="background:${typeColor}22;color:${typeColor};padding:2px 8px;border-radius:4px;font-size:11px;font-weight:600;">${type}</span></td>
      <td style="padding:8px 12px; color:var(--text-muted); font-size:12px;">${pkg}</td>
      <td style="padding:8px 12px; font-size:12px;">${score}</td>
      <td style="padding:8px 12px; font-family:'JetBrains Mono',monospace; font-size:11px; color:var(--accent-light); word-break:break-all;">${filePath || "<em style='color:var(--text-muted)'>not mapped</em>"}</td>
    </tr>`;
  }).join("");

  // File paths box
  const pathList = nodes.map(n => n.filePath).filter(Boolean);
  paths.textContent = pathList.length
    ? pathList.join("\n")
    : "(No file paths returned — try a traversal action like Expand Both)";

  results.style.display = "block";
  empty.style.display   = "none";
}

function neo4jCopyPaths() {
  const pathList = neo4jLastNodes.map(n => n.filePath).filter(Boolean);
  if (!pathList.length) {
    alert("No file paths to copy.");
    return;
  }
  navigator.clipboard.writeText(pathList.join("\n"));
  showToastMsg(`✅ ${pathList.length} file paths copied to clipboard!`);
}

