async function fetchJson(url) {
  const res = await fetch(url);
  if (!res.ok) {
    throw new Error(`${url} failed: ${res.status}`);
  }
  return res.json();
}

function setStatus(text, cls = "") {
  const el = document.getElementById("status-pill");
  if (!el) return;
  el.textContent = text;
  el.className = `status ${cls}`;
}

function renderTable(elId, rows, headers, fields) {
  const el = document.getElementById(elId);
  if (!el) return;
  if (!rows || rows.length === 0) {
    el.innerHTML = `<div class="empty">No data</div>`;
    return;
  }
  const head = `<div class="row header">${headers.map((h) => `<div>${h}</div>`).join("")}</div>`;
  const body = rows.map((r) => {
    const cols = fields.map((f) => `<div>${r[f] ?? ""}</div>`).join("");
    return `<div class="row">${cols}</div>`;
  }).join("");
  el.innerHTML = head + body;
}

function renderLearningHealth(learningHealth) {
  const row = {
    coverage: `${learningHealth.coverage_pct || 0}%`,
    tracked: `${learningHealth.tracked_coverage_pct || 0}%`,
    resolved: `${learningHealth.resolved_routes || 0}/${learningHealth.eligible_routes || 0}`,
    realized: learningHealth.realized_routes || 0,
  };
  renderTable(
    "learning-health",
    [row],
    ["Resolved %", "Tracked %", "Resolved", "Realized"],
    ["coverage", "tracked", "resolved", "realized"]
  );
}

function renderMemoryIntegrity(memoryIntegrity) {
  const el = document.getElementById("memory-integrity");
  if (!el) return;
  const rows = [
    `<div class="row header"><div>Approved</div><div>Linked</div><div>Resolved</div><div>State</div></div>`,
    `<div class="row"><div>${memoryIntegrity.approved_routes || 0}</div><div>${memoryIntegrity.linked_routes || 0}</div><div>${memoryIntegrity.resolved_routes || 0}</div><div>${memoryIntegrity.consistency_state || "unknown"}</div></div>`,
    `<div class="row header"><div>Coverage</div><div>Tracked</div><div>Realized</div><div>Orphans</div></div>`,
    `<div class="row"><div>${memoryIntegrity.coverage_pct || 0}%</div><div>${memoryIntegrity.tracked_pct || 0}%</div><div>${memoryIntegrity.realized_routes || 0}</div><div>${memoryIntegrity.orphan_outcomes || 0}</div></div>`,
  ];
  el.innerHTML = rows.join("");
}

async function boot() {
  try {
    setStatus("loading");
    const [systemHealth, learningHealth, memoryIntegrity, tradeIntents, executionLearning, sourceLearning, strategyLearning, inputFeatureStats] = await Promise.all([
      fetchJson("/api/system-health"),
      fetchJson("/api/learning-health"),
      fetchJson("/api/memory-integrity"),
      fetchJson("/api/trade-intents"),
      fetchJson("/api/execution-learning"),
      fetchJson("/api/source-learning"),
      fetchJson("/api/strategy-learning"),
      fetchJson("/api/input-feature-stats"),
    ]);

    renderLearningHealth(learningHealth || {});
    renderMemoryIntegrity(memoryIntegrity || {});
    renderTable("trade-intents", (tradeIntents || []).slice(0, 20), ["Venue", "Symbol", "Side", "Status"], ["venue", "symbol", "side", "status"]);
    renderTable("execution-learning", (executionLearning || []).slice(0, 20), ["Ticker", "Source", "Venue", "Order"], ["ticker", "source_tag", "venue", "order_status"]);
    renderTable("source-learning", (sourceLearning || []).slice(0, 20), ["Source", "N", "Win %", "Avg PnL%", "Sharpe"], ["source_tag", "sample_size", "win_rate", "avg_pnl_percent", "sharpe_ratio"]);
    renderTable("strategy-learning", (strategyLearning || []).slice(0, 20), ["Strategy", "N", "Win %", "Avg PnL%"], ["strategy_tag", "sample_size", "win_rate", "avg_pnl_percent"]);
    renderTable(
      "input-feature-stats",
      (inputFeatureStats || []).slice(0, 40),
      ["Outcome", "Dimension", "Value", "N", "Win %", "Avg PnL%"],
      ["outcome_type", "dimension", "dimension_value", "sample_size", "win_rate", "avg_pnl_percent"]
    );

    const topState = (systemHealth && systemHealth.overall) || "good";
    setStatus("online", topState === "good" ? "good" : (topState === "warn" ? "warn" : "bad"));
  } catch (err) {
    console.error(err);
    setStatus("offline", "bad");
  }
}

boot();
