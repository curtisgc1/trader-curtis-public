async function fetchJson(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${url} failed: ${res.status}`);
  return res.json();
}

async function postJson(url, body) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`${url} failed: ${res.status}`);
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
  const body = rows.map((r) => `<div class="row">${fields.map((f) => `<div>${r[f] ?? ""}</div>`).join("")}</div>`).join("");
  el.innerHTML = head + body;
}

function renderChartLiquidity(rows) {
  const el = document.getElementById("chart-liquidity");
  if (!el) return;
  if (!rows || rows.length === 0) {
    el.innerHTML = `<div class="empty">No data</div>`;
    return;
  }
  const head = `<div class="row header"><div>Ticker</div><div>Dir</div><div>Pattern</div><div>Chart</div></div>`;
  const body = rows.slice(0, 20).map((r) => {
    const link = r.chart_url ? `<a href="${r.chart_url}" target="_blank" rel="noreferrer">open chart</a>` : "";
    return `<div class="row"><div>${r.ticker || ""}</div><div>${r.direction || ""}</div><div>${r.pattern || ""}</div><div>${link}</div></div>`;
  }).join("");
  el.innerHTML = head + body;
}

function renderSignalReadiness(readiness) {
  const checks = readiness?.checks || [];
  const first = {
    state: readiness?.state || "unknown",
    score: readiness?.score ?? 0,
    blockers: (readiness?.blockers || []).length,
    checks: checks.length,
  };
  renderTable("signal-readiness", [first], ["State", "Score", "Blockers", "Checks"], ["state", "score", "blockers", "checks"]);
}

function bindActions() {
  const btn = document.getElementById("btn-validate-signals");
  const status = document.getElementById("action-status");
  if (!btn) return;
  btn.onclick = async () => {
    try {
      if (status) status.textContent = "Running validate_signals...";
      const res = await postJson("/api/actions", { action: "validate_signals" });
      if (status) status.textContent = res.ok ? `Started validate_signals (pid ${res.pid})` : `Failed: ${res.error || "unknown"}`;
    } catch (err) {
      if (status) status.textContent = `Failed: ${err.message}`;
    }
  };
}

async function boot() {
  try {
    setStatus("loading");
    const [systemHealth, signalReadiness, signalRoutes, bookmarkTheses, pipelineSignals, executionOrders, sourceScores, eventAlerts, quantValidations, chartLiquidity] = await Promise.all([
      fetchJson("/api/system-health"),
      fetchJson("/api/signal-readiness"),
      fetchJson("/api/signal-routes"),
      fetchJson("/api/bookmark-theses"),
      fetchJson("/api/pipeline-signals"),
      fetchJson("/api/execution-orders"),
      fetchJson("/api/source-scores"),
      fetchJson("/api/event-alerts"),
      fetchJson("/api/quant-validations"),
      fetchJson("/api/chart-liquidity"),
    ]);

    renderSignalReadiness(signalReadiness || {});
    renderTable("signal-routes", (signalRoutes || []).slice(0, 30), ["Ticker", "Score", "Decision", "Reason"], ["ticker", "score", "decision", "reason"]);
    renderTable("bookmark-theses", (bookmarkTheses || []).slice(0, 20), ["Source", "Type", "Horizon", "Conf"], ["source_handle", "thesis_type", "horizon", "confidence"]);
    renderTable("pipeline-signals", (pipelineSignals || []).slice(0, 30), ["Pipe", "Asset", "Dir", "Score"], ["pipeline_id", "asset", "direction", "score"]);
    renderTable("execution-orders", (executionOrders || []).slice(0, 30), ["Ticker", "Dir", "Mode", "Status"], ["ticker", "direction", "mode", "order_status"]);
    renderTable("source-scores", (sourceScores || []).slice(0, 20), ["Source", "N", "Appr", "Reliability"], ["source_tag", "sample_size", "approved_rate", "reliability_score"]);
    renderTable("event-alerts", (eventAlerts || []).slice(0, 20), ["Playbook", "Asset", "Dir", "Priority"], ["playbook_id", "proposed_asset", "direction", "priority"]);
    renderTable("quant-validations", (quantValidations || []).slice(0, 40), ["Ticker", "Pass", "EV%", "Win%"], ["ticker", "passed", "expected_value_percent", "win_rate"]);
    renderChartLiquidity(chartLiquidity || []);
    bindActions();

    const topState = (systemHealth && systemHealth.overall) || "good";
    setStatus("online", topState === "good" ? "good" : (topState === "warn" ? "warn" : "bad"));
  } catch (err) {
    console.error(err);
    setStatus("offline", "bad");
  }
}

boot();
