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

function renderBreakthroughEvents(rows) {
  const view = (rows || []).slice(0, 20).map((r) => ({
    ...r,
    source_short: (r.source || "").slice(0, 22),
    title_short: (r.title || "").slice(0, 90),
  }));
  renderTable(
    "breakthrough-events",
    view,
    ["Source", "Modality", "Score", "Title"],
    ["source_short", "modality", "score", "title_short"]
  );
}

function renderBreakthroughMap(rows) {
  const view = (rows || []).slice(0, 20).map((r) => ({
    modality: r.modality || "",
    mapped_tickers: r.mapped_tickers || "",
    confidence: r.confidence || "",
  }));
  renderTable(
    "breakthrough-map",
    view,
    ["Modality", "Tickers", "Conf"],
    ["modality", "mapped_tickers", "confidence"]
  );
}

function renderAllocator(rows) {
  const view = (rows || []).slice(0, 30).map((r) => ({
    ...r,
    allowed_txt: Number(r.allowed || 0) === 1 ? "yes" : "no",
    factor_txt: Number(r.factor || 1).toFixed(2),
    notional_pair: `${Number(r.base_notional || 0).toFixed(0)} -> ${Number(r.adjusted_notional || 0).toFixed(0)}`,
  }));
  renderTable(
    "allocator-decisions",
    view,
    ["Ticker", "Source", "Regime", "Factor", "Notional", "Allowed"],
    ["ticker", "source_tag", "regime", "factor_txt", "notional_pair", "allowed_txt"]
  );

  const el = document.getElementById("allocator-summary");
  if (!el) return;
  const n = view.length;
  if (!n) {
    el.innerHTML = `<div class="empty">No allocator decisions yet</div>`;
    return;
  }
  const blocked = view.filter((x) => x.allowed_txt === "no").length;
  const avgFactor = view.reduce((s, x) => s + Number(x.factor || 1), 0) / n;
  const regimes = {};
  view.forEach((x) => { regimes[x.regime || "unknown"] = (regimes[x.regime || "unknown"] || 0) + 1; });
  const topRegime = Object.entries(regimes).sort((a, b) => b[1] - a[1])[0]?.[0] || "unknown";
  renderTable(
    "allocator-summary",
    [{ total: n, blocked, avg_factor: avgFactor.toFixed(2), regime: topRegime }],
    ["Decisions", "Blocked", "Avg Factor", "Top Regime"],
    ["total", "blocked", "avg_factor", "regime"]
  );
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
    const [systemHealth, signalReadiness, signalRoutes, bookmarkTheses, pipelineSignals, executionOrders, sourceScores, eventAlerts, quantValidations, chartLiquidity, breakthroughEvents, allocatorDecisions] = await Promise.all([
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
      fetchJson("/api/breakthrough-events"),
      fetchJson("/api/allocator-decisions"),
    ]);

    renderSignalReadiness(signalReadiness || {});
    renderTable("signal-routes", (signalRoutes || []).slice(0, 30), ["Ticker", "Score", "Decision", "Reason"], ["ticker", "score", "decision", "reason"]);
    renderTable("bookmark-theses", (bookmarkTheses || []).slice(0, 20), ["Source", "Type", "Horizon", "Conf"], ["source_handle", "thesis_type", "horizon", "confidence"]);
    renderTable("pipeline-signals", (pipelineSignals || []).slice(0, 30), ["Pipe", "Asset", "Dir", "Score"], ["pipeline_id", "asset", "direction", "score"]);
    const execRows = (executionOrders || []).slice(0, 30).map((r) => ({
      ...r,
      leverage_allowed: Number(r.leverage_capable || 0) === 1 ? "yes" : "no",
      leverage: `${Number(r.leverage_used || 1).toFixed(2)}x`,
    }));
    renderTable("execution-orders", execRows, ["Ticker", "Dir", "Mode", "Lev Allowed", "Leverage", "Status"], ["ticker", "direction", "mode", "leverage_allowed", "leverage", "order_status"]);
    renderTable("source-scores", (sourceScores || []).slice(0, 20), ["Source", "N", "Appr", "Reliability"], ["source_tag", "sample_size", "approved_rate", "reliability_score"]);
    renderTable("event-alerts", (eventAlerts || []).slice(0, 20), ["Playbook", "Asset", "Dir", "Priority"], ["playbook_id", "proposed_asset", "direction", "priority"]);
    renderTable("quant-validations", (quantValidations || []).slice(0, 40), ["Ticker", "Pass", "EV%", "Win%"], ["ticker", "passed", "expected_value_percent", "win_rate"]);
    renderChartLiquidity(chartLiquidity || []);
    renderBreakthroughEvents(breakthroughEvents || []);
    renderBreakthroughMap(breakthroughEvents || []);
    renderAllocator(allocatorDecisions || []);
    bindActions();

    const topState = (systemHealth && systemHealth.overall) || "good";
    setStatus("online", topState === "good" ? "good" : (topState === "warn" ? "warn" : "bad"));
  } catch (err) {
    console.error(err);
    setStatus("offline", "bad");
  }
}

boot();
