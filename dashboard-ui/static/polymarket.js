async function fetchJson(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${url} failed: ${res.status}`);
  return res.json();
}

const UI_BUILD = "20260228d";

async function fetchJsonSafe(url, fallback) {
  try {
    return await fetchJson(url);
  } catch (err) {
    console.error(`safe fetch fallback for ${url}:`, err);
    return fallback;
  }
}

function runUiStep(name, fn) {
  try {
    fn();
  } catch (err) {
    console.error(`ui step failed: ${name}`, err);
  }
}

async function postJson(url, body) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
  });
  if (!res.ok) throw new Error(`${url} failed: ${res.status}`);
  return res.json();
}

function fmtUsd(v) {
  const n = Number(v || 0);
  if (!Number.isFinite(n)) return "$0.00";
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 2 }).format(n);
}

function setStatus(text, cls = "") {
  const el = document.getElementById("status-pill");
  if (!el) return;
  el.textContent = text;
  el.className = `status ${cls}`;
}

/* ---------- Account Overview ---------- */

function renderPolyOverview(overview, snapshot) {
  const el = document.getElementById("poly-overview");
  if (!el) return;
  const poly = snapshot.polymarket || {};
  if (!overview || !poly) {
    el.innerHTML = `<div class="empty">No account data</div>`;
    return;
  }
  const mode = (overview.mode || "paper").toUpperCase();
  const modeCls = mode === "LIVE" ? "good" : "muted";
  const wallet = poly.wallet || "";
  const walletShort = wallet.length > 10 ? wallet.slice(0, 6) + "..." + wallet.slice(-4) : wallet || "—";
  const cap = overview.daily_cap_usd || 0;
  const used = overview.daily_used_usd || 0;
  const remaining = Math.max(0, cap - used);
  const pct = cap > 0 ? Math.min(100, (used / cap) * 100) : 0;
  const barColor = pct < 50 ? "var(--accent)" : pct < 75 ? "#f0ad4e" : "var(--danger)";
  const positions = poly.positions || [];
  const posCount = positions.length;
  const totalPnl = positions.reduce((s, p) => s + (p.total_pnl || 0), 0);
  const pnlCls = totalPnl >= 0 ? "pnl-pos" : "pnl-neg";

  el.innerHTML = [
    `<div class="account-header">`,
    `  <span><span class="badge ${modeCls === "good" ? "good-bg" : ""}" style="font-size:11px">${mode}</span> <span class="mono muted">${walletShort}</span></span>`,
    `  <span>${posCount} market${posCount !== 1 ? "s" : ""}</span>`,
    `</div>`,
    `<div class="account-stats">`,
    `  <div class="stat-box"><span class="stat-label">Daily Cap</span><span class="stat-value">${fmtUsd(cap)}</span></div>`,
    `  <div class="stat-box"><span class="stat-label">Used Today</span><span class="stat-value">${fmtUsd(used)} <span class="muted">(${pct.toFixed(0)}%)</span></span></div>`,
    `  <div class="stat-box"><span class="stat-label">Remaining</span><span class="stat-value">${fmtUsd(remaining)}</span></div>`,
    `  <div class="stat-box"><span class="stat-label">Open Markets</span><span class="stat-value">${posCount}</span></div>`,
    `</div>`,
    `<div class="margin-bar"><div class="margin-bar-fill" style="width:${pct.toFixed(1)}%;background:${barColor}"></div></div>`,
    `<div class="margin-bar-label muted">${pct.toFixed(0)}% daily exposure</div>`,
    `<div class="account-stats" style="margin-top:12px">`,
    `  <div class="stat-box"><span class="stat-label">Filled Live</span><span class="stat-value">${overview.filled_live || 0}</span></div>`,
    `  <div class="stat-box"><span class="stat-label">Submitted</span><span class="stat-value">${overview.submitted_live || 0}</span></div>`,
    `  <div class="stat-box"><span class="stat-label">Pending Approval</span><span class="stat-value">${overview.pending_approval || 0}</span></div>`,
    `  <div class="stat-box"><span class="stat-label">Failed</span><span class="stat-value">${overview.failed || 0}</span></div>`,
    `  <div class="stat-box"><span class="stat-label">Total uPnL</span><span class="stat-value ${pnlCls}">${totalPnl >= 0 ? "+" : ""}${fmtUsd(totalPnl)}</span></div>`,
    `</div>`,
  ].join("\n");
}

/* ---------- Position Cards ---------- */

function fmtPct(v) {
  const n = Number(v || 0) * 100;
  return Number.isFinite(n) ? n.toFixed(1) + "%" : "—";
}

function renderPolyPositions(snapshot) {
  const el = document.getElementById("poly-positions");
  if (!el) return;
  const markets = (snapshot.polymarket || {}).positions || [];
  if (!markets.length) {
    el.innerHTML = `<div class="position-card" style="text-align:center;opacity:0.5">No active positions</div>`;
    return;
  }
  el.innerHTML = markets.map((m) => {
    const question = m.question || m.market_id || "Unknown market";
    const questionShort = question.length > 90 ? question.slice(0, 87) + "..." : question;
    const pnl = m.total_pnl || 0;
    const pnlCls = pnl >= 0 ? "pnl-pos" : "pnl-neg";
    const tint = pnl >= 0 ? "rgba(0,209,178,0.05)" : "rgba(255,123,123,0.05)";
    const lastAt = (m.last_at || "").replace("T", " ").slice(0, 16);
    const linkHtml = m.market_url
      ? `<a class="position-link" href="${m.market_url}" target="_blank" rel="noopener">View on Polymarket &#8599;</a>`
      : "";

    const outcomeRows = (m.outcomes || []).map((o) => {
      const outcomeUpper = (o.outcome || "").toUpperCase();
      const isYes = outcomeUpper === "YES";
      const badgeCls = isYes ? "yes" : "no";
      const oPnl = o.unrealized_pnl || 0;
      const oPnlCls = oPnl >= 0 ? "pnl-pos" : "pnl-neg";
      const shares = Math.abs(o.net_shares || 0);
      return [
        `<div class="poly-outcome-row">`,
        `  <span class="poly-outcome-badge ${badgeCls}">${outcomeUpper}</span>`,
        `  <div class="stat-box"><span class="stat-label">Shares</span><span class="stat-value">${shares.toFixed(1)}</span></div>`,
        `  <div class="stat-box"><span class="stat-label">Avg Entry</span><span class="stat-value">${fmtPct(o.avg_entry)}</span></div>`,
        `  <div class="stat-box"><span class="stat-label">Current</span><span class="stat-value">${fmtPct(o.current_price)}</span></div>`,
        `  <div class="stat-box"><span class="stat-label">Cost</span><span class="stat-value">${fmtUsd(Math.abs(o.net_notional || 0))}</span></div>`,
        `  <div class="stat-box"><span class="stat-label">Value</span><span class="stat-value">${fmtUsd(o.current_value || 0)}</span></div>`,
        `  <div class="stat-box"><span class="stat-label">P&L</span><span class="stat-value ${oPnlCls}">${oPnl >= 0 ? "+" : ""}${fmtUsd(oPnl)}</span></div>`,
        `</div>`,
      ].join("\n");
    }).join("\n");

    return [
      `<div class="position-card" style="background:linear-gradient(180deg,${tint},#121720 90%)">`,
      `  <div class="position-header">`,
      `    <span class="position-coin" style="font-size:14px" title="${question}">${questionShort}</span>`,
      `  </div>`,
      `  ${outcomeRows}`,
      `  <div class="poly-card-footer">`,
      `    <div class="poly-card-summary">`,
      `      <span class="muted">Exposure ${fmtUsd(m.total_exposure || 0)}</span>`,
      `      <span class="${pnlCls}" style="font-weight:600">P&L ${pnl >= 0 ? "+" : ""}${fmtUsd(pnl)}</span>`,
      `      <span class="muted">Last fill ${lastAt || "—"}</span>`,
      `    </div>`,
      `    ${linkHtml}`,
      `  </div>`,
      `</div>`,
    ].join("\n");
  }).join("\n");
}

/* ---------- Brain Status ---------- */

function renderBrainStatus(data) {
  const el = document.getElementById("brain-status");
  if (!el) return;
  if (!data || typeof data.signals_seen === "undefined") {
    el.innerHTML = `<div class="empty">No brain data</div>`;
    return;
  }
  const alive = !!data.brain_alive;
  const aliveCls = alive ? "good" : "bad";
  const aliveText = alive ? "LIVE" : "DEAD";
  const ageSec = data.heartbeat_age_sec || -1;
  const ageText = ageSec >= 0 ? `${ageSec}s ago` : "no heartbeat";
  const enabled = data.controls && data.controls.tb_enabled === "1";
  const enabledCls = enabled ? "good" : "bad";
  const enabledText = enabled ? "ON" : "OFF";
  const lastAt = data.last_signal_at
    ? (data.last_signal_at || "").replace("T", " ").slice(0, 19)
    : "none";
  el.innerHTML = [
    `<div class="item"><span class="label">Process</span><span class="${aliveCls}">${aliveText}</span> <span style="opacity:0.5;font-size:0.85em">(${ageText})</span></div>`,
    `<div class="item"><span class="label">Brain</span><span class="${enabledCls}">${enabledText}</span></div>`,
    `<div class="item"><span class="label">Signals Seen</span><span>${data.signals_seen}</span></div>`,
    `<div class="item"><span class="label">Trades Executed</span><span>${data.trades_executed}</span></div>`,
    `<div class="item"><span class="label">Last Signal</span><span>${lastAt}</span></div>`,
  ].join("");
}

/* ---------- Brain Signals ---------- */

function renderBrainSignals(rows) {
  const el = document.getElementById("brain-signals");
  if (!el) return;
  const nonFiltered = (rows || []).filter((r) => r.action !== "filtered");
  const cntEl = document.getElementById("cnt-signals");
  if (cntEl) cntEl.textContent = nonFiltered.length ? `(${nonFiltered.length})` : "";
  if (!nonFiltered.length) {
    el.innerHTML = `<div class="empty">No brain signals yet &mdash; start trader_brain.py</div>`;
    return;
  }
  const grid = "140px 100px 1fr 50px 55px 60px 55px 80px 90px";
  const head = `<div class="row header" style="grid-template-columns:${grid}"><div>Time</div><div>Wallet</div><div>Market</div><div>Side</div><div>Price</div><div>Size</div><div>Conv</div><div>Action</div><div>Order</div></div>`;
  const body = nonFiltered.slice(0, 50).map((r) => {
    const t = (r.detected_at || "").replace("T", " ").slice(0, 16);
    const wallet = (r.wallet_address || "").slice(0, 10) + "...";
    const market = (r.condition_id || "").slice(0, 12) + "...";
    const actionCls = r.action === "executed" || r.action === "filled" ? "good" : r.action === "skipped" ? "bad" : "";
    const orderId = r.order_id ? r.order_id.slice(0, 8) + "..." : "-";
    return `<div class="row" style="grid-template-columns:${grid}"><div>${t}</div><div title="${r.wallet_address || ""}">${wallet}</div><div title="${r.condition_id || ""}">${market}</div><div>${r.side || ""}</div><div>${Number(r.price || 0).toFixed(2)}</div><div>${fmtUsd(r.size_usdc)}</div><div>${r.convergence_count || 0}</div><div class="${actionCls}">${r.action || ""}</div><div title="${r.order_id || ""}">${orderId}</div></div>`;
  }).join("");
  el.innerHTML = head + body;
}

/* ---------- Filtered Signals ---------- */

function renderFilteredSignals(rows) {
  const el = document.getElementById("brain-filtered");
  if (!el) return;
  const filtered = (rows || []).filter((r) => r.action === "filtered");
  const cntEl = document.getElementById("cnt-filtered");
  if (cntEl) cntEl.textContent = filtered.length ? `(${filtered.length})` : "";
  if (!filtered.length) {
    el.innerHTML = `<div class="empty">No filtered signals yet</div>`;
    return;
  }
  const grid = "140px 100px 1fr 55px 60px 55px 55px 1fr";
  const head = `<div class="row header" style="grid-template-columns:${grid}"><div>Time</div><div>Wallet</div><div>Market</div><div>Price</div><div>Size</div><div>WR</div><div>PnL</div><div>Reason</div></div>`;
  const body = filtered.slice(0, 100).map((r) => {
    const t = (r.detected_at || "").replace("T", " ").slice(0, 16);
    const wallet = (r.wallet_address || "").slice(0, 10) + "...";
    const market = (r.condition_id || "").slice(0, 12) + "...";
    const wr = r.wallet_win_rate > 0 ? (r.wallet_win_rate * 100).toFixed(0) + "%" : "-";
    const pnl = r.wallet_pnl > 0 ? fmtUsd(r.wallet_pnl) : "-";
    return `<div class="row" style="grid-template-columns:${grid}"><div>${t}</div><div title="${r.wallet_address || ""}">${wallet}</div><div title="${r.condition_id || ""}">${market}</div><div>${Number(r.price || 0).toFixed(2)}</div><div>${fmtUsd(r.size_usdc)}</div><div>${wr}</div><div>${pnl}</div><div>${r.notes || ""}</div></div>`;
  }).join("");
  el.innerHTML = head + body;
}

/* ---------- Brain Controls ---------- */

function renderBrainControls(rawControls) {
  if (!rawControls) return;
  const controls = {};
  if (Array.isArray(rawControls)) {
    for (const r of rawControls) controls[r.key] = r.value;
  } else {
    Object.assign(controls, rawControls);
  }
  const set = (id, key, fallback) => {
    const el = document.getElementById(id);
    if (!el) return;
    if (controls[key] !== undefined) el.value = controls[key];
    else if (fallback !== undefined) el.value = fallback;
  };
  const chk = (id, key, fallback) => {
    const el = document.getElementById(id);
    if (!el) return;
    if (controls[key] !== undefined) el.checked = controls[key] === "1";
    else if (fallback !== undefined) el.checked = fallback;
  };
  chk("ctl-tb-enabled", "tb_enabled");
  set("ctl-tb-min-trade", "tb_min_trade_usdc");
  set("ctl-tb-win-rate", "tb_min_wallet_win_rate");
  set("ctl-tb-min-trades", "tb_min_wallet_trades");
  set("ctl-tb-min-pnl", "tb_min_wallet_pnl");
  set("ctl-tb-convergence", "tb_convergence_min");
  set("ctl-tb-conv-window", "tb_convergence_window_hours");
  set("ctl-tb-kelly", "tb_kelly_fraction");
  set("ctl-tb-max-notional", "tb_max_notional_per_trade");
  set("ctl-tb-daily", "tb_max_daily_exposure");
  set("ctl-tb-max-open", "tb_max_open_positions");
  chk("ctl-tb-notify-signal", "tb_notify_on_signal");
  chk("ctl-tb-notify-exec", "tb_notify_on_execute");
  chk("ctl-tb-grok", "tb_grok_enabled", true);
  set("ctl-tb-grok-min", "tb_grok_min_score", "70");
  set("ctl-tb-grok-block", "tb_grok_block_below", "30");
  set("ctl-tb-grok-boost", "tb_grok_conviction_boost", "1.3");
  chk("ctl-tb-grok-alpha", "tb_grok_alpha_enabled", true);
  set("ctl-tb-grok-alpha-bet", "tb_grok_alpha_bet_usd", "15");
  set("ctl-tb-grok-alpha-edge", "tb_grok_alpha_min_edge_pct", "20");
}

function wireBrainControls() {
  const btn = document.getElementById("btn-brain-save");
  if (!btn || btn.dataset.wired) return;
  btn.dataset.wired = "1";
  btn.addEventListener("click", async () => {
    const status = document.getElementById("brain-control-status");
    const val = (id) => String(document.getElementById(id)?.value || "");
    const chk = (id) => document.getElementById(id)?.checked ? "1" : "0";
    try {
      await postJson("/api/risk-controls", {
        updates: {
          tb_enabled: chk("ctl-tb-enabled"),
          tb_min_trade_usdc: val("ctl-tb-min-trade"),
          tb_min_wallet_win_rate: val("ctl-tb-win-rate"),
          tb_min_wallet_trades: val("ctl-tb-min-trades"),
          tb_min_wallet_pnl: val("ctl-tb-min-pnl"),
          tb_convergence_min: val("ctl-tb-convergence"),
          tb_convergence_window_hours: val("ctl-tb-conv-window"),
          tb_kelly_fraction: val("ctl-tb-kelly"),
          tb_max_notional_per_trade: val("ctl-tb-max-notional"),
          tb_max_daily_exposure: val("ctl-tb-daily"),
          tb_max_open_positions: val("ctl-tb-max-open"),
          tb_notify_on_signal: chk("ctl-tb-notify-signal"),
          tb_notify_on_execute: chk("ctl-tb-notify-exec"),
          tb_grok_enabled: chk("ctl-tb-grok"),
          tb_grok_min_score: val("ctl-tb-grok-min"),
          tb_grok_block_below: val("ctl-tb-grok-block"),
          tb_grok_conviction_boost: val("ctl-tb-grok-boost"),
          tb_grok_alpha_enabled: chk("ctl-tb-grok-alpha"),
          tb_grok_alpha_bet_usd: val("ctl-tb-grok-alpha-bet"),
          tb_grok_alpha_min_edge_pct: val("ctl-tb-grok-alpha-edge"),
        },
      });
      if (status) { status.textContent = "Saved"; status.className = "control-warning good"; }
      await boot();
    } catch (err) {
      if (status) { status.textContent = "Save failed"; status.className = "control-warning bad"; }
    }
  });
}

/* ---------- Arb Overview ---------- */

function renderArbOverview(data) {
  const el = document.getElementById("arb-overview");
  if (!el) return;
  if (!data || typeof data.total_scanned === "undefined") {
    el.innerHTML = `<div class="empty">No arb data</div>`;
    return;
  }
  const enabledCls = data.arb_enabled ? "good" : "bad";
  const enabledText = data.arb_enabled ? "ON" : "OFF";
  el.innerHTML = [
    `<div class="item"><span class="label">Scanner</span><span class="${enabledCls}">${enabledText}</span></div>`,
    `<div class="item"><span class="label">Pairs Scanned (7d)</span><span>${data.total_scanned || 0}</span></div>`,
    `<div class="item"><span class="label">Executed</span><span>${data.executed || 0}</span></div>`,
    `<div class="item"><span class="label">Partial (unhedged)</span><span>${data.partial || 0}</span></div>`,
    `<div class="item"><span class="label">Avg Spread (net)</span><span>${Number(data.avg_spread || 0).toFixed(4)}</span></div>`,
    `<div class="item"><span class="label">Total Notional</span><span>${fmtUsd(data.total_notional || 0)}</span></div>`,
    `<div class="item"><span class="label">Min Spread Threshold</span><span>${data.min_spread_pct || 5}%</span></div>`,
    `<div class="item"><span class="label">Max Per Leg</span><span>${fmtUsd(data.max_per_leg || 25)}</span></div>`,
  ].join("");
  const arbEnabled = document.getElementById("ctl-arb-enabled");
  const arbSpread = document.getElementById("ctl-arb-spread");
  const arbLeg = document.getElementById("ctl-arb-leg");
  if (arbEnabled) arbEnabled.checked = !!data.arb_enabled;
  if (arbSpread) arbSpread.value = data.min_spread_pct || 5;
  if (arbLeg) arbLeg.value = data.max_per_leg || 25;
}

/* ---------- Arb Opportunities ---------- */

function renderArbOpportunities(rows) {
  const el = document.getElementById("arb-opportunities");
  if (!el) return;
  const cntEl = document.getElementById("cnt-arb");
  if (cntEl) cntEl.textContent = (rows || []).length ? `(${rows.length})` : "";
  if (!rows || rows.length === 0) {
    el.innerHTML = `<div class="empty">No arb opportunities detected yet</div>`;
    return;
  }
  const grid = "150px 100px 1fr 70px 70px 70px 80px 80px 90px";
  const head = `<div class="row header" style="grid-template-columns:${grid}"><div>Time</div><div>Kalshi</div><div>Title</div><div>Sim%</div><div>P.Price</div><div>K.Price</div><div>Net</div><div>Action</div><div>Leg $</div></div>`;
  const body = rows.slice(0, 50).map((r) => {
    const t = (r.detected_at || "").replace("T", " ").slice(0, 16);
    const actionCls = r.action === "executed" ? "good" : (r.action === "partial" ? "bad" : "");
    const legUsd = (r.action === "executed" || r.action === "partial")
      ? fmtUsd((r.poly_size_usd || 0) + (r.kalshi_size_usd || 0))
      : "-";
    return `<div class="row" style="grid-template-columns:${grid}"><div>${t}</div><div>${r.kalshi_ticker || ""}</div><div title="${r.title || ""}">${(r.title || "").slice(0, 40)}</div><div>${r.similarity || 0}</div><div>${Number(r.poly_price || 0).toFixed(2)}</div><div>${Number(r.kalshi_price || 0).toFixed(2)}</div><div>${Number(r.spread_after_fees || 0).toFixed(3)}</div><div class="${actionCls}">${r.action || ""}</div><div>${legUsd}</div></div>`;
  }).join("");
  el.innerHTML = head + body;
}

/* ---------- Arb Actions ---------- */

function wireArbActions() {
  const btn = document.getElementById("btn-arb-save");
  if (!btn || btn.dataset.wired) return;
  btn.dataset.wired = "1";
  btn.addEventListener("click", async () => {
    const status = document.getElementById("arb-control-status");
    try {
      await postJson("/api/risk-controls", {
        updates: {
          tb_arb_enabled: document.getElementById("ctl-arb-enabled")?.checked ? "1" : "0",
          tb_arb_min_spread_pct: String(document.getElementById("ctl-arb-spread")?.value || "5.0"),
          tb_arb_max_per_leg: String(document.getElementById("ctl-arb-leg")?.value || "25"),
        },
      });
      if (status) { status.textContent = "Saved arb settings"; status.className = "control-warning good"; }
      await boot();
    } catch (err) {
      if (status) { status.textContent = "Save failed"; status.className = "control-warning bad"; }
    }
  });
}

/* ---------- Grok Alpha Bets ---------- */

function renderGrokAlpha(rows) {
  const el = document.getElementById("grok-alpha");
  if (!el) return;
  const cntEl = document.getElementById("cnt-grok-alpha");
  if (cntEl) cntEl.textContent = (rows || []).length ? `(${rows.length})` : "";
  if (!rows || rows.length === 0) {
    el.innerHTML = `<div class="empty">No Grok alpha bets yet &mdash; scanner runs every 10 min</div>`;
    return;
  }
  const grid = "140px 1fr 55px 55px 55px 55px 70px 1fr";
  const head = `<div class="row header" style="grid-template-columns:${grid}"><div>Time</div><div>Market</div><div>Mkt%</div><div>Grok%</div><div>Edge</div><div>Dir</div><div>Status</div><div>News</div></div>`;
  const body = rows.slice(0, 50).map((r) => {
    const t = (r.detected_at || "").replace("T", " ").slice(0, 16);
    const question = (r.question || "").slice(0, 40);
    const mktPct = (Number(r.market_price || 0) * 100).toFixed(0);
    const grokPct = Number(r.grok_confidence || 0);
    const edge = Number(r.edge_pct || 0).toFixed(0);
    const statusCls = r.status === "executed" ? "good" : r.status === "failed" ? "bad" : "";
    const news = (r.news_summary || "").slice(0, 80);
    return `<div class="row" style="grid-template-columns:${grid}"><div>${t}</div><div title="${r.question || ""}">${question}</div><div>${mktPct}%</div><div>${grokPct}%</div><div>${edge}%</div><div>${r.direction || ""}</div><div class="${statusCls}">${r.status || ""}</div><div title="${r.news_summary || ""}">${news}</div></div>`;
  }).join("");
  el.innerHTML = head + body;
}

/* ---------- Grok Scores ---------- */

function renderGrokScores(rows) {
  const el = document.getElementById("grok-scores");
  if (!el) return;
  const cntEl = document.getElementById("cnt-grok-scores");
  if (cntEl) cntEl.textContent = (rows || []).length ? `(${rows.length})` : "";
  if (!rows || rows.length === 0) {
    el.innerHTML = `<div class="empty">No Grok scores yet &mdash; scanner runs every 5 min</div>`;
    return;
  }
  const grid = "140px 1fr 60px 60px 60px 50px 1fr";
  const head = `<div class="row header" style="grid-template-columns:${grid}"><div>Time</div><div>Market</div><div>Price</div><div>Score</div><div>Dir</div><div>Posts</div><div>Rationale</div></div>`;
  const body = rows.slice(0, 50).map((r) => {
    const t = (r.scored_at || "").replace("T", " ").slice(0, 16);
    const score = Number(r.grok_score || 0);
    const scoreCls = score >= 70 ? "good" : score < 30 ? "bad" : "";
    const question = (r.question || "").slice(0, 50);
    return `<div class="row" style="grid-template-columns:${grid}"><div>${t}</div><div title="${r.question || ""}">${question}</div><div>${Number(r.current_price || 0).toFixed(2)}</div><div class="${scoreCls}">${score}</div><div>${r.grok_direction || ""}</div><div>${r.x_post_count || 0}</div><div>${(r.rationale || "").slice(0, 80)}</div></div>`;
  }).join("");
  el.innerHTML = head + body;
}

/* ---------- Boot ---------- */

async function boot() {
  try {
    setStatus("loading");
    const [brainStatus, brainSignals, arbOverview, arbOpportunities, riskControls, grokScores, grokAlpha, polyOverview, portfolioSnapshot] = await Promise.all([
      fetchJsonSafe("/api/brain-status", {}),
      fetchJsonSafe("/api/brain-signals?limit=500", []),
      fetchJsonSafe("/api/arb-overview", {}),
      fetchJsonSafe("/api/arb-opportunities", []),
      fetchJsonSafe("/api/risk-controls", {}),
      fetchJsonSafe("/api/grok-scores", []),
      fetchJsonSafe("/api/grok-alpha", []),
      fetchJsonSafe("/api/polymarket-overview", {}),
      fetchJsonSafe("/api/portfolio-snapshot", {}),
    ]);

    runUiStep("polyOverview", () => renderPolyOverview(polyOverview, portfolioSnapshot));
    runUiStep("polyPositions", () => renderPolyPositions(portfolioSnapshot));
    runUiStep("brainStatus", () => renderBrainStatus(brainStatus));
    runUiStep("brainSignals", () => renderBrainSignals(brainSignals));
    runUiStep("filteredSignals", () => renderFilteredSignals(brainSignals));
    runUiStep("grokAlpha", () => renderGrokAlpha(grokAlpha));
    runUiStep("grokScores", () => renderGrokScores(grokScores));
    runUiStep("arbOverview", () => renderArbOverview(arbOverview));
    runUiStep("arbOpportunities", () => renderArbOpportunities(arbOpportunities));
    runUiStep("brainControls", () => renderBrainControls(riskControls));
    runUiStep("wireBrainControls", () => wireBrainControls());
    runUiStep("wireArbActions", () => wireArbActions());

    const alive = brainStatus && brainStatus.brain_alive;
    setStatus(alive ? "brain live" : "brain offline", alive ? "good" : "bad");
  } catch (err) {
    setStatus("error", "bad");
  }
}

document.addEventListener("DOMContentLoaded", boot);
setInterval(boot, 30_000);
