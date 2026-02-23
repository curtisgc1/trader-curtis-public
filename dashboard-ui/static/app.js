async function fetchJson(url) {
  const res = await fetch(url);
  if (!res.ok) {
    throw new Error(`${url} failed: ${res.status}`);
  }
  return res.json();
}

async function fetchJsonSafe(url, fallback) {
  try {
    return await fetchJson(url);
  } catch (err) {
    console.error(`safe fetch fallback for ${url}:`, err);
    return fallback;
  }
}

async function postJson(url, body) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    throw new Error(`${url} failed: ${res.status}`);
  }
  return res.json();
}

function setStatus(text, cls = "") {
  const el = document.getElementById("status-pill");
  el.textContent = text;
  el.className = `status ${cls}`;
}

function renderSummary(summary) {
  const el = document.getElementById("summary");
  if (!summary) return;
  const stats = [
    ["Total Trades", summary.total_trades],
    ["Win Rate", `${summary.win_rate}%`],
    ["Avg PnL", summary.avg_pnl],
    ["Open Trades", summary.open_trades],
  ];
  el.innerHTML = stats
    .map(([label, value]) => {
      return `<div class="stat"><label>${label}</label><span>${value}</span></div>`;
    })
    .join("");

  if (summary.open_trades > 0) {
    document.getElementById("open-trades").textContent = `${summary.open_trades} open`;
  }
}

function renderSystemHealth(health) {
  const el = document.getElementById("system-health");
  if (!el) return;
  if (!health || !health.checks || health.checks.length === 0) {
    el.innerHTML = `<div class="empty">No health data</div>`;
    return;
  }
  const rows = health.checks.map((c) => {
    const cls = c.state === "good" ? "good" : (c.state === "warn" ? "warn" : "bad");
    return `<div class="item"><span class="label">${c.name}</span><span class="${cls}">${c.detail}</span></div>`;
  }).join("");
  el.innerHTML = rows;
}

function controlMap(rows) {
  const out = {};
  (rows || []).forEach((r) => {
    out[r.key] = r.value;
  });
  return out;
}

function renderControlWarnings(riskControls) {
  const el = document.getElementById("control-warning");
  if (!el) return;
  const map = controlMap(riskControls);
  const hlLive = map.allow_hyperliquid_live === "1";
  const hlNotional = parseFloat(map.hyperliquid_test_notional_usd || "0");
  if (hlLive && hlNotional < 10) {
    el.textContent = "Warning: Hyperliquid live mode is ON and notional is below ~$10 minimum for BTC perps.";
    return;
  }
  el.textContent = "";
}

async function updateControls(updates) {
  await postJson("/api/risk-controls", { updates });
  await boot();
}

async function runAction(action) {
  const status = document.getElementById("action-status");
  if (status) status.textContent = `Running: ${action}...`;
  const res = await postJson("/api/actions", { action });
  if (status) {
    status.textContent = res.ok ? `Started ${action} (pid ${res.pid})` : `Action failed: ${res.error || "unknown"}`;
  }
  return res;
}

function bindControlActions(riskControls) {
  const map = controlMap(riskControls);
  const hlInput = document.getElementById("hl-notional");
  if (hlInput && map.hyperliquid_test_notional_usd) {
    hlInput.value = map.hyperliquid_test_notional_usd;
  }

  const btnEnable = document.getElementById("btn-enable-auto");
  const btnDisable = document.getElementById("btn-disable-auto");
  const btnSaveHl = document.getElementById("btn-save-hl");
  const btnRunScan = document.getElementById("btn-run-scan");
  const btnSyncBroker = document.getElementById("btn-sync-broker");
  const btnRefreshLearning = document.getElementById("btn-refresh-learning");

  if (btnEnable) {
    btnEnable.onclick = async () => {
      const currentNotional = parseFloat((hlInput?.value || "10").toString());
      const safeNotional = Number.isFinite(currentNotional) ? Math.max(10, currentNotional) : 10;
      await updateControls({
        allow_live_trading: "0",
        enable_alpaca_paper_auto: "1",
        enable_hyperliquid_test_auto: "1",
        allow_hyperliquid_live: "1",
        hyperliquid_test_notional_usd: safeNotional.toString(),
      });
    };
  }

  if (btnDisable) {
    btnDisable.onclick = async () => {
      await updateControls({
        enable_alpaca_paper_auto: "0",
        enable_hyperliquid_test_auto: "0",
        allow_hyperliquid_live: "0",
      });
    };
  }

  if (btnSaveHl) {
    btnSaveHl.onclick = async () => {
      const value = (hlInput?.value || "1").toString();
      await updateControls({
        hyperliquid_test_notional_usd: value,
      });
    };
  }

  if (btnRunScan) {
    btnRunScan.onclick = async () => {
      await runAction("run_scan");
    };
  }
  if (btnSyncBroker) {
    btnSyncBroker.onclick = async () => {
      await runAction("sync_broker");
      await boot();
    };
  }
  if (btnRefreshLearning) {
    btnRefreshLearning.onclick = async () => {
      await runAction("refresh_learning");
      await boot();
    };
  }
}

function renderTable(elId, rows, headers, fields) {
  const el = document.getElementById(elId);
  if (!rows || rows.length === 0) {
    el.innerHTML = `<div class="empty">No data</div>`;
    return;
  }
  const head = `<div class="row header">${headers.map(h => `<div>${h}</div>`).join("")}</div>`;
  const body = rows.map(r => {
    const cols = fields.map(f => {
      const v = r[f] ?? "";
      return `<div>${v}</div>`;
    }).join("");
    return `<div class="row">${cols}</div>`;
  }).join("");
  el.innerHTML = head + body;
}

function renderBookmarks(bookmarks) {
  const el = document.getElementById("bookmarks");
  const urls = [
    ...(bookmarks.status_urls || []),
    ...(bookmarks.external_urls || [])
  ];
  if (urls.length === 0) {
    el.innerHTML = `<div class="empty">No bookmarks found</div>`;
    return;
  }
  el.innerHTML = urls.map(u => `<a href="${u}" target="_blank" rel="noreferrer">${u}</a>`).join("");
}

function renderLearningHealth(learningHealth) {
  const row = {
    coverage: `${learningHealth.coverage_pct || 0}%`,
    tracked: `${learningHealth.tracked_coverage_pct || 0}%`,
    resolved: `${learningHealth.resolved_routes || 0}/${learningHealth.eligible_routes || 0}`,
    tracked_routes: learningHealth.tracked_routes || 0,
    realized: learningHealth.realized_routes || 0,
    operational: learningHealth.operational_routes || 0,
    win_rate: `${learningHealth.realized_win_rate || 0}%`,
    avg_pnl_pct: learningHealth.realized_avg_pnl_pct || 0,
  };
  renderTable(
    "learning-health",
    [row],
    ["Resolved %", "Tracked %", "Resolved", "Tracked", "Realized", "Operational", "Win %", "Avg PnL%"],
    ["coverage", "tracked", "resolved", "tracked_routes", "realized", "operational", "win_rate", "avg_pnl_pct"]
  );
}

function renderMemoryIntegrity(memoryIntegrity) {
  const el = document.getElementById("memory-integrity");
  if (!el) return;
  const top = {
    approved: memoryIntegrity.approved_routes || 0,
    linked: memoryIntegrity.linked_routes || 0,
    resolved: memoryIntegrity.resolved_routes || 0,
    state: memoryIntegrity.consistency_state || "unknown",
  };
  const rates = {
    coverage: `${memoryIntegrity.coverage_pct || 0}%`,
    tracked: `${memoryIntegrity.tracked_pct || 0}%`,
    realized: memoryIntegrity.realized_routes || 0,
    orphan: memoryIntegrity.orphan_outcomes || 0,
  };
  const rows = [
    `<div class="row header"><div>Approved</div><div>Linked</div><div>Resolved</div><div>State</div></div>`,
    `<div class="row"><div>${top.approved}</div><div>${top.linked}</div><div>${top.resolved}</div><div>${top.state}</div></div>`,
    `<div class="row header"><div>Coverage</div><div>Tracked</div><div>Realized</div><div>Orphans</div></div>`,
    `<div class="row"><div>${rates.coverage}</div><div>${rates.tracked}</div><div>${rates.realized}</div><div>${rates.orphan}</div></div>`,
  ];
  el.innerHTML = rows.join("");
}

function renderPageSummaries(signalRoutes, polymarketCandidates, polymarketMarkets, sourceScores, learningHealth) {
  renderTable(
    "signals-summary",
    [{
      routed: (signalRoutes || []).length,
      scored_sources: (sourceScores || []).length,
      resolved_pct: `${learningHealth.coverage_pct || 0}%`,
      link: "See /signals",
    }],
    ["Routes", "Sources", "Resolved %", "More"],
    ["routed", "scored_sources", "resolved_pct", "link"]
  );
  renderTable(
    "polymarket-summary",
    [{
      candidates: (polymarketCandidates || []).length,
      markets: (polymarketMarkets || []).length,
      status: "Integrated",
      link: "See /polymarket",
    }],
    ["Candidates", "Markets", "Status", "More"],
    ["candidates", "markets", "status", "link"]
  );
  renderTable(
    "learning-summary",
    [{
      resolved: `${learningHealth.resolved_routes || 0}/${learningHealth.eligible_routes || 0}`,
      tracked: `${learningHealth.tracked_coverage_pct || 0}%`,
      win_rate: `${learningHealth.realized_win_rate || 0}%`,
      link: "See /learning",
    }],
    ["Resolved", "Tracked", "Win %", "More"],
    ["resolved", "tracked", "win_rate", "link"]
  );
}

async function boot() {
  try {
    setStatus("loading");
    const [candidates, summary, systemHealth, learningHealth, memoryIntegrity, trades, patterns, copyTrades, bookmarks, externalSignals, riskControls, signalRoutes, sourceScores, polymarketCandidates, polymarketMarkets] = await Promise.all([
      fetchJsonSafe("/api/candidates", []),
      fetchJsonSafe("/api/summary", {}),
      fetchJsonSafe("/api/system-health", { overall: "warn", checks: [] }),
      fetchJsonSafe("/api/learning-health", {}),
      fetchJsonSafe("/api/memory-integrity", {}),
      fetchJsonSafe("/api/trades", []),
      fetchJsonSafe("/api/patterns", []),
      fetchJsonSafe("/api/copy-trades", []),
      fetchJsonSafe("/api/bookmarks", { status_urls: [], external_urls: [] }),
      fetchJsonSafe("/api/external-signals", []),
      fetchJsonSafe("/api/risk-controls", []),
      fetchJsonSafe("/api/signal-routes", []),
      fetchJsonSafe("/api/source-scores", []),
      fetchJsonSafe("/api/polymarket-candidates", []),
      fetchJsonSafe("/api/polymarket-markets", []),
    ]);

    renderSummary(summary);
    renderSystemHealth(systemHealth);
    renderTable("trades", trades.slice(0, 8), ["Ticker", "Entry", "Exit", "PnL"], ["ticker", "entry_price", "exit_price", "pnl"]);
    renderTable("patterns", patterns.slice(0, 8), ["Ticker", "Pattern", "Dir", "Time"], ["ticker", "pattern_name", "direction", "timestamp"]);
    renderTable("copy-trades", copyTrades.slice(0, 8), ["Source", "Ticker", "Type", "Time"], ["source_handle", "ticker", "call_type", "call_timestamp"]);
    renderTable("candidates", candidates.slice(0, 8), ["Ticker", "Score", "Dir", "Source"], ["ticker", "score", "direction", "source"]);
    renderTable("external-signals", externalSignals.slice(0, 8), ["Source", "Ticker", "Dir", "Conf"], ["source", "ticker", "direction", "confidence"]);
    renderTable("risk-controls", riskControls, ["Key", "Value", "Updated"], ["key", "value", "updated_at"]);
    bindControlActions(riskControls);
    renderControlWarnings(riskControls);
    renderPageSummaries(signalRoutes, polymarketCandidates, polymarketMarkets, sourceScores, learningHealth || {});
    renderLearningHealth(learningHealth || {});
    renderMemoryIntegrity(memoryIntegrity || {});
    renderBookmarks(bookmarks);

    const topState = (systemHealth && systemHealth.overall) || "good";
    setStatus("online", topState === "good" ? "good" : (topState === "warn" ? "warn" : "bad"));
  } catch (err) {
    console.error(err);
    setStatus("online", "warn");
  }
}

boot();
