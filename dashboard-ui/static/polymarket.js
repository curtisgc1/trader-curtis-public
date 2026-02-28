async function fetchJson(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${url} failed: ${res.status}`);
  return res.json();
}

const UI_BUILD = "20260228a";

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

function normalizeXHandle(value) {
  const raw = String(value || "").trim();
  if (!raw) return "";
  const token = raw.split(/[?#\s]/, 1)[0].trim();
  if (!token) return "";

  let candidate = token;
  let urlText = token;
  if (/^(?:www\.)?(?:x\.com|twitter\.com)\//i.test(token)) {
    urlText = `https://${token.replace(/^\/+/, "")}`;
  }
  try {
    const u = new URL(urlText);
    const host = String(u.hostname || "").toLowerCase().replace(/^www\./, "");
    if (host === "x.com" || host === "twitter.com") {
      candidate = String(u.pathname || "").replace(/^\/+/, "").split("/", 1)[0] || "";
    }
  } catch (_) {
    // Keep raw token fallback for plain handles.
  }

  return candidate.replace(/^@+/, "").replace(/[^A-Za-z0-9_]/g, "").toLowerCase();
}

function resolveHandleInput(preferredIds, btnId) {
  const direct = (preferredIds || [])
    .map((id) => document.getElementById(id))
    .filter(Boolean)
    .map((el) => String(el.value || "").trim())
    .find((v) => !!v);
  if (direct) return direct;

  const btn = document.getElementById(btnId || "");
  const scope = btn?.closest(".card") || document;
  const fields = Array.from(scope.querySelectorAll("input[type='text'],input[type='url'],input:not([type])"));
  const handleLike = fields.filter((el) => {
    const meta = `${el.id || ""} ${el.name || ""} ${el.placeholder || ""} ${el.getAttribute("aria-label") || ""}`.toLowerCase();
    return /handle|x\.com|twitter|@/.test(meta);
  });
  const scoped = handleLike
    .map((el) => String(el.value || "").trim())
    .find((v) => !!v);
  if (scoped) return scoped;

  const active = document.activeElement;
  if (active && active.tagName === "INPUT") {
    const t = String(active.type || "").toLowerCase();
    if (!t || t === "text" || t === "url") {
      const v = String(active.value || "").trim();
      if (v) return v;
    }
  }

  const anyTextValues = fields
    .map((el) => String(el.value || "").trim())
    .filter((v) => !!v);
  if (anyTextValues.length === 1) return anyTextValues[0];
  return "";
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

function setControlStatus(msg, cls = "warn") {
  const el = document.getElementById("poly-control-status");
  if (!el) return;
  el.textContent = msg || "";
  el.className = `control-warning ${cls}`;
}

function setSourceStatus(msg, cls = "warn") {
  const el = document.getElementById("source-status");
  if (!el) return;
  el.textContent = msg || "";
  el.className = `control-warning ${cls}`;
}

function setPolyWalletStatus(msg, cls = "warn") {
  const el = document.getElementById("polyw-status");
  if (!el) return;
  el.textContent = msg || "";
  el.className = `control-warning ${cls}`;
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

function renderOverview(overview) {
  const el = document.getElementById("polymarket-overview");
  if (!el) return;
  const mode = overview.live_enabled ? "LIVE REAL MONEY" : "PAPER";
  const modeClass = overview.live_enabled ? "bad" : "good";
  const exposurePct = overview.daily_cap_usd > 0 ? Math.min(100, Math.round((overview.daily_used_usd / overview.daily_cap_usd) * 100)) : 0;

  el.innerHTML = [
    `<div class="item"><span class="label">Execution Mode</span><span class="${modeClass}">${mode}</span></div>`,
    `<div class="item"><span class="label">Auto Execution</span><span>${overview.auto_enabled ? "enabled" : "disabled"}</span></div>`,
    `<div class="item"><span class="label">Daily Exposure (${overview.live_enabled ? "live" : "paper"})</span><span>${fmtUsd(overview.daily_used_usd)} / ${fmtUsd(overview.daily_cap_usd)} (${exposurePct}%)</span></div>`,
    `<div class="item"><span class="label">Live Used Today</span><span>${fmtUsd(overview.live_used_usd || 0)}</span></div>`,
    `<div class="item"><span class="label">Paper Used Today</span><span>${fmtUsd(overview.paper_used_usd || 0)}</span></div>`,
    `<div class="item"><span class="label">Pending Approval</span><span>${overview.pending_approval || 0}</span></div>`,
    `<div class="item"><span class="label">Live Submitted / Filled</span><span>${overview.submitted_live || 0} / ${overview.filled_live || 0}</span></div>`,
    `<div class="item"><span class="label">Paper Submitted</span><span>${overview.submitted_paper || 0}</span></div>`,
    `<div class="item"><span class="label">Blocked / Failed</span><span>${overview.blocked || 0} / ${overview.failed || 0}</span></div>`,
    `<div class="item"><span class="label">Manual Approval</span><span>${overview.manual_approval ? "required" : "off"} (${overview.approval_count || 0}/${overview.approval_threshold || 0})</span></div>`,
  ].join("");
}

function renderMmOverview(mm) {
  const el = document.getElementById("polymarket-mm-overview");
  if (!el) return;
  if (!mm) {
    el.innerHTML = `<div class="empty">No MM data</div>`;
    return;
  }
  const state = String(mm.state || "offline");
  const stateCls = state === "good" ? "good" : (state === "caution" || state === "standby" ? "warn" : "bad");
  el.innerHTML = [
    `<div class="item"><span class="label">State</span><span class="${stateCls}">${state.toUpperCase()}</span></div>`,
    `<div class="item"><span class="label">MM Enabled</span><span>${mm.mm_enabled ? "ON" : "OFF"}</span></div>`,
    `<div class="item"><span class="label">Execution Ready</span><span>${mm.ready_count || 0} / ${mm.snapshot_count || 0}</span></div>`,
    `<div class="item"><span class="label">Avg Toxicity</span><span>${Number(mm.avg_toxicity || 0).toFixed(3)}</span></div>`,
    `<div class="item"><span class="label">Source Accuracy (hist)</span><span>${Number(mm.avg_source_accuracy || 0).toFixed(1)}%</span></div>`,
    `<div class="item"><span class="label">Poly Exec Accuracy (30d)</span><span>${Number(mm.poly_exec_accuracy_30d || 0).toFixed(1)}%</span></div>`,
    `<div class="item"><span class="label">Poly Signal Accuracy (30d)</span><span>${Number(mm.poly_signal_accuracy_30d || 0).toFixed(1)}%</span></div>`,
    `<div class="item"><span class="label">Avg Edge (bps)</span><span>${Number(mm.avg_edge_bps || 0).toFixed(1)}</span></div>`,
  ].join("");
}

function renderPreTradeControls(controls) {
  const byKey = {};
  (controls || []).forEach((r) => { byKey[r.key] = String(r.value || ""); });
  const master = document.getElementById("ctl-master");
  const live = document.getElementById("ctl-poly-live");
  const auto = document.getElementById("ctl-poly-auto");
  const manual = document.getElementById("ctl-poly-manual");
  const consensus = document.getElementById("ctl-consensus");
  const max = document.getElementById("ctl-poly-max");
  const daily = document.getElementById("ctl-poly-daily");
  const edge = document.getElementById("ctl-poly-edge");
  const feeGate = document.getElementById("ctl-poly-fee-gate");
  const feePct = document.getElementById("ctl-poly-fee");
  const feeBuf = document.getElementById("ctl-poly-fee-buf");
  const cMin = document.getElementById("ctl-c-min");
  const cRatio = document.getElementById("ctl-c-ratio");
  const cScore = document.getElementById("ctl-c-score");
  const mmEnabled = document.getElementById("ctl-mm-enabled");
  const mmRisk = document.getElementById("ctl-mm-risk");
  const mmSpread = document.getElementById("ctl-mm-spread");
  const mmInv = document.getElementById("ctl-mm-inv");
  const mmTox = document.getElementById("ctl-mm-tox");
  const mmEdge = document.getElementById("ctl-mm-edge");
  const xInfluence = document.getElementById("ctl-x-influence");
  const inputReweight = document.getElementById("ctl-input-reweight");
  const inputMinSamples = document.getElementById("ctl-input-min-samples");
  const inputFloor = document.getElementById("ctl-input-floor");
  const inputCeil = document.getElementById("ctl-input-ceil");
  const inputDisableThreshold = document.getElementById("ctl-input-disable-threshold");
  if (master) master.checked = (byKey.agent_master_enabled || "0") === "1";
  if (live) live.checked = ["1","true","yes","on","enabled","live"].includes((byKey.allow_polymarket_live || "0").toLowerCase());
  if (auto) auto.checked = (byKey.enable_polymarket_auto || "0") === "1";
  if (manual) manual.checked = (byKey.polymarket_manual_approval || "1") === "1";
  if (consensus) consensus.checked = (byKey.consensus_enforce || "1") === "1";
  if (max) max.value = byKey.polymarket_max_notional_usd || "10";
  if (daily) daily.value = byKey.polymarket_max_daily_exposure || "20";
  if (edge) edge.value = byKey.polymarket_min_edge_pct || "5";
  if (feeGate) feeGate.checked = (byKey.polymarket_fee_gate_enabled || "1") === "1";
  if (feePct) feePct.value = byKey.polymarket_taker_fee_pct || "3.15";
  if (feeBuf) feeBuf.value = byKey.polymarket_fee_buffer_pct || "0.50";
  if (cMin) cMin.value = byKey.consensus_min_confirmations || "3";
  if (cRatio) cRatio.value = byKey.consensus_min_ratio || "0.6";
  if (cScore) cScore.value = byKey.consensus_min_score || "60";
  if (mmEnabled) mmEnabled.checked = (byKey.mm_enabled || "0") === "1";
  if (mmRisk) mmRisk.value = byKey.mm_risk_aversion || "0.25";
  if (mmSpread) mmSpread.value = byKey.mm_base_spread_bps || "80";
  if (mmInv) mmInv.value = byKey.mm_inventory_limit || "200";
  if (mmTox) mmTox.value = byKey.mm_toxicity_threshold || "0.72";
  if (mmEdge) mmEdge.value = byKey.mm_min_edge_bps || "50";
  if (xInfluence) xInfluence.checked = (byKey.x_influence_enabled || "1") === "1";
  if (inputReweight) inputReweight.checked = (byKey.input_auto_reweight_enabled || "1") === "1";
  if (inputMinSamples) inputMinSamples.value = byKey.input_weight_min_samples || "5";
  if (inputFloor) inputFloor.value = byKey.input_weight_floor || "0.6";
  if (inputCeil) inputCeil.value = byKey.input_weight_ceiling || "1.6";
  if (inputDisableThreshold) inputDisableThreshold.value = byKey.input_auto_disable_threshold || "0.0";
}

function wirePreTradeActions() {
  const saveBtn = document.getElementById("btn-poly-save");
  if (saveBtn && !saveBtn.dataset.wired) {
    saveBtn.dataset.wired = "1";
    saveBtn.addEventListener("click", async () => {
      try {
        const payload = {
          updates: {
            agent_master_enabled: document.getElementById("ctl-master")?.checked ? "1" : "0",
            allow_polymarket_live: document.getElementById("ctl-poly-live")?.checked ? "1" : "0",
            enable_polymarket_auto: document.getElementById("ctl-poly-auto")?.checked ? "1" : "0",
            polymarket_manual_approval: document.getElementById("ctl-poly-manual")?.checked ? "1" : "0",
            consensus_enforce: document.getElementById("ctl-consensus")?.checked ? "1" : "0",
            consensus_min_confirmations: String(document.getElementById("ctl-c-min")?.value || "3"),
            consensus_min_ratio: String(document.getElementById("ctl-c-ratio")?.value || "0.6"),
            consensus_min_score: String(document.getElementById("ctl-c-score")?.value || "60"),
            polymarket_max_notional_usd: String(document.getElementById("ctl-poly-max")?.value || "10"),
            polymarket_max_daily_exposure: String(document.getElementById("ctl-poly-daily")?.value || "20"),
            polymarket_min_edge_pct: String(document.getElementById("ctl-poly-edge")?.value || "5"),
            polymarket_fee_gate_enabled: document.getElementById("ctl-poly-fee-gate")?.checked ? "1" : "0",
            polymarket_taker_fee_pct: String(document.getElementById("ctl-poly-fee")?.value || "3.15"),
            polymarket_fee_buffer_pct: String(document.getElementById("ctl-poly-fee-buf")?.value || "0.50"),
            mm_enabled: document.getElementById("ctl-mm-enabled")?.checked ? "1" : "0",
            mm_risk_aversion: String(document.getElementById("ctl-mm-risk")?.value || "0.25"),
            mm_base_spread_bps: String(document.getElementById("ctl-mm-spread")?.value || "80"),
            mm_inventory_limit: String(document.getElementById("ctl-mm-inv")?.value || "200"),
            mm_toxicity_threshold: String(document.getElementById("ctl-mm-tox")?.value || "0.72"),
            mm_min_edge_bps: String(document.getElementById("ctl-mm-edge")?.value || "50"),
            x_influence_enabled: document.getElementById("ctl-x-influence")?.checked ? "1" : "0",
            input_auto_reweight_enabled: document.getElementById("ctl-input-reweight")?.checked ? "1" : "0",
            input_weight_min_samples: String(document.getElementById("ctl-input-min-samples")?.value || "5"),
            input_weight_floor: String(document.getElementById("ctl-input-floor")?.value || "0.6"),
            input_weight_ceiling: String(document.getElementById("ctl-input-ceil")?.value || "1.6"),
            input_auto_disable_threshold: String(document.getElementById("ctl-input-disable-threshold")?.value || "0.0"),
          },
        };
        const out = await postJson("/api/risk-controls", payload);
        if (!out || typeof out.updated !== "number") throw new Error("failed to save controls");
        setControlStatus("Saved pre-trade controls", "good");
        await boot();
      } catch (err) {
        console.error(err);
        setControlStatus("Save failed", "bad");
      }
    });
  }

  const execBtn = document.getElementById("btn-poly-exec");
  if (execBtn && !execBtn.dataset.wired) {
    execBtn.dataset.wired = "1";
    execBtn.addEventListener("click", async () => {
      try {
        await postJson("/api/actions", { action: "run_polymarket_exec" });
        setControlStatus("Execution triggered", "good");
        setTimeout(() => { boot(); }, 1500);
      } catch (err) {
        console.error(err);
        setControlStatus("Execution trigger failed", "bad");
      }
    });
  }

  const mmBtn = document.getElementById("btn-poly-mm");
  if (mmBtn && !mmBtn.dataset.wired) {
    mmBtn.dataset.wired = "1";
    mmBtn.addEventListener("click", async () => {
      try {
        await postJson("/api/actions", { action: "run_polymarket_mm" });
        setControlStatus("MM refresh triggered", "good");
        setTimeout(() => { boot(); }, 1200);
      } catch (err) {
        console.error(err);
        setControlStatus("MM refresh failed", "bad");
      }
    });
  }
}

function renderTrustPanel(panel) {
  const el = document.getElementById("trust-panel");
  if (!el) return;
  if (!panel) {
    el.innerHTML = `<div class="empty">No trust data</div>`;
    return;
  }
  const stateCls = panel.state === "good" ? "good" : (panel.state === "warn" ? "warn" : "bad");
  const thresholds = panel.consensus_thresholds || {};
  const lines = [
    `<div class="item"><span class="label">State</span><span class="${stateCls}">${String(panel.state || "unknown").toUpperCase()}</span></div>`,
    `<div class="item"><span class="label">Master Switch</span><span>${panel.master_enabled ? "ON" : "OFF"}</span></div>`,
    `<div class="item"><span class="label">Consensus Gate</span><span>${panel.consensus_enforce ? "ENFORCED" : "OFF"}</span></div>`,
    `<div class="item"><span class="label">Thresholds</span><span>${thresholds.min_confirmations || 0} / ${thresholds.min_ratio || 0} / ${thresholds.min_score || 0}</span></div>`,
    `<div class="item"><span class="label">Flagged Candidates</span><span>${panel.candidates_flagged || 0} / ${panel.candidates_total || 0}</span></div>`,
  ];
  const top = (panel.top_sources || []).slice(0, 4).map((s) => `${s.source} (${s.samples} | ${s.win_rate}%)`).join(" • ");
  lines.push(`<div class="item"><span class="label">Top Sources</span><span>${top || "n/a"}</span></div>`);
  el.innerHTML = lines.join("");
}

function renderPolymarketScorecard(data) {
  const el = document.getElementById("polymarket-scorecard");
  if (!el) return;
  if (!data || !data.ok) {
    el.innerHTML = `<div class="empty">No scorecard data</div>`;
    return;
  }

  let html = "";

  // Strategy performance table
  const strats = data.strategies || [];
  if (strats.length > 0) {
    const grid = "140px 80px 80px 80px 90px 100px";
    html += `<div class="row header" style="grid-template-columns:${grid}"><div>Strategy</div><div>Orders</div><div>Fills</div><div>Fails</div><div>Fill%</div><div>Total $</div></div>`;
    strats.forEach((s) => {
      const fillCls = s.fill_rate >= 70 ? "good" : (s.fill_rate >= 40 ? "warn" : "bad");
      html += `<div class="row" style="grid-template-columns:${grid}"><div>${s.strategy}</div><div>${s.total_orders}</div><div>${s.fills}</div><div>${s.fails}</div><div class="${fillCls}">${s.fill_rate}%</div><div>${fmtUsd(s.total_notional)}</div></div>`;
    });
  }

  // Summary items
  html += `<div class="item" style="margin-top:8px"><span class="label">Active Arb Opportunities</span><span>${data.active_arb_opportunities || 0}</span></div>`;
  html += `<div class="item"><span class="label">Avg Edge at Entry (7d)</span><span>${Number(data.avg_edge_at_entry || 0).toFixed(2)}%</span></div>`;

  // Wallet copy performance
  const wallets = data.wallet_copy_performance || [];
  if (wallets.length > 0) {
    html += `<div style="margin-top:8px;font-weight:600;font-size:0.85rem">Wallet Copy Performance</div>`;
    const wGrid = "180px 60px 60px 80px 90px";
    html += `<div class="row header" style="grid-template-columns:${wGrid}"><div>Source</div><div>N</div><div>Fills</div><div>Fill%</div><div>Avg $</div></div>`;
    wallets.slice(0, 10).forEach((w) => {
      html += `<div class="row" style="grid-template-columns:${wGrid}"><div>${w.source_tag}</div><div>${w.total}</div><div>${w.fills}</div><div>${w.fill_rate}%</div><div>${fmtUsd(w.avg_notional)}</div></div>`;
    });
  }

  el.innerHTML = html;
}

function renderPolymarketCandidates(rows) {
  const el = document.getElementById("polymarket-candidates");
  if (!el) return;
  if (!rows || rows.length === 0) {
    el.innerHTML = `<div class="empty">No candidates</div>`;
    return;
  }

  const grid = "120px 1fr 120px 120px 180px 120px 90px";
  const head = `<div class="row header" style="grid-template-columns:${grid}"><div>ID</div><div>Strategy</div><div>Edge %</div><div>Outcome</div><div>Status</div><div>Action</div><div>Market</div></div>`;
  const body = rows.slice(0, 50).map((r) => {
    const link = r.market_url ? `<a href="${r.market_url}" target="_blank" rel="noreferrer">open</a>` : "";
    const st = String(r.status || "new");
    const canApprove = st === "new" || st === "awaiting_approval";
    const action = canApprove ? `<button data-cid="${r.id}" class="approve-btn">approve</button>` : "";
    return `<div class="row" style="grid-template-columns:${grid}"><div>${r.id || ""}</div><div>${r.strategy_id || ""}</div><div>${Number(r.edge || 0).toFixed(2)}</div><div>${r.outcome || ""}</div><div>${st}</div><div>${action}</div><div>${link}</div></div>`;
  }).join("");
  el.innerHTML = head + body;

  el.querySelectorAll(".approve-btn").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const id = Number(btn.getAttribute("data-cid"));
      btn.disabled = true;
      btn.textContent = "approving...";
      try {
        const out = await postJson("/api/polymarket-approve", { ids: [id] });
        if (!out.ok) throw new Error(out.error || "approve failed");
        await boot();
      } catch (err) {
        console.error(err);
        btn.disabled = false;
        btn.textContent = "retry";
      }
    });
  });
}

function renderPolymarketMarkets(rows) {
  const el = document.getElementById("polymarket-markets");
  if (!el) return;
  if (!rows || rows.length === 0) {
    el.innerHTML = `<div class="empty">No data</div>`;
    return;
  }
  const grid = "1fr 140px 140px 80px";
  const head = `<div class="row header" style="grid-template-columns:${grid}"><div>Slug</div><div>Liq</div><div>Vol 24h</div><div>URL</div></div>`;
  const body = rows.slice(0, 30).map((r) => {
    const link = r.market_url ? `<a href="${r.market_url}" target="_blank" rel="noreferrer">open</a>` : "";
    return `<div class="row" style="grid-template-columns:${grid}"><div>${r.slug || ""}</div><div>${r.liquidity || ""}</div><div>${r.volume_24h || ""}</div><div>${link}</div></div>`;
  }).join("");
  el.innerHTML = head + body;
}

function renderPolymarketOrders(rows) {
  const el = document.getElementById("polymarket-orders");
  if (!el) return;
  if (!rows || rows.length === 0) {
    el.innerHTML = `<div class="empty">No order events yet</div>`;
    return;
  }
  const grid = "170px 90px 80px 170px 120px 220px 1fr";
  const head = `<div class="row header" style="grid-template-columns:${grid}"><div>Time</div><div>Candidate</div><div>Money</div><div>Status</div><div>Notional</div><div>Order ID</div><div>Notes</div></div>`;
  const body = rows.slice(0, 60).map((r) => {
    const t = (r.created_at || "").replace("T", " ").slice(0, 19);
    const money = (r.money_type === "real") ? "REAL" : "PAPER";
    const moneyCls = (r.money_type === "real") ? "bad" : "good";
    return `<div class="row" style="grid-template-columns:${grid}"><div>${t}</div><div>${r.candidate_id || ""}</div><div class="${moneyCls}">${money}</div><div>${r.status || ""}</div><div>${fmtUsd(r.notional || 0)}</div><div>${r.order_id || ""}</div><div>${r.notes || ""}</div></div>`;
  }).join("");
  el.innerHTML = head + body;
}

function renderMmSnapshots(rows) {
  const el = document.getElementById("polymarket-mm-snapshots");
  if (!el) return;
  if (!rows || rows.length === 0) {
    el.innerHTML = `<div class="empty">No MM opportunities yet. Run MM refresh after scans.</div>`;
    return;
  }
  const grid = "70px 80px 70px 110px 90px 90px 90px 90px 80px 80px 1fr";
  const head = `<div class="row header" style="grid-template-columns:${grid}"><div>Ticker</div><div>Dir</div><div>N/M</div><div>Market</div><div>Implied</div><div>Fair</div><div>Bid</div><div>Ask</div><div>Edge bps</div><div>State</div><div>History Context</div></div>`;
  const body = rows.slice(0, 40).map((r) => {
    const conf = `${Number(r.confirmations || 0)}/${Number(r.sources_total || 0)}`;
    const link = r.market_url ? `<a href=\"${r.market_url}\" target=\"_blank\" rel=\"noreferrer\">open</a>` : "";
    const state = String(r.state || "");
    const stCls = state === "normal" ? "good" : (state === "caution" ? "warn" : "bad");
    const ready = Number(r.execution_ready || 0) === 1 ? "READY" : "HOLD";
    const readyCls = Number(r.execution_ready || 0) === 1 ? "good" : "warn";
    const hist = `src ${Number(r.source_accuracy || 0).toFixed(1)}% | exec ${Number(r.poly_exec_accuracy || 0).toFixed(1)}% | tox ${Number(r.toxicity || 0).toFixed(2)} | <span class=\"${readyCls}\">${ready}</span>`;
    return `<div class=\"row\" style=\"grid-template-columns:${grid}\"><div>${r.ticker || ""}</div><div>${r.direction || ""}</div><div>${conf}</div><div>${link}</div><div>${Number(r.implied_prob || 0).toFixed(3)}</div><div>${Number(r.fair_prob || 0).toFixed(3)}</div><div>${Number(r.bid_price || 0).toFixed(3)}</div><div>${Number(r.ask_price || 0).toFixed(3)}</div><div>${Number(r.edge_bps || 0).toFixed(1)}</div><div class=\"${stCls}\">${state}</div><div>${hist}</div></div>`;
  }).join("");
  el.innerHTML = head + body;
}

function renderWeatherMarketProbs(rows) {
  const el = document.getElementById("weather-market-probs");
  if (!el) return;
  if (!rows || rows.length === 0) {
    el.innerHTML = `<div class="empty">No active weather temp markets detected right now.</div>`;
    return;
  }
  const grid = "80px 90px 70px 1fr 90px 70px 1fr 70px";
  const head = `<div class="row header" style="grid-template-columns:${grid}"><div>City</div><div>Date</div><div>Models</div><div>Top Outcome Probabilities</div><div>Best</div><div>Unc.</div><div>Resolver</div><div>Market</div></div>`;
  const body = rows.slice(0, 30).map((r) => {
    const link = r.market_url ? `<a href="${r.market_url}" target="_blank" rel="noreferrer">open</a>` : "";
    const unc = Number(r.uncertainty || 0).toFixed(2);
    const resolver = `${r.station_hint || ""} | ${r.source_hint || "src?"} | ${r.rounding_hint || "nearest-int"}`;
    return `<div class="row" style="grid-template-columns:${grid}"><div>${r.city || ""}</div><div>${r.target_date || ""}</div><div>${Number(r.model_count || 0)}</div><div>${r.top_probs || ""}</div><div>${r.best_outcome || ""} (${(Number(r.best_prob || 0) * 100).toFixed(1)}%)</div><div>${unc}</div><div>${resolver}</div><div>${link}</div></div>`;
  }).join("");
  el.innerHTML = head + body;
}

function renderBookmarkAlphaIdeas(rows) {
  const el = document.getElementById("bookmark-alpha-ideas");
  if (!el) return;
  if (!rows || rows.length === 0) {
    el.innerHTML = `<div class="empty">No data</div>`;
    return;
  }
  const grid = "160px 160px 1fr 80px";
  const head = `<div class="row header" style="grid-template-columns:${grid}"><div>Source</div><div>Strategy</div><div>Thesis</div><div>URL</div></div>`;
  const body = rows.slice(0, 30).map((r) => {
    const link = r.source_url ? `<a href="${r.source_url}" target="_blank" rel="noreferrer">open</a>` : "";
    return `<div class="row" style="grid-template-columns:${grid}"><div>${r.source_handle || ""}</div><div>${r.strategy_tag || ""}</div><div>${r.thesis_type || ""}</div><div>${link}</div></div>`;
  }).join("");
  el.innerHTML = head + body;
}

function renderTrackedSources(rows) {
  const el = document.getElementById("tracked-sources");
  if (!el) return;
  if (!rows || rows.length === 0) {
    el.innerHTML = `<div class="empty">No tracked sources yet</div>`;
    return;
  }
  const grid = "140px 60px 60px 60px 60px 80px 1fr";
  const head = `<div class="row header" style="grid-template-columns:${grid}"><div>Handle</div><div>Copy</div><div>Alpha</div><div>X API</div><div>Active</div><div>Weight</div><div>Notes</div></div>`;
  const body = rows.slice(0, 30).map((r) => {
    const h = `@${r.handle || ""}`;
    const c = Number(r.role_copy || 0) === 1 ? "yes" : "no";
    const a = Number(r.role_alpha || 0) === 1 ? "yes" : "no";
    const xApi = Number(r.x_api_enabled || 0) === 1 ? "yes" : "no";
    const active = Number(r.active || 0) === 1 ? "yes" : "no";
    const weight = Number(r.source_weight || 1).toFixed(2);
    return `<div class="row" style="grid-template-columns:${grid}"><div>${h}</div><div>${c}</div><div>${a}</div><div>${xApi}</div><div>${active}</div><div>${weight}</div><div>${r.notes || ""}</div></div>`;
  }).join("");
  el.innerHTML = head + body;
}

function renderInputSources(rows) {
  const el = document.getElementById("input-sources");
  if (!el) return;
  if (!rows || rows.length === 0) {
    el.innerHTML = `<div class="empty">No input sources yet</div>`;
    return;
  }
  const grid = "170px 120px 70px 90px 90px 90px 1fr";
  const head = `<div class="row header" style="grid-template-columns:${grid}"><div>Key</div><div>Class</div><div>On</div><div>Manual</div><div>Auto</div><div>Effective</div><div>Notes</div></div>`;
  const body = rows.slice(0, 120).map((r) => {
    const on = Number(r.enabled || 0) === 1 ? "yes" : "no";
    return `<div class="row" style="grid-template-columns:${grid}"><div>${r.source_key || ""}</div><div>${r.source_class || ""}</div><div>${on}</div><div>${Number(r.manual_weight || 1).toFixed(2)}</div><div>${Number(r.auto_weight || 1).toFixed(2)}</div><div>${Number(r.effective_weight || 1).toFixed(2)}</div><div>${r.notes || ""}</div></div>`;
  }).join("");
  el.innerHTML = head + body;
}

function renderTrackedPolyWallets(rows) {
  const el = document.getElementById("tracked-poly-wallets");
  if (!el) return;
  if (!rows || rows.length === 0) {
    el.innerHTML = `<div class="empty">No tracked wallets yet</div>`;
    return;
  }
  const grid = "130px 70px 70px 70px 1fr";
  const head = `<div class="row header" style="grid-template-columns:${grid}"><div>Handle</div><div>Copy</div><div>Alpha</div><div>Active</div><div>Profile</div></div>`;
  const body = rows.slice(0, 30).map((r) => {
    const h = `@${r.handle || ""}`;
    const c = Number(r.role_copy || 0) === 1 ? "yes" : "no";
    const a = Number(r.role_alpha || 0) === 1 ? "yes" : "no";
    const active = Number(r.active || 0) === 1 ? "yes" : "no";
    const profile = r.profile_url ? `<a href="${r.profile_url}" target="_blank" rel="noreferrer">open</a>` : "";
    return `<div class="row" style="grid-template-columns:${grid}"><div>${h}</div><div>${c}</div><div>${a}</div><div>${active}</div><div>${profile}</div></div>`;
  }).join("");
  el.innerHTML = head + body;
}

function renderPolyWalletScores(rows) {
  const el = document.getElementById("poly-wallet-scores");
  if (!el) return;
  if (!rows || rows.length === 0) {
    el.innerHTML = `<div class="empty">No wallet score data yet</div>`;
    return;
  }
  const grid = "140px 80px 80px 90px 90px 100px 80px";
  const head = `<div class="row header" style="grid-template-columns:${grid}"><div>Handle</div><div>Samples</div><div>Win%</div><div>Avg PnL%</div><div>Reliability</div><div>Profile</div><div>Active</div></div>`;
  const body = rows.slice(0, 40).map((r) => {
    const p = r.profile_url ? `<a href="${r.profile_url}" target="_blank" rel="noreferrer">open</a>` : "";
    return `<div class="row" style="grid-template-columns:${grid}"><div>@${r.handle || ""}</div><div>${Number(r.sample_size || 0)}</div><div>${Number(r.win_rate || 0).toFixed(1)}</div><div>${Number(r.avg_pnl_pct || 0).toFixed(2)}</div><div>${Number(r.reliability_score || 0).toFixed(1)}</div><div>${p}</div><div>${Number(r.active || 0) === 1 ? "yes" : "no"}</div></div>`;
  }).join("");
  el.innerHTML = head + body;
}

function wireSourceActions() {
  const btn = document.getElementById("btn-source-save");
  if (!btn || btn.dataset.wired) return;
  btn.dataset.wired = "1";
  btn.addEventListener("click", async () => {
    const rawHandle = resolveHandleInput(["src-handle", "x-handle", "polyw-handle"], "btn-source-save");
    const handle = normalizeXHandle(rawHandle);
    if (!rawHandle) {
      setSourceStatus(`Handle is required (example: @NoLimitGains or x.com/NoLimitGains) [build ${UI_BUILD}]`, "bad");
      console.error("source handle missing at submit", {
        build: UI_BUILD,
        srcHandle: document.getElementById("src-handle")?.value || "",
        xHandle: document.getElementById("x-handle")?.value || "",
        polywHandle: document.getElementById("polyw-handle")?.value || "",
      });
      return;
    }
    try {
      const payload = {
        handle: handle || rawHandle,
        x_handle: rawHandle,
        role_copy: !!document.getElementById("src-copy")?.checked,
        role_alpha: !!document.getElementById("src-alpha")?.checked,
        active: !!document.getElementById("src-active")?.checked,
        x_api_enabled: !!document.getElementById("src-x-api")?.checked,
        source_weight: Number(document.getElementById("src-weight")?.value || "1.0"),
        notes: (document.getElementById("src-notes")?.value || "").trim(),
      };
      const out = await postJson("/api/tracked-sources", payload);
      if (!out.ok) throw new Error(out.error || "failed");
      setSourceStatus(`Saved @${out.handle}`, "good");
      await boot();
    } catch (err) {
      console.error(err);
      setSourceStatus("Save failed", "bad");
    }
  });
}

function wireInputSourceActions() {
  const btn = document.getElementById("btn-input-source-save");
  if (!btn || btn.dataset.wired) return;
  btn.dataset.wired = "1";
  btn.addEventListener("click", async () => {
    const key = (document.getElementById("input-source-key")?.value || "").trim();
    const status = document.getElementById("input-source-status");
    if (!key) {
      if (status) status.textContent = "source key is required";
      return;
    }
    try {
      const payload = {
        source_key: key,
        source_label: (document.getElementById("input-source-label")?.value || "").trim(),
        source_class: (document.getElementById("input-source-class")?.value || "").trim(),
        manual_weight: Number(document.getElementById("input-source-weight")?.value || "1.0"),
        enabled: !!document.getElementById("input-source-enabled")?.checked,
      };
      const out = await postJson("/api/input-sources", payload);
      if (!out.ok) throw new Error(out.error || "failed");
      if (status) status.textContent = `saved ${out.source_key}`;
      await boot();
    } catch (err) {
      console.error(err);
      if (status) status.textContent = "save failed";
    }
  });

  const btnSettings = document.getElementById("btn-input-settings-save");
  if (btnSettings && !btnSettings.dataset.wired) {
    btnSettings.dataset.wired = "1";
    btnSettings.addEventListener("click", async () => {
      const status = document.getElementById("input-settings-status");
      try {
        await postJson("/api/risk-controls", {
          updates: {
            x_influence_enabled: document.getElementById("ctl-x-influence")?.checked ? "1" : "0",
            input_auto_reweight_enabled: document.getElementById("ctl-input-reweight")?.checked ? "1" : "0",
            input_weight_min_samples: String(document.getElementById("ctl-input-min-samples")?.value || "5"),
            input_weight_floor: String(document.getElementById("ctl-input-floor")?.value || "0.6"),
            input_weight_ceiling: String(document.getElementById("ctl-input-ceil")?.value || "1.6"),
            input_auto_disable_threshold: String(document.getElementById("ctl-input-disable-threshold")?.value || "0.0"),
          },
        });
        if (status) status.textContent = "saved";
        await boot();
      } catch (err) {
        console.error(err);
        if (status) status.textContent = "save failed";
      }
    });
  }
}

function wirePolyWalletActions() {
  const btn = document.getElementById("btn-polyw-save");
  if (!btn || btn.dataset.wired) return;
  btn.dataset.wired = "1";
  btn.addEventListener("click", async () => {
    const rawHandle = resolveHandleInput(["polyw-handle", "src-handle", "x-handle"], "btn-polyw-save");
    const handle = normalizeXHandle(rawHandle) || rawHandle;
    if (!handle) {
      setPolyWalletStatus(`Handle is required [build ${UI_BUILD}]`, "bad");
      console.error("wallet handle missing at submit", {
        build: UI_BUILD,
        polywHandle: document.getElementById("polyw-handle")?.value || "",
        srcHandle: document.getElementById("src-handle")?.value || "",
        xHandle: document.getElementById("x-handle")?.value || "",
      });
      return;
    }
    try {
      const payload = {
        handle,
        profile_url: (document.getElementById("polyw-url")?.value || "").trim(),
        role_copy: !!document.getElementById("polyw-copy")?.checked,
        role_alpha: !!document.getElementById("polyw-alpha")?.checked,
        active: true,
        notes: (document.getElementById("polyw-notes")?.value || "").trim(),
      };
      const out = await postJson("/api/tracked-poly-wallets", payload);
      if (!out.ok) throw new Error(out.error || "failed");
      setPolyWalletStatus(`Saved @${out.handle}`, "good");
      await boot();
    } catch (err) {
      console.error(err);
      setPolyWalletStatus("Save failed", "bad");
    }
  });
}

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
  // Populate controls
  const arbEnabled = document.getElementById("ctl-arb-enabled");
  const arbSpread = document.getElementById("ctl-arb-spread");
  const arbLeg = document.getElementById("ctl-arb-leg");
  if (arbEnabled) arbEnabled.checked = !!data.arb_enabled;
  if (arbSpread) arbSpread.value = data.min_spread_pct || 5;
  if (arbLeg) arbLeg.value = data.max_per_leg || 25;
}

function renderArbOpportunities(rows) {
  const el = document.getElementById("arb-opportunities");
  if (!el) return;
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
      console.error(err);
      if (status) { status.textContent = "Save failed"; status.className = "control-warning bad"; }
    }
  });
}

function renderFreshWhales(data) {
  const el = document.getElementById("fresh-whale-list");
  if (!el) return;
  const discoveries = (data && data.discoveries) || [];
  if (!discoveries.length) {
    el.innerHTML = `<div class="empty">No fresh whale discoveries yet.</div>`;
    return;
  }
  const now = Date.now();
  const rows = discoveries.map((d) => {
    const ago = d.discovered_at ? (() => {
      const ms = now - new Date(d.discovered_at).getTime();
      const h = Math.floor(ms / 3600000);
      return h < 1 ? "<1h ago" : h < 24 ? `${h}h ago` : `${Math.floor(h / 24)}d ago`;
    })() : "";
    const handleLink = d.handle
      ? `<a href="https://polymarket.com/@${d.handle}" target="_blank" rel="noopener">@${d.handle}</a>`
      : d.wallet_address ? d.wallet_address.slice(0, 10) + "..." : "—";
    const age = d.account_age_days >= 0 ? `${Math.round(d.account_age_days)}d` : "—";
    const size = d.trade_size_usdc ? "$" + Number(d.trade_size_usdc).toLocaleString("en-US", { maximumFractionDigits: 0 }) : "—";
    const slug = d.market_slug || "—";
    const tracked = d.auto_tracked
      ? `<span style="color:var(--green,#4caf50);font-weight:600">YES</span>`
      : `<span style="opacity:0.5">NO</span>`;
    return `<tr><td>${ago}</td><td>${handleLink}</td><td>${age}</td><td>${size}</td><td title="${slug}">${slug.length > 30 ? slug.slice(0, 30) + "…" : slug}</td><td>${tracked}</td></tr>`;
  }).join("");
  el.innerHTML = `<table><thead><tr><th>Discovered</th><th>Handle</th><th>Age</th><th>Trade Size</th><th>Market</th><th>Tracked</th></tr></thead><tbody>${rows}</tbody></table>`;
}

async function boot() {
  try {
    setStatus("loading");
    const [
      systemHealth,
      polymarketOverview,
      polymarketMmOverview,
      polymarketMmSnapshots,
      weatherMarketProbs,
      polymarketCandidates,
      polymarketMarkets,
      polymarketOrders,
      bookmarkAlphaIdeas,
      externalSignals,
      riskControls,
      trackedSources,
      inputSources,
      trackedPolyWallets,
      polyWalletScores,
      trustPanel,
      polymarketScorecard,
      arbOverview,
      arbOpportunities,
    ] = await Promise.all([
      fetchJsonSafe("/api/system-health", { overall: "warn", checks: [] }),
      fetchJsonSafe("/api/polymarket-overview", {}),
      fetchJsonSafe("/api/polymarket-mm-overview", {}),
      fetchJsonSafe("/api/polymarket-mm-snapshots?ready_only=0", []),
      fetchJsonSafe("/api/weather-market-probs", []),
      fetchJsonSafe("/api/polymarket-candidates", []),
      fetchJsonSafe("/api/polymarket-markets", []),
      fetchJsonSafe("/api/polymarket-orders", []),
      fetchJsonSafe("/api/bookmark-alpha-ideas", []),
      fetchJsonSafe("/api/external-signals", []),
      fetchJsonSafe("/api/risk-controls", []),
      fetchJsonSafe("/api/tracked-sources", []),
      fetchJsonSafe("/api/input-sources", []),
      fetchJsonSafe("/api/tracked-poly-wallets", []),
      fetchJsonSafe("/api/polymarket-wallet-scores", []),
      fetchJsonSafe("/api/trust-panel", {}),
      fetchJsonSafe("/api/polymarket-scorecard", {}),
      fetchJsonSafe("/api/arb-overview", {}),
      fetchJsonSafe("/api/arb-opportunities", []),
    ]);

    runUiStep("wirePreTradeActions", () => wirePreTradeActions());
    runUiStep("wireSourceActions", () => wireSourceActions());
    runUiStep("wireInputSourceActions", () => wireInputSourceActions());
    runUiStep("wirePolyWalletActions", () => wirePolyWalletActions());
    runUiStep("wireArbActions", () => wireArbActions());

    runUiStep("renderPolymarketScorecard", () => renderPolymarketScorecard(polymarketScorecard || {}));
    runUiStep("renderOverview", () => renderOverview(polymarketOverview || {}));
    runUiStep("renderMmOverview", () => renderMmOverview(polymarketMmOverview || {}));
    runUiStep("renderPreTradeControls", () => renderPreTradeControls(riskControls || []));
    runUiStep("renderPolymarketCandidates", () => renderPolymarketCandidates(polymarketCandidates || []));
    runUiStep("renderPolymarketMarkets", () => renderPolymarketMarkets(polymarketMarkets || []));
    runUiStep("renderPolymarketOrders", () => renderPolymarketOrders(polymarketOrders || []));
    runUiStep("renderMmSnapshots", () => renderMmSnapshots(polymarketMmSnapshots || []));
    runUiStep("renderArbOverview", () => renderArbOverview(arbOverview || {}));
    runUiStep("renderArbOpportunities", () => renderArbOpportunities(arbOpportunities || []));
    runUiStep("renderWeatherMarketProbs", () => renderWeatherMarketProbs(weatherMarketProbs || []));
    runUiStep("renderBookmarkAlphaIdeas", () => renderBookmarkAlphaIdeas(bookmarkAlphaIdeas || []));
    runUiStep("renderTrackedSources", () => renderTrackedSources(trackedSources || []));
    runUiStep("renderInputSources", () => renderInputSources(inputSources || []));
    runUiStep("renderTrackedPolyWallets", () => renderTrackedPolyWallets(trackedPolyWallets || []));
    runUiStep("renderPolyWalletScores", () => renderPolyWalletScores(polyWalletScores || []));
    runUiStep("renderTrustPanel", () => renderTrustPanel(trustPanel || {}));
    fetchJsonSafe("/api/fresh-whales", {}).then(d => runUiStep("renderFreshWhales", () => renderFreshWhales(d || {})));

    runUiStep("renderExternalSignals", () => {
      renderTable(
        "external-signals",
        (externalSignals || []).slice(0, 20),
        ["Source", "Ticker", "Dir", "Conf"],
        ["source", "ticker", "direction", "confidence"]
      );
    });

    const topState = (systemHealth && systemHealth.overall) || "good";
    setStatus("online", topState === "good" ? "good" : (topState === "warn" ? "warn" : "bad"));
  } catch (err) {
    console.error(err);
    setStatus("offline", "bad");
  }
}

boot();
