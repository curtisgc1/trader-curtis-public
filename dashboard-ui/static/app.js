async function fetchJson(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${url} failed: ${res.status}`);
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
  if (!res.ok) throw new Error(`${url} failed: ${res.status}`);
  return res.json();
}

let curveMode = localStorage.getItem("curveMode") || "time";

function setStatus(text, cls = "") {
  const el = document.getElementById("status-pill");
  if (!el) return;
  el.textContent = text;
  el.className = `status ${cls}`;
}

function fmtCurrency(v) {
  const n = Number(v || 0);
  if (!Number.isFinite(n)) return "$0";
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(n);
}

function controlMap(rows) {
  const out = {};
  (rows || []).forEach((r) => { out[r.key] = r.value; });
  return out;
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

function renderHero(summary, controls) {
  const pnlEl = document.getElementById("metric-pnl");
  const winEl = document.getElementById("metric-win");
  const openEl = document.getElementById("metric-open");
  const modeEl = document.getElementById("metric-mode");

  if (pnlEl) pnlEl.textContent = fmtCurrency(summary.total_pnl || summary.avg_pnl || 0);
  if (winEl) winEl.textContent = `${summary.win_rate || 0}%`;
  if (openEl) openEl.textContent = `${summary.open_trades || 0}`;

  const c = controlMap(controls);
  const autoOn = c.enable_alpaca_paper_auto === "1" || c.enable_hyperliquid_test_auto === "1" || c.enable_polymarket_auto === "1";
  const safe = c.allow_live_trading !== "1" && c.enable_alpaca_paper_auto !== "1" && c.enable_hyperliquid_test_auto !== "1" && c.enable_polymarket_auto !== "1";
  let mode = "Safe";
  if (autoOn && c.allow_live_trading === "1") mode = "Auto Live";
  else if (autoOn) mode = "Auto Paper";
  else if (!safe) mode = "Mixed";
  if (modeEl) modeEl.textContent = mode;
}

function setRing(id, textId, pct, label) {
  const el = document.getElementById(id);
  const t = document.getElementById(textId);
  if (!el || !t) return;
  const p = Math.max(0, Math.min(100, Number(pct || 0)));
  el.style.setProperty("--p", p);
  t.textContent = `${label} ${Math.round(p)}%`;
}

function scoreFromHealth(health) {
  const checks = health?.checks || [];
  if (checks.length === 0) return 50;
  let score = 100;
  checks.forEach((c) => {
    if (c.state === "bad") score -= 25;
    else if (c.state === "warn") score -= 10;
  });
  return Math.max(5, score);
}

function renderPulse(systemHealth, readiness, controls) {
  const healthScore = scoreFromHealth(systemHealth);
  const readinessScore = Number(readiness?.score || 0);
  const c = controlMap(controls);
  const autoFlags = ["enable_alpaca_paper_auto", "enable_hyperliquid_test_auto", "enable_polymarket_auto"];
  const on = autoFlags.filter((k) => c[k] === "1").length;
  const autoScore = Math.round((on / autoFlags.length) * 100);

  setRing("ring-health", "ring-health-text", healthScore, "Health");
  setRing("ring-readiness", "ring-readiness-text", readinessScore, "Readiness");
  setRing("ring-automation", "ring-automation-text", autoScore, "Automation");
}

function renderAlerts(systemHealth, readiness, awareness) {
  const el = document.getElementById("alerts");
  if (!el) return;

  const items = [];
  (systemHealth?.checks || []).forEach((c) => {
    if (c.state !== "good") items.push({ n: c.name, d: c.detail, s: c.state });
  });
  (readiness?.checks || []).forEach((c) => {
    if (c.state === "bad") items.push({ n: `Readiness: ${c.name}`, d: c.detail, s: c.state });
  });
  (readiness?.blockers || []).forEach((b) => {
    items.push({ n: "Blocker", d: b, s: "bad" });
  });
  (awareness?.blockers || []).forEach((b) => {
    items.push({ n: "Awareness Blocker", d: b, s: "bad" });
  });
  (awareness?.warnings || []).forEach((w) => {
    items.push({ n: "Awareness Warning", d: w, s: "warn" });
  });

  if (items.length === 0) {
    el.innerHTML = `<div class="item"><span class="label">All core checks look stable</span><span class="good">OK</span></div>`;
    return;
  }

  el.innerHTML = items.slice(0, 6).map((x) => {
    const cls = x.s === "bad" ? "bad" : "warn";
    return `<div class="item"><span class="label">${x.n}: ${x.d}</span><span class="${cls}">${x.s.toUpperCase()}</span></div>`;
  }).join("");
}

function renderAwareness(awareness) {
  const brief = document.getElementById("awareness-brief");
  if (brief) {
    const rows = [
      ["Awareness", awareness?.overall || "unknown"],
      ["Effective Mode", awareness?.effective_mode || "unknown"],
      ["Summary", awareness?.summary || "n/a"],
    ];
    brief.innerHTML = rows
      .map(([k, v]) => `<div class="item"><span class="label">${k}</span><span>${v}</span></div>`)
      .join("");
  }
  renderTable("awareness-checks", awareness?.checks || [], ["Check", "State", "Detail"], ["name", "state", "detail"]);
}

function renderWallet(rows) {
  const el = document.getElementById("wallet-brief");
  if (!el) return;
  const map = {};
  (rows || []).forEach((r) => { map[r.key] = r.value; });

  const lines = [
    ["HL Wallet", map.hl_wallet_address || "not set"],
    ["HL Network", map.hl_network || "unknown"],
    ["HL API", map.hl_api_url || "n/a"],
    ["Poly Wallet", map.poly_wallet_address || "not set"],
    ["Poly Host", map.poly_clob_host || "n/a"],
    ["Alpaca", map.alpaca_base_url || "n/a"],
  ];

  el.innerHTML = lines.map(([k, v]) => `<div class="item"><span class="label">${k}</span><span>${v}</span></div>`).join("");
}

function renderFlow(exOrders, polyOrders) {
  const exEl = document.getElementById("list-exec");
  const poEl = document.getElementById("list-poly");

  if (exEl) {
    const rows = (exOrders || []).slice(0, 8);
    exEl.innerHTML = rows.length === 0
      ? `<div class="empty">No execution orders</div>`
      : rows.map((r) => {
          const st = String(r.order_status || "").toLowerCase();
          const cls = st.includes("block") || st.includes("fail") ? "bad" : (st.includes("submit") || st.includes("fill") ? "good" : "warn");
          return `<div class="flow-item"><div><strong>${r.ticker || ""}</strong> ${r.direction || ""}</div><div>${r.mode || ""} • ${fmtCurrency(r.notional || 0)}</div><div class="${cls}">${r.order_status || ""}</div></div>`;
        }).join("");
  }

  if (poEl) {
    const rows = (polyOrders || []).slice(0, 8);
    poEl.innerHTML = rows.length === 0
      ? `<div class="empty">No polymarket orders</div>`
      : rows.map((r) => {
          const st = String(r.status || "").toLowerCase();
          const cls = st.includes("block") || st.includes("fail") ? "bad" : (st.includes("submit") || st.includes("fill") ? "good" : "warn");
          return `<div class="flow-item"><div><strong>${r.strategy_id || ""}</strong> ${r.outcome || ""}</div><div>${r.mode || ""} • ${fmtCurrency(r.notional || 0)}</div><div class="${cls}">${r.status || ""}</div></div>`;
        }).join("");
  }
}

function renderPortfolio(snapshot) {
  const brief = document.getElementById("portfolio-brief");
  const alpEl = document.getElementById("alpaca-positions");
  const hlEl = document.getElementById("hl-positions");

  const alp = snapshot?.alpaca || {};
  const hl = snapshot?.hyperliquid || {};

  if (brief) {
    const rows = [
      ["Alpaca Equity", fmtCurrency(alp.equity || 0)],
      ["Alpaca Cash", fmtCurrency(alp.cash || 0)],
      ["Alpaca Buying Power", fmtCurrency(alp.buying_power || 0)],
      ["HL Network", hl.network || "unknown"],
      ["HL Account Value", fmtCurrency(hl.account_value || 0)],
      ["HL Withdrawable", fmtCurrency(hl.withdrawable || 0)],
    ];
    brief.innerHTML = rows
      .map(([k, v]) => `<div class="item"><span class="label">${k}</span><span>${v}</span></div>`)
      .join("");
  }

  if (alpEl) {
    const rows = alp.positions || [];
    alpEl.innerHTML = rows.length
      ? rows.slice(0, 8).map((p) => {
          const pl = Number(p.unrealized_pl || 0);
          const cls = pl >= 0 ? "good" : "bad";
          return `<div class="flow-item"><div><strong>${p.symbol || ""}</strong> ${p.qty || ""} ${p.side || ""}</div><div>Value ${fmtCurrency(p.market_value || 0)}</div><div class="${cls}">uPnL ${fmtCurrency(pl)}</div></div>`;
        }).join("")
      : `<div class="empty">${alp.error ? `Alpaca: ${alp.error}` : "No Alpaca positions"}</div>`;
  }

  if (hlEl) {
    const rows = hl.positions || [];
    hlEl.innerHTML = rows.length
      ? rows.slice(0, 8).map((p) => {
          const pl = Number(p.unrealized_pnl || 0);
          const cls = pl >= 0 ? "good" : "bad";
          return `<div class="flow-item"><div><strong>${p.coin || ""}</strong> ${p.szi || ""}</div><div>Value ${fmtCurrency(p.position_value || 0)}</div><div class="${cls}">uPnL ${fmtCurrency(pl)}</div></div>`;
        }).join("")
      : `<div class="empty">${hl.error ? `HL: ${hl.error}` : "No HL positions"}</div>`;
  }
}

function renderTradeDecisions(rows) {
  const el = document.getElementById("trade-decisions");
  if (!el) return;
  if (!rows || rows.length === 0) {
    el.innerHTML = `<div class="empty">No recent execution decisions</div>`;
    return;
  }
  el.innerHTML = rows.slice(0, 12).map((r) => {
    const st = String(r.order_status || "").toLowerCase();
    const cls = st.includes("block") || st.includes("fail") ? "bad" : (st.includes("submit") || st.includes("fill") ? "good" : "warn");
    const why = r.learning_reason || r.route_reason || r.notes || "n/a";
    return `<details class="flow-item"><summary><strong>${r.ticker || ""}</strong> ${r.direction || ""} • ${fmtCurrency(r.notional || 0)} • <span class="${cls}">${r.order_status || ""}</span></summary><div>source: ${r.source_tag || "n/a"} | score: ${r.score || ""} | mode: ${r.mode || ""}</div><div>reason: ${why}</div><div>notes: ${r.notes || ""}</div></details>`;
  }).join("");
}

function buildLinePath(points, width, height, pad) {
  if (!points || points.length === 0) return { path: "", minY: 0, maxY: 0 };
  const ys = points.map((p) => Number(p.y || 0));
  let minY = Math.min(...ys);
  let maxY = Math.max(...ys);
  if (minY === maxY) {
    minY -= 1;
    maxY += 1;
  }
  const innerW = width - pad * 2;
  const innerH = height - pad * 2;
  const toX = (idx) => pad + (points.length <= 1 ? innerW / 2 : (idx / (points.length - 1)) * innerW);
  const toY = (v) => pad + (maxY - v) / (maxY - minY) * innerH;
  const d = points.map((p, i) => `${i === 0 ? "M" : "L"} ${toX(i).toFixed(2)} ${toY(Number(p.y || 0)).toFixed(2)}`).join(" ");
  return { path: d, minY, maxY };
}

function renderPerformanceCurve(curve) {
  const el = document.getElementById("perf-chart");
  const statsEl = document.getElementById("perf-stats");
  const modeEl = document.getElementById("curve-mode-label");
  if (!el || !statsEl || !modeEl) return;

  const series = curveMode === "trade" ? (curve?.by_trade || []) : (curve?.by_time || []);
  const unit = curve?.unit || "usd";
  const fmtVal = (v) => unit === "pct" ? `${Number(v || 0).toFixed(2)}%` : fmtCurrency(v || 0);
  modeEl.textContent = `mode: ${curveMode === "trade" ? "trade # scale" : "time scale"}`;

  if (!series.length) {
    el.innerHTML = `<div class="empty">No performance data yet</div>`;
    statsEl.innerHTML = "";
    return;
  }

  const width = 860;
  const height = 220;
  const pad = 26;
  const { path, minY, maxY } = buildLinePath(series, width, height, pad);
  const last = series[series.length - 1] || {};

  const y0 = maxY === minY ? height / 2 : (pad + (maxY - 0) / (maxY - minY) * (height - pad * 2));
  const zeroLine = y0 >= pad && y0 <= (height - pad)
    ? `<line class="perf-axis" x1="${pad}" y1="${y0.toFixed(2)}" x2="${width - pad}" y2="${y0.toFixed(2)}" />`
    : "";

  el.innerHTML = `
    <svg viewBox="0 0 ${width} ${height}" preserveAspectRatio="none">
      <line class="perf-axis" x1="${pad}" y1="${height - pad}" x2="${width - pad}" y2="${height - pad}" />
      <line class="perf-axis" x1="${pad}" y1="${pad}" x2="${pad}" y2="${height - pad}" />
      ${zeroLine}
      <path class="perf-line" d="${path}" />
      <text class="perf-label" x="${pad}" y="${pad - 6}">${fmtVal(maxY)}</text>
      <text class="perf-label" x="${pad}" y="${height - 8}">${fmtVal(minY)}</text>
      <text class="perf-label" x="${width - pad - 90}" y="${height - 8}">${curveMode === "trade" ? "Trade #" : "Time"}</text>
    </svg>
  `;

  statsEl.innerHTML = [
    ["Source", curve?.source || "n/a"],
    ["Points", String(curve?.count || 0)],
    ["Wins", String(curve?.wins || 0)],
    ["Losses", String(curve?.losses || 0)],
    ["Unit", unit === "pct" ? "%" : "USD"],
    ["Total", fmtVal(curve?.total_pnl || last.y || 0)],
    ["Max Drawdown", fmtVal(curve?.max_drawdown || 0)],
  ].map(([k, v]) => `<div class="item"><span class="label">${k}</span><span>${v}</span></div>`).join("");
}

function bindCurveButtons(curve) {
  const btnTime = document.getElementById("btn-curve-time");
  const btnTrade = document.getElementById("btn-curve-trade");
  if (btnTime) {
    btnTime.onclick = () => {
      curveMode = "time";
      localStorage.setItem("curveMode", curveMode);
      renderPerformanceCurve(curve);
    };
  }
  if (btnTrade) {
    btnTrade.onclick = () => {
      curveMode = "trade";
      localStorage.setItem("curveMode", curveMode);
      renderPerformanceCurve(curve);
    };
  }
}

async function updateControls(updates) {
  await postJson("/api/risk-controls", { updates });
}

async function runAction(action) {
  const status = document.getElementById("action-status");
  if (status) status.textContent = `Running: ${action}...`;
  const res = await postJson("/api/actions", { action });
  if (status) status.textContent = res.ok ? `Started ${action} (pid ${res.pid})` : `Action failed: ${res.error || "unknown"}`;
}

function bindControls(controls) {
  const c = controlMap(controls);
  const hlNotional = document.getElementById("ctl-hl-notional");
  const hlLev = document.getElementById("ctl-hl-lev");
  const maxSignal = document.getElementById("ctl-max-signal");
  const minScore = document.getElementById("ctl-min-score");
  const routeLimit = document.getElementById("ctl-route-limit");

  if (hlNotional) hlNotional.value = c.hyperliquid_test_notional_usd || "10";
  if (hlLev) hlLev.value = c.hyperliquid_test_leverage || "1";
  if (maxSignal) maxSignal.value = c.max_signal_notional_usd || "150";
  if (minScore) minScore.value = c.min_candidate_score || "50";
  if (routeLimit) routeLimit.value = c.auto_route_limit || "24";

  const status = document.getElementById("master-control-status");
  const setMsg = (m) => { if (status) status.textContent = m; };

  const btnSave = document.getElementById("btn-master-save");
  if (btnSave) btnSave.onclick = async () => {
    await updateControls({
      hyperliquid_test_notional_usd: (hlNotional?.value || "10").toString(),
      hyperliquid_test_leverage: (hlLev?.value || "1").toString(),
      max_signal_notional_usd: (maxSignal?.value || "150").toString(),
      min_candidate_score: (minScore?.value || "50").toString(),
      auto_route_limit: (routeLimit?.value || "24").toString(),
    });
    setMsg("Saved limits");
    await boot();
  };

  const btnEnable = document.getElementById("btn-master-enable");
  if (btnEnable) btnEnable.onclick = async () => {
    await updateControls({ allow_live_trading: "1", enable_alpaca_paper_auto: "1", enable_hyperliquid_test_auto: "1", enable_polymarket_auto: "1" });
    setMsg("Auto trading enabled");
    await boot();
  };

  const btnSafe = document.getElementById("btn-master-safe");
  if (btnSafe) btnSafe.onclick = async () => {
    await updateControls({ allow_live_trading: "0", enable_alpaca_paper_auto: "0", enable_hyperliquid_test_auto: "0", enable_polymarket_auto: "0" });
    setMsg("Safe mode enabled");
    await boot();
  };

  const btnQuant = document.getElementById("btn-master-quant-soft");
  if (btnQuant) btnQuant.onclick = async () => {
    await updateControls({ quant_gate_enforce: "0" });
    setMsg("Quant soft mode enabled");
    await boot();
  };

  const btnScan = document.getElementById("btn-run-scan");
  const btnCycle = document.getElementById("btn-run-cycle");
  if (btnScan) btnScan.onclick = async () => { await runAction("run_scan"); };
  if (btnCycle) btnCycle.onclick = async () => { await runAction("run_cycle"); };

  const btnSync = document.getElementById("btn-sync-broker");
  if (btnSync) btnSync.onclick = async () => { await runAction("sync_broker"); await boot(); };

  const btnLearn = document.getElementById("btn-refresh-learning");
  if (btnLearn) btnLearn.onclick = async () => { await runAction("refresh_learning"); await boot(); };

  const btnAware = document.getElementById("btn-check-awareness");
  if (btnAware) btnAware.onclick = async () => { await runAction("check_awareness"); await boot(); };
}

let booting = false;
async function boot() {
  if (booting) return;
  booting = true;
  try {
    setStatus("loading");
    const [summary, systemHealth, readiness, controls, walletConfig, exOrders, polyOrders, portfolioSnapshot, tradeDecisions, awareness, performanceCurve] = await Promise.all([
      fetchJsonSafe("/api/summary", {}),
      fetchJsonSafe("/api/system-health", { overall: "warn", checks: [] }),
      fetchJsonSafe("/api/signal-readiness", { score: 0, checks: [], blockers: [] }),
      fetchJsonSafe("/api/risk-controls", []),
      fetchJsonSafe("/api/wallet-config", []),
      fetchJsonSafe("/api/execution-orders", []),
      fetchJsonSafe("/api/polymarket-orders", []),
      fetchJsonSafe("/api/portfolio-snapshot", {}),
      fetchJsonSafe("/api/recent-trade-decisions", []),
      fetchJsonSafe("/api/agent-awareness", { overall: "warn", checks: [], blockers: [], warnings: [] }),
      fetchJsonSafe("/api/performance-curve", { by_time: [], by_trade: [] }),
    ]);

    renderHero(summary, controls);
    renderPulse(systemHealth, readiness, controls);
    renderAlerts(systemHealth, readiness, awareness);
    renderWallet(walletConfig);
    renderAwareness(awareness);
    renderFlow(exOrders, polyOrders);
    renderPortfolio(portfolioSnapshot);
    renderTradeDecisions(tradeDecisions);
    renderPerformanceCurve(performanceCurve || {});
    bindCurveButtons(performanceCurve || {});
    renderTable("risk-controls", controls, ["Key", "Value", "Updated"], ["key", "value", "updated_at"]);
    bindControls(controls);

    const topState = (systemHealth && systemHealth.overall) || "warn";
    const awareState = (awareness && awareness.overall) || "warn";
    const merged = topState === "bad" || awareState === "bad" ? "bad" : (topState === "warn" || awareState === "warn" ? "warn" : "good");
    setStatus("online", merged === "good" ? "good" : (merged === "warn" ? "warn" : "bad"));
  } catch (err) {
    console.error(err);
    setStatus("offline", "bad");
  } finally {
    booting = false;
  }
}

boot();
setInterval(() => {
  boot();
}, 15000);
