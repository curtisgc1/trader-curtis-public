async function fetchJson(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${url} failed: ${res.status}`);
  return res.json();
}

const UI_BUILD = "20260226a";

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
    body: JSON.stringify(body),
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

let curveMode = localStorage.getItem("curveMode") || "time";
let autoRefreshTimer = null;
let pnlBreakdownCache = null;
let tradeReviewExplain = null;

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

function fmtMinutes(v) {
  const n = Number(v);
  if (!Number.isFinite(n) || n < 0) return "n/a";
  if (n < 60) return `${n.toFixed(1)}m`;
  const h = n / 60;
  if (h < 48) return `${h.toFixed(1)}h`;
  return `${(h / 24).toFixed(1)}d`;
}

function friendlyInputName(key) {
  const k = String(key || "").trim();
  if (!k) return "Unknown input";
  const lower = k.toLowerCase();
  if (lower === "family:liquidity") return "Liquidity setup quality";
  if (lower === "family:pipeline") return "Strategy model score";
  if (lower === "family:pattern") return "Chart/pattern reliability";
  if (lower === "family:social") return "Social sentiment";
  if (lower === "family:external") return "External news/event signals";
  if (lower === "family:copy") return "Copy-trade style signals";
  if (lower.startsWith("strategy:")) return `Strategy-specific input (${k.split(":")[1] || "custom"})`;
  if (lower.startsWith("pipeline:")) return `Pipeline source (${k.split(":")[1] || "custom"})`;
  if (lower.startsWith("source:")) return `Source feed (${k.split(":")[1] || "custom"})`;
  if (lower.startsWith("x:")) return `Tracked X handle (${k.split(":")[1] || "custom"})`;
  return k.replace(/[:_]/g, " ");
}

function inputHelpText(key) {
  const k = String(key || "").toLowerCase();
  if (!k) return "Pick an input to see what it controls.";
  if (k === "family:liquidity") return "Emphasizes entries where stop/target structure and liquidity sweeps look high quality. Best for timing entries.";
  if (k === "family:pipeline") return "Controls weight of your strategy engine scores. Higher means strategy score drives decisions more.";
  if (k === "family:pattern") return "Controls chart-pattern confidence impact (flags, reversals, liquidity grabs, etc.).";
  if (k === "family:social") return "Controls sentiment influence from social inputs.";
  if (k === "family:external") return "Controls external signal impact (news/events/free feeds).";
  if (k === "family:copy") return "Controls copy/call style source impact.";
  if (k.startsWith("strategy:") && k.includes(":family:liquidity")) return "Liquidity weight only for this strategy profile. Useful for scalp-vs-swing tuning.";
  if (k.startsWith("strategy:")) return "Strategy-specific override. Lets one strategy use different weight than global defaults.";
  if (k.startsWith("source:")) return "Source-level override. Use this when one feed is consistently strong/weak.";
  if (k.startsWith("pipeline:")) return "Pipeline-level override. Use to boost or reduce one strategy lane.";
  if (k.startsWith("x:")) return "X-account-level override. Use to tune one handle without changing others.";
  return "This is a tunable input weight. Start near 1.0 and adjust gradually using results.";
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

function renderAlerts(systemHealth, readiness, awareness, tradeClaimGuard) {
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
  (tradeClaimGuard?.blockers || []).forEach((b) => {
    items.push({ n: "Trade Claim Blocker", d: b, s: "bad" });
  });
  (tradeClaimGuard?.warnings || []).forEach((w) => {
    items.push({ n: "Trade Claim Warning", d: w, s: "warn" });
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

function renderHealthOverview(systemHealth, readiness, learningMonitor, masterOverview) {
  const el = document.getElementById("health-overview");
  if (!el) return;
  const lh = learningMonitor?.learning_health || {};
  const out = learningMonitor?.outcomes || {};
  const venue = masterOverview?.venue_24h || {};
  const missed = masterOverview?.missed_opportunities || {};

  const alp = venue?.alpaca || {};
  const hl = venue?.hyperliquid || {};
  const poly = venue?.polymarket || {};
  const made = Number(alp.filled || 0) + Number(hl.filled || 0) + Number(poly.filled || 0);
  const submitted = Number(alp.submitted || 0) + Number(hl.submitted || 0) + Number(poly.submitted || 0);

  const freshPipeline = (systemHealth?.checks || []).find((c) => c.name === "Pipeline Freshness")?.detail || "n/a";
  const freshRoute = (systemHealth?.checks || []).find((c) => c.name === "Routing Freshness")?.detail || "n/a";
  const readyScore = Number(readiness?.score || 0).toFixed(0);
  const cov = Number(lh.coverage_pct || 0).toFixed(1);
  const trackedCov = Number(lh.tracked_coverage_pct || 0).toFixed(1);
  const realized = Number(out.realized_total || 0);
  const op = Number(out.operational_total || 0);

  el.innerHTML = [
    ["Overall", `${systemHealth?.overall || "unknown"} | readiness ${readiness?.state || "unknown"} (${readyScore})`],
    ["Freshness", `pipeline ${freshPipeline} | routing ${freshRoute}`],
    ["24h Trades Made", `${made} filled | ${submitted} submitted`],
    ["Truth Coverage (7d)", `${cov}% resolved | ${trackedCov}% tracked`],
    ["Outcome Layer", `realized ${realized} | operational ${op}`],
    ["Not Taken (7d)", `${Number(missed.not_taken_total || 0)} checked | ${Number(missed.not_taken_wins || 0)} winners`],
  ].map(([k, v]) => `<div class="item"><span class="label">${k}</span><span>${v}</span></div>`).join("");
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

function renderTradeClaimGuard(guard) {
  const brief = document.getElementById("trade-claim-brief");
  if (brief) {
    const state = guard?.state || "unknown";
    const ready = guard?.trade_ready ? "yes" : "no";
    const summary = guard?.summary || "n/a";
    const queued = guard?.approved_queued_routes ?? 0;
    brief.innerHTML = [
      ["Trade Claim Guard", state],
      ["Trade Ready", ready],
      ["Approved Queued Routes", String(queued)],
      ["Summary", summary],
    ]
      .map(([k, v]) => `<div class="item"><span class="label">${k}</span><span>${v}</span></div>`)
      .join("");
  }
  renderTable("trade-claim-checks", guard?.checks || [], ["Check", "State", "Detail"], ["name", "state", "detail"]);
}

function renderExecutionReadiness(walletRows, awareness, guard) {
  const el = document.getElementById("execution-readiness-brief");
  if (!el) return;
  const map = {};
  (walletRows || []).forEach((r) => { map[r.key] = r.value; });

  const awarenessState = String(awareness?.overall || "unknown");
  const guardState = String(guard?.state || "unknown");
  let overall = "good";
  if (awarenessState === "bad" || guardState === "bad") overall = "bad";
  else if (awarenessState === "warn" || guardState === "warn") overall = "warn";

  const blockers = [...(awareness?.blockers || []), ...(guard?.blockers || [])];
  const warnings = [...(awareness?.warnings || []), ...(guard?.warnings || [])];
  const adapterDetail = (guard?.checks || []).find((c) => c?.name === "Adapters Detail")?.detail || "n/a";

  const lines = [
    ["Readiness", `${overall} | awareness ${awarenessState} | claim ${guardState}`],
    ["Effective Mode", `${awareness?.effective_mode || "unknown"} | trade ready ${guard?.trade_ready ? "yes" : "no"}`],
    ["Approved Queued Routes", String(guard?.approved_queued_routes ?? 0)],
    ["Adapters", adapterDetail],
    ["HL Wallet", map.hl_wallet_address ? "configured" : "missing"],
    ["Poly Wallet", map.poly_wallet_address ? "configured" : "missing"],
  ];
  if (blockers.length) {
    lines.push(["Top Blockers", blockers.slice(0, 3).join(" | ")]);
  } else if (warnings.length) {
    lines.push(["Top Warnings", warnings.slice(0, 3).join(" | ")]);
  } else {
    lines.push(["Blocking Status", "none"]);
  }
  el.innerHTML = lines.map(([k, v]) => `<div class="item"><span class="label">${k}</span><span>${v}</span></div>`).join("");

  renderTable("awareness-checks", awareness?.checks || [], ["Check", "State", "Detail"], ["name", "state", "detail"]);
  renderTable("trade-claim-checks", guard?.checks || [], ["Check", "State", "Detail"], ["name", "state", "detail"]);
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
  const isMade = (status) => {
    const st = String(status || "").toLowerCase();
    if (!st) return false;
    if (st.includes("block") || st.includes("reject") || st.includes("fail") || st.includes("queued")) return false;
    return st.includes("submit") || st.includes("fill") || st.includes("execut") || st.includes("open") || st.includes("accept");
  };

  if (exEl) {
    const rows = (exOrders || []).filter((r) => isMade(r.order_status)).slice(0, 8);
    exEl.innerHTML = rows.length === 0
      ? `<div class="empty">No made execution trades yet</div>`
      : rows.map((r) => {
          const st = String(r.order_status || "").toLowerCase();
          const cls = st.includes("block") || st.includes("fail") ? "bad" : (st.includes("submit") || st.includes("fill") ? "good" : "warn");
          return `<div class="flow-item"><div><strong>${r.ticker || ""}</strong> ${r.direction || ""}</div><div>${r.mode || ""} • ${fmtCurrency(r.notional || 0)}</div><div class="${cls}">${r.order_status || ""}</div></div>`;
        }).join("");
  }

  if (poEl) {
    const rows = (polyOrders || []).filter((r) => isMade(r.status)).slice(0, 8);
    poEl.innerHTML = rows.length === 0
      ? `<div class="empty">No made polymarket trades yet</div>`
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
  const polyEl = document.getElementById("poly-positions");

  const alp = snapshot?.alpaca || {};
  const hl = snapshot?.hyperliquid || {};
  const poly = snapshot?.polymarket || {};

  if (brief) {
    const rows = [
      ["Alpaca Equity", fmtCurrency(alp.equity || 0)],
      ["Alpaca Cash", fmtCurrency(alp.cash || 0)],
      ["Alpaca Buying Power", fmtCurrency(alp.buying_power || 0)],
      ["HL Network", hl.network || "unknown"],
      ["HL Account Value", fmtCurrency(hl.account_value || 0)],
      ["HL Withdrawable", fmtCurrency(hl.withdrawable || 0)],
      ["Poly Filled Live", String(poly.filled_live_count || 0)],
      ["Poly Net Exposure", fmtCurrency(poly.net_exposure_usd || 0)],
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
    const perpRows = hl.positions || [];
    const spotRows = (hl.spot_balances || []).filter((b) => Number(b.total || 0) > 0);
    const perpHtml = perpRows.length
      ? `<div class="flow-item"><strong>Perps: ${perpRows.length}</strong></div>` +
        perpRows.slice(0, 24).map((p) => {
          const pl = Number(p.unrealized_pnl || 0);
          const plPct = Number(p.unrealized_pnl_pct || 0);
          const lev = Number(p.leverage || 1);
          const cls = pl >= 0 ? "good" : "bad";
          return `<div class="flow-item"><div><strong>${p.coin || ""}</strong> ${p.szi || ""} | lev ${lev.toFixed(2)}x</div><div>Value ${fmtCurrency(p.position_value || 0)}</div><div class="${cls}">uPnL ${fmtCurrency(pl)} (${plPct.toFixed(2)}%)</div></div>`;
        }).join("") +
        (perpRows.length > 24 ? `<div class="flow-item">...and ${perpRows.length - 24} more perp positions</div>` : "")
      : `<div class="empty">No HL perp positions</div>`;
    const spotHtml = spotRows.length
      ? `<div class="flow-item"><strong>Spot Balances: ${spotRows.length}</strong></div>` +
        spotRows.slice(0, 24).map((b) => {
          return `<div class="flow-item"><div><strong>${b.coin || ""}</strong> ${Number(b.total || 0).toFixed(6)}</div><div>Hold ${Number(b.hold || 0).toFixed(6)}</div></div>`;
        }).join("") +
        (spotRows.length > 24 ? `<div class="flow-item">...and ${spotRows.length - 24} more spot balances</div>` : "")
      : `<div class="empty">No HL spot balances</div>`;
    hlEl.innerHTML = `${perpHtml}${spotHtml}`;
    if (!perpRows.length && !spotRows.length && hl.error) {
      hlEl.innerHTML = `<div class="empty">HL: ${hl.error}</div>`;
    }
  }

  if (polyEl) {
    const rows = poly.positions || [];
    polyEl.innerHTML = rows.length
      ? rows.slice(0, 24).map((p) => {
          const n = Number(p.net_notional || 0);
          const cls = n >= 0 ? "good" : "bad";
          return `<div class="flow-item"><div><strong>${p.market_id || ""}</strong> ${p.outcome || ""}</div><div class="${cls}">Net ${fmtCurrency(n)}</div><div>Trades ${Number(p.trades || 0)}</div></div>`;
        }).join("")
      : `<div class="empty">${poly.error ? `Poly: ${poly.error}` : "No Polymarket positions"}</div>`;
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
    const candidateWhy = r.candidate_rationale || "";
    let inputSummary = "";
    try {
      const parsed = JSON.parse(r.candidate_inputs || "[]");
      if (Array.isArray(parsed) && parsed.length) {
        inputSummary = parsed
          .map((x) => ({ key: String(x.key || "input"), value: Number(x.value || 0), weight: Number(x.weight || 0) }))
          .filter((x) => Number.isFinite(x.value) && x.value > 0)
          .sort((a, b) => b.value - a.value)
          .slice(0, 5)
          .map((x) => `${x.key}:${x.value.toFixed(3)} (w=${x.weight.toFixed(2)})`)
          .join(" | ");
      }
    } catch (_) {
      inputSummary = "";
    }
    return `<details class="flow-item"><summary><strong>${r.ticker || ""}</strong> ${r.direction || ""} • ${fmtCurrency(r.notional || 0)} • <span class="${cls}">${r.order_status || ""}</span></summary><div>source: ${r.source_tag || "n/a"} | score: ${r.score || ""} | mode: ${r.mode || ""}</div><div>route reason: ${why}</div><div>candidate synopsis: ${candidateWhy || "n/a"}</div><div>input hits: ${inputSummary || "n/a"}</div><div>notes: ${r.notes || ""}</div></details>`;
  }).join("");
}

function renderVenueAndMissed(master) {
  const venueEl = document.getElementById("venue-summary");
  const missedEl = document.getElementById("missed-summary");
  if (!venueEl || !missedEl) return;
  const v = (master && master.venue_24h) || {};
  const a = v.alpaca || {};
  const h = v.hyperliquid || {};
  const p = v.polymarket || {};
  venueEl.innerHTML = [
    ["Alpaca 24h", `events ${a.events || 0} | submitted ${a.submitted || 0} | filled ${a.filled || 0}`],
    ["Hyperliquid 24h", `events ${h.events || 0} | submitted ${h.submitted || 0} | filled ${h.filled || 0}`],
    ["Polymarket 24h", `events ${p.events || 0} | submitted ${p.submitted || 0} | filled ${p.filled || 0}`],
  ].map(([k, val]) => `<div class="item"><span class="label">${k}</span><span>${val}</span></div>`).join("");

  const m = (master && master.missed_opportunities) || {};
  missedEl.innerHTML = [
    ["Not Taken (7d)", `${m.not_taken_total || 0}`],
    ["Resolved", `${m.not_taken_resolved || 0}`],
    ["Missed Winners", `${m.not_taken_wins || 0}`],
    ["Missed Win Rate", `${Number(m.not_taken_win_rate || 0).toFixed(2)}%`],
    ["Avg PnL %", `${Number(m.not_taken_avg_pnl_pct || 0).toFixed(2)}%`],
  ].map(([k, val]) => `<div class="item"><span class="label">${k}</span><span>${val}</span></div>`).join("");
}

function renderExecutionOpportunity(master, monitor) {
  const el = document.getElementById("execution-opportunity-brief");
  if (!el) return;

  const v = master?.venue_24h || {};
  const a = v.alpaca || {};
  const h = v.hyperliquid || {};
  const p = v.polymarket || {};
  const missed = master?.missed_opportunities || {};
  const lh = monitor?.learning_health || {};
  const out = monitor?.outcomes || {};

  const submitted = Number(a.submitted || 0) + Number(h.submitted || 0) + Number(p.submitted || 0);
  const filled = Number(a.filled || 0) + Number(h.filled || 0) + Number(p.filled || 0);
  const blocked = Number(a.blocked || 0) + Number(h.blocked || 0) + Number(p.blocked || 0);
  const resolved = Number(missed.not_taken_resolved || 0);
  const wins = Number(missed.not_taken_wins || 0);

  el.innerHTML = [
    ["24h Execution", `submitted ${submitted} | filled ${filled} | blocked ${blocked}`],
    ["By Venue", `alp ${a.filled || 0}/${a.submitted || 0} | hl ${h.filled || 0}/${h.submitted || 0} | poly ${p.filled || 0}/${p.submitted || 0}`],
    ["Missed Opportunities (7d)", `${Number(missed.not_taken_total || 0)} checked | ${wins} winners / ${resolved} resolved`],
    ["Missed Win Rate", `${Number(missed.not_taken_win_rate || 0).toFixed(2)}% | avg ${Number(missed.not_taken_avg_pnl_pct || 0).toFixed(2)}%`],
    ["Truth Coverage (7d)", `${Number(lh.coverage_pct || 0).toFixed(2)}% resolved | ${Number(lh.tracked_coverage_pct || 0).toFixed(2)}% tracked`],
    ["Outcome Writes", `realized ${Number(out.realized_total || 0)} | operational ${Number(out.operational_total || 0)} | last ${fmtMinutes(out.last_resolved_age_min)} ago`],
  ].map(([k, vtxt]) => `<div class="item"><span class="label">${k}</span><span>${vtxt}</span></div>`).join("");
}

function renderPositionPlan(intents) {
  const brief = document.getElementById("position-plan-brief");
  const table = document.getElementById("position-plan-table");
  if (!brief || !table) return;

  const rows = Array.isArray(intents) ? intents : [];
  if (!rows.length) {
    brief.innerHTML = [
      ["Plan Status", "No current manage intents"],
      ["Meaning", "No open positions currently crossed manage thresholds"],
    ].map(([k, v]) => `<div class="item"><span class="label">${k}</span><span>${v}</span></div>`).join("");
    table.innerHTML = `<div class="empty">No position-management intents yet</div>`;
    return;
  }

  const actionCounts = {};
  rows.forEach((r) => {
    const a = String(r.action || r.status || "manage");
    actionCounts[a] = (actionCounts[a] || 0) + 1;
  });
  const actionSummary = Object.entries(actionCounts)
    .sort((a, b) => Number(b[1]) - Number(a[1]))
    .slice(0, 3)
    .map(([k, v]) => `${k} (${v})`)
    .join(" | ");

  const top = rows
    .slice()
    .sort((a, b) => Number(b.confidence || 0) - Number(a.confidence || 0))[0] || {};
  const topLabel = top.symbol
    ? `${top.symbol} ${top.side || ""} | ${top.action || top.status || "manage"} | conf ${Number(top.confidence || 0).toFixed(2)}`
    : "n/a";

  const newest = rows[0]?.created_at || "n/a";
  brief.innerHTML = [
    ["Active Intents", String(rows.length)],
    ["Action Mix", actionSummary || "n/a"],
    ["Top Conviction", topLabel],
    ["Last Update", newest],
  ].map(([k, v]) => `<div class="item"><span class="label">${k}</span><span>${v}</span></div>`).join("");

  const mapped = rows.slice(0, 60).map((r) => ({
    time: String(r.created_at || ""),
    symbol: String(r.symbol || ""),
    side: String(r.side || ""),
    action: String(r.action || r.status || "manage"),
    leverage: `${Number(r.leverage || 1).toFixed(2)}x`,
    confidence: Number(r.confidence || 0).toFixed(2),
    pnl: `${Number(r.pnl_pct || 0).toFixed(2)}% / ${fmtCurrency(r.upnl_usd || 0)}`,
    stop: Number(r.suggested_stop_price || 0) > 0 ? Number(r.suggested_stop_price).toFixed(4) : "-",
    reason: String(r.reason || ""),
  }));
  renderTable(
    "position-plan-table",
    mapped,
    ["Time", "Symbol", "Side", "Action", "Lev", "Conf", "uPnL", "Suggested Stop", "Reason"],
    ["time", "symbol", "side", "action", "leverage", "confidence", "pnl", "stop", "reason"]
  );
}

function renderLearningMonitor(monitor) {
  const brief = document.getElementById("learning-monitor-brief");
  const horizonEl = document.getElementById("learning-monitor-horizons");
  if (!brief && !horizonEl) return;

  const lh = monitor?.learning_health || {};
  const out = monitor?.outcomes || {};
  const hz = monitor?.horizons || {};
  const rd = monitor?.readiness || {};
  const rc = monitor?.reconciler || {};
  const tr = monitor?.trades || {};

  const realized = Number(out.realized_total || 0);
  const operational = Number(out.operational_total || 0);
  const resolved = Number(lh.resolved_routes || 0);
  const eligible = Number(lh.eligible_routes || 0);
  const realized24 = Number(out.realized_24h || 0);
  const op24 = Number(out.operational_24h || 0);
  const coverage = Number(lh.coverage_pct || 0).toFixed(2);
  const trackedCoverage = Number(lh.tracked_coverage_pct || 0).toFixed(2);
  const realizedWin = Number(lh.realized_win_rate || 0).toFixed(2);
  const avgPnl = Number(lh.realized_avg_pnl_pct || 0).toFixed(2);

  if (brief) {
    brief.innerHTML = [
      ["Route Outcomes", `realized ${realized} | operational ${operational}`],
      ["24h Outcome Adds", `realized ${realized24} | operational ${op24}`],
      ["Coverage (7d)", `${coverage}% (${resolved}/${eligible}) | tracked ${trackedCoverage}%`],
      ["Realized Quality (7d)", `win ${realizedWin}% | avg ${avgPnl}%`],
      ["Trades", `open ${Number(tr.open_total || 0)} | closed ${Number(tr.closed_total || 0)} | route-linked closed ${Number(tr.closed_with_route || 0)}`],
      ["Last Outcome Write", `${fmtMinutes(out.last_resolved_age_min)} ago`],
      ["GRPO Readiness", `${rd.state || "unknown"} ${rd.reasons ? `(${rd.reasons})` : ""}`],
      ["Live Weight Updates", String(rd.apply_live_updates || "0") === "1" ? "enabled" : "disabled"],
      ["Reconciler", `${rc.last_status || "n/a"} | last success ${rc.last_success_utc || "n/a"}`],
    ].map(([k, v]) => `<div class="item"><span class="label">${k}</span><span>${v}</span></div>`).join("");
  }

  const byH = Array.isArray(hz.by_horizon) ? hz.by_horizon : [];
  if (!horizonEl) return;
  if (!byH.length) {
    horizonEl.innerHTML = `<div class="item"><span class="label">Horizon Rows</span><span>0</span></div>`;
    return;
  }
  horizonEl.innerHTML = [
    `<div class="item"><span class="label">Total Horizon Rows</span><span>${Number(hz.rows_total || 0)}</span></div>`,
    ...byH.slice(0, 8).map((row) => {
      const h = Number(row.horizon_hours || 0);
      const n = Number(row.count || 0);
      const avg = Number(row.avg_pnl_pct || 0).toFixed(3);
      const label = h >= 24 ? `${(h / 24).toFixed(h % 24 === 0 ? 0 : 1)}d` : `${h}h`;
      return `<div class="item"><span class="label">${label}</span><span>${n} rows | avg ${avg}%</span></div>`;
    }),
  ].join("");
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

function renderPnlBreakdown(data) {
  const wrap = document.getElementById("pnl-drilldown-wrap");
  const summaryEl = document.getElementById("pnl-drilldown-summary");
  const winnersEl = document.getElementById("pnl-top-winners");
  const losersEl = document.getElementById("pnl-top-losers");
  const recentEl = document.getElementById("pnl-recent-table");
  if (!wrap || !summaryEl || !winnersEl || !losersEl || !recentEl) return;

  const rows = data || {};
  summaryEl.innerHTML = [
    ["Closed Trades", String(rows.closed_count || 0)],
    ["Wins / Losses", `${Number(rows.wins || 0)} / ${Number(rows.losses || 0)}`],
    ["Win Rate", `${Number(rows.win_rate || 0).toFixed(2)}%`],
    ["Total PnL", fmtCurrency(rows.total_pnl || 0)],
    ["Avg Per Trade", fmtCurrency(rows.avg_pnl || 0)],
  ].map(([k, v]) => `<div class="item"><span class="label">${k}</span><span>${v}</span></div>`).join("");

  const renderTradeRow = (r) => {
    const pnl = Number(r.pnl || 0);
    const cls = pnl >= 0 ? "good" : "bad";
    return `<div class="flow-item"><div><strong>${r.ticker || ""}</strong> ${r.trade_id || ""}</div><div>${r.closed_at || ""}</div><div class="${cls}">${fmtCurrency(pnl)} (${Number(r.pnl_percent || 0).toFixed(2)}%)</div><div>src: ${r.source_tag || "n/a"}</div></div>`;
  };

  winnersEl.innerHTML = (rows.top_winners || []).length
    ? (rows.top_winners || []).map(renderTradeRow).join("")
    : `<div class="empty">No winning closed trades yet</div>`;
  losersEl.innerHTML = (rows.top_losers || []).length
    ? (rows.top_losers || []).map(renderTradeRow).join("")
    : `<div class="empty">No losing closed trades yet</div>`;

  renderTable(
    "pnl-recent-table",
    rows.recent_closed || [],
    ["Closed", "Ticker", "PnL", "PnL %", "Source", "Score"],
    ["closed_at", "ticker", "pnl", "pnl_percent", "source_tag", "route_score"]
  );
}

function setupRefreshControls() {
  const btn = document.getElementById("btn-dashboard-refresh");
  const auto = document.getElementById("auto-refresh-toggle");

  if (btn && !btn.dataset.wired) {
    btn.dataset.wired = "1";
    btn.onclick = async () => {
      await boot();
    };
  }

  if (auto && !auto.dataset.wired) {
    auto.dataset.wired = "1";
    const saved = localStorage.getItem("dashboardAutoRefresh") === "1";
    auto.checked = saved;
    const apply = () => {
      if (autoRefreshTimer) {
        clearInterval(autoRefreshTimer);
        autoRefreshTimer = null;
      }
      if (auto.checked) {
        autoRefreshTimer = setInterval(() => {
          boot();
        }, 60000);
        localStorage.setItem("dashboardAutoRefresh", "1");
      } else {
        localStorage.setItem("dashboardAutoRefresh", "0");
      }
    };
    auto.onchange = apply;
    apply();
  }
}

function bindPnlDrilldown() {
  const btn = document.getElementById("metric-pnl-toggle");
  const wrap = document.getElementById("pnl-drilldown-wrap");
  if (!btn || !wrap || btn.dataset.wired) return;
  btn.dataset.wired = "1";
  btn.onclick = async () => {
    const isOpen = wrap.style.display !== "none";
    if (isOpen) {
      wrap.style.display = "none";
      return;
    }
    wrap.style.display = "";
    if (!pnlBreakdownCache) {
      pnlBreakdownCache = await fetchJsonSafe("/api/pnl-breakdown?limit=160", {});
    }
    renderPnlBreakdown(pnlBreakdownCache || {});
  };
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
  const alpacaMinScore = document.getElementById("ctl-alpaca-min-score");
  const hlMinScore = document.getElementById("ctl-hl-min-score");
  const polyMinConf = document.getElementById("ctl-poly-min-conf");
  const routeLimit = document.getElementById("ctl-route-limit");
  const thresholdUnlock = document.getElementById("ctl-threshold-unlock");

  if (hlNotional) hlNotional.value = c.hyperliquid_test_notional_usd || "10";
  if (hlLev) hlLev.value = c.hyperliquid_test_leverage || "1";
  if (maxSignal) maxSignal.value = c.max_signal_notional_usd || "150";
  if (minScore) minScore.value = c.min_candidate_score || "50";
  if (alpacaMinScore) alpacaMinScore.value = c.alpaca_min_route_score || "60";
  if (hlMinScore) hlMinScore.value = c.hyperliquid_min_route_score || "60";
  if (polyMinConf) polyMinConf.value = c.polymarket_min_confidence_pct || "60";
  if (routeLimit) routeLimit.value = c.auto_route_limit || "24";
  if (thresholdUnlock) thresholdUnlock.value = c.threshold_override_unlocked || "0";

  const status = document.getElementById("master-control-status");
  const setMsg = (m) => { if (status) status.textContent = m; };

  const btnSave = document.getElementById("btn-master-save");
  if (btnSave) btnSave.onclick = async () => {
    await updateControls({
      hyperliquid_test_notional_usd: (hlNotional?.value || "10").toString(),
      hyperliquid_test_leverage: (hlLev?.value || "1").toString(),
      max_signal_notional_usd: (maxSignal?.value || "150").toString(),
      min_candidate_score: (minScore?.value || "50").toString(),
      alpaca_min_route_score: (alpacaMinScore?.value || "60").toString(),
      hyperliquid_min_route_score: (hlMinScore?.value || "60").toString(),
      polymarket_min_confidence_pct: (polyMinConf?.value || "60").toString(),
      auto_route_limit: (routeLimit?.value || "24").toString(),
      threshold_override_unlocked: (thresholdUnlock?.value || "0").toString(),
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

function bindPositionPlanControls(controls) {
  const c = controlMap(controls);
  const stopLoss = document.getElementById("pos-stop-loss-pct");
  const trailStart = document.getElementById("pos-trail-start-pct");
  const trailGap = document.getElementById("pos-trail-gap-pct");
  const tpPartial = document.getElementById("pos-tp-partial-pct");
  const tpMajor = document.getElementById("pos-tp-major-pct");
  const cooldown = document.getElementById("pos-intent-cooldown-hours");
  const btnSave = document.getElementById("btn-position-plan-save");
  const status = document.getElementById("position-plan-status");

  if (stopLoss) stopLoss.value = c.position_stop_loss_pct || "5";
  if (trailStart) trailStart.value = c.position_trail_start_pct || "6";
  if (trailGap) trailGap.value = c.position_trailing_stop_gap_pct || "2.5";
  if (tpPartial) tpPartial.value = c.position_take_profit_partial_pct || "12";
  if (tpMajor) tpMajor.value = c.position_take_profit_major_pct || "25";
  if (cooldown) cooldown.value = c.position_manage_intent_cooldown_hours || "6";

  if (!btnSave || btnSave.dataset.wired) return;
  btnSave.dataset.wired = "1";
  btnSave.onclick = async () => {
    await updateControls({
      position_stop_loss_pct: String(stopLoss?.value || "5"),
      position_trail_start_pct: String(trailStart?.value || "6"),
      position_trailing_stop_gap_pct: String(trailGap?.value || "2.5"),
      position_take_profit_partial_pct: String(tpPartial?.value || "12"),
      position_take_profit_major_pct: String(tpMajor?.value || "25"),
      position_manage_intent_cooldown_hours: String(cooldown?.value || "6"),
    });
    if (status) status.textContent = "Saved. New settings apply on next position planner run.";
    await runAction("run_cycle");
    await boot();
  };
}

function bindPositionProtectionActions(intents, snapshot, controls) {
  const symbolEl = document.getElementById("pos-protect-symbol");
  const stopEl = document.getElementById("pos-protect-stop-price");
  const trailGapEl = document.getElementById("pos-protect-trail-gap");
  const qtyPctEl = document.getElementById("pos-protect-qty-pct");
  const dryRunEl = document.getElementById("pos-protect-dry-run");
  const btnStop = document.getElementById("btn-pos-apply-stop");
  const btnTrail = document.getElementById("btn-pos-apply-trailing");
  const status = document.getElementById("pos-protect-status");
  if (!symbolEl || !stopEl || !trailGapEl || !qtyPctEl || !dryRunEl || !btnStop || !btnTrail || !status) return;

  const c = controlMap(controls || []);
  const defaultTrailGap = Number(c.position_trailing_stop_gap_pct || 2.5);
  if (!String(trailGapEl.value || "").trim() || Number(trailGapEl.value || 0) <= 0) {
    trailGapEl.value = defaultTrailGap.toFixed(1);
  }

  const rows = Array.isArray(intents) ? intents : [];
  const suggestions = {};
  rows.forEach((r) => {
    const sym = String(r.symbol || "").toUpperCase().trim();
    if (!sym) return;
    const s = Number(r.suggested_stop_price || 0);
    if (s > 0 && !suggestions[sym]) suggestions[sym] = s;
  });

  const hlPositions = ((snapshot && snapshot.hyperliquid && snapshot.hyperliquid.positions) || [])
    .map((p) => String(p.coin || "").toUpperCase().trim())
    .filter((x) => !!x);
  const intentSymbols = rows.map((r) => String(r.symbol || "").toUpperCase().trim()).filter((x) => !!x);
  const symbols = Array.from(new Set([...hlPositions, ...intentSymbols])).sort((a, b) => a.localeCompare(b));

  symbolEl.innerHTML = symbols.length
    ? symbols.map((s) => `<option value="${s}">${s}</option>`).join("")
    : `<option value="">No open HL symbols</option>`;
  if (symbols.length && !symbols.includes(String(symbolEl.value || "").toUpperCase())) {
    symbolEl.value = symbols[0];
  }

  const syncStopSuggestion = () => {
    const sym = String(symbolEl.value || "").toUpperCase();
    const sug = Number(suggestions[sym] || 0);
    if (sug > 0) {
      stopEl.value = sug.toFixed(4);
    }
  };
  if (!symbolEl.dataset.wired) {
    symbolEl.dataset.wired = "1";
    symbolEl.addEventListener("change", syncStopSuggestion);
  }
  if (Number(stopEl.value || 0) <= 0) syncStopSuggestion();

  const apply = async (mode) => {
    const symbol = String(symbolEl.value || "").toUpperCase().trim();
    if (!symbol) {
      status.textContent = "No symbol selected";
      return;
    }
    const payload = {
      symbol,
      mode,
      qty_pct: Number(qtyPctEl.value || 100),
      dry_run: String(dryRunEl.value || "0") === "1",
      cancel_existing: true,
    };
    if (mode === "stop") {
      payload.stop_price = Number(stopEl.value || 0);
    } else {
      payload.trailing_gap_pct = Number(trailGapEl.value || defaultTrailGap || 2.5);
      payload.stop_price = 0;
    }
    status.textContent = `Submitting ${mode} protection for ${symbol}...`;
    const out = await postJson("/api/position-protection", payload);
    if (!out || !out.ok) {
      status.textContent = `Failed: ${(out && (out.error || out.message)) || "unknown"}`;
      return;
    }
    const sp = Number(out.stop_price || 0);
    if (sp > 0) stopEl.value = sp.toFixed(4);
    const intentId = out?.details?.intent_id ? ` intent ${out.details.intent_id}` : "";
    status.textContent = out.dry_run
      ? `Dry run OK ${symbol}: stop ${sp.toFixed(4)} qty ${Number(out.qty_to_protect || 0).toFixed(6)}`
      : `Submitted ${mode} stop for ${symbol}: stop ${sp.toFixed(4)}${intentId}`;
    await boot();
  };

  btnStop.onclick = async () => { await apply("stop"); };
  btnTrail.onclick = async () => { await apply("trailing"); };
}

function renderTrackedSources(rows) {
  const el = document.getElementById("x-sources-list");
  if (!el) return;
  if (!rows || rows.length === 0) {
    el.innerHTML = `<div class="empty">No tracked X handles yet</div>`;
    return;
  }
  el.innerHTML = rows.slice(0, 50).map((r) => {
    const h = `@${String(r.handle || "").replace(/^@+/, "")}`;
    const copy = String(r.role_copy || "0") === "1" ? "copy:on" : "copy:off";
    const alpha = String(r.role_alpha || "0") === "1" ? "alpha:on" : "alpha:off";
    const active = String(r.active || "0") === "1" ? "active" : "inactive";
    const xapi = String(r.x_api_enabled || "0") === "1" ? "xapi:on" : "xapi:off";
    const weight = Number(r.source_weight || 1).toFixed(2);
    const notes = String(r.notes || "").trim();
    return `<div class="flow-item"><div><strong>${h}</strong> ${active}</div><div>${copy} | ${alpha} | ${xapi} | w=${weight}</div>${notes ? `<div>${notes}</div>` : ""}</div>`;
  }).join("");
}

function renderMainInputSources(rows) {
  const el = document.getElementById("input-sources-list-main");
  if (!el) return;
  if (!rows || rows.length === 0) {
    el.innerHTML = `<div class="empty">No input source controls yet</div>`;
    return;
  }
  const filtered = rows
    .filter((r) => {
      const key = String(r.source_key || "");
      return key.startsWith("family:") || key.startsWith("strategy:") || key.startsWith("source:") || key.startsWith("pipeline:");
    })
    .sort((a, b) => {
      const ak = String(a.source_key || "");
      const bk = String(b.source_key || "");
      return ak.localeCompare(bk);
    })
    .slice(0, 60);
  const grid = "210px 150px 60px 70px 70px 80px";
  const head = `<div class="row header" style="grid-template-columns:${grid}"><div>Input</div><div>Class</div><div>On</div><div>Manual</div><div>Auto</div><div>Effective</div></div>`;
  const body = filtered.map((r) => {
    const key = String(r.source_key || "");
    const name = friendlyInputName(key);
    const tip = inputHelpText(key);
    return `<div class="row" style="grid-template-columns:${grid}"><div title="${tip.replace(/\"/g, "&quot;")}">${name}<br/><span class="sub">${key}</span></div><div>${r.source_class || ""}</div><div>${Number(r.enabled || 0) === 1 ? "yes" : "no"}</div><div>${Number(r.manual_weight || 1).toFixed(2)}</div><div>${Number(r.auto_weight || 1).toFixed(2)}</div><div>${Number(r.effective_weight || 1).toFixed(2)}</div></div>`;
  }).join("");
  el.innerHTML = head + body;
}

function populateTradeReviewInputChoices(explain, allInputSources) {
  const select = document.getElementById("trade-review-input-key-select");
  if (!select) return;
  const fromExplain = ((explain?.candidate?.input_breakdown || []).map((x) => String(x.key || "").trim()).filter((x) => !!x));
  const fromAll = (allInputSources || [])
    .map((r) => String(r.source_key || "").trim())
    .filter((k) => k.startsWith("family:") || k.startsWith("strategy:") || k.startsWith("source:") || k.startsWith("pipeline:") || k.startsWith("x:"));
  const merged = Array.from(new Set([...fromExplain, ...fromAll])).sort((a, b) => a.localeCompare(b));
  const opts = [`<option value=\"\">Select input...</option>`].concat(
    merged.map((k) => `<option value="${k}">${friendlyInputName(k)} (${k})</option>`)
  );
  select.innerHTML = opts.join("");
  if (fromExplain.length > 0) {
    select.value = fromExplain[0];
  }
}

function renderTradeReplayExplain(explain) {
  const status = document.getElementById("trade-review-status");
  const explainEl = document.getElementById("trade-review-explain");
  const inputsEl = document.getElementById("trade-review-inputs");
  if (!status || !explainEl || !inputsEl) return;
  if (!explain || !explain.ok) {
    const err = explain?.error || "Trade not found";
    status.textContent = err;
    explainEl.innerHTML = "";
    inputsEl.innerHTML = "";
    return;
  }
  status.textContent = `Loaded ${explain.trade?.ticker || ""} (${explain.identifier || ""})`;
  explainEl.innerHTML = [
    ["Trade", `${explain.trade?.trade_id || ""} | route ${explain.trade?.route_id || 0}`],
    ["Outcome", `${Number(explain.outcome?.pnl || 0).toFixed(2)} USD | ${Number(explain.outcome?.pnl_percent || 0).toFixed(2)}% | ${explain.outcome?.resolution || "n/a"}`],
    ["Why (simple)", explain.simple_explanation || "n/a"],
  ].map(([k, v]) => `<div class="item"><span class="label">${k}</span><span>${v}</span></div>`).join("");

  const rows = (explain?.candidate?.input_breakdown || []).slice(0, 10).map((x) => ({
    input: `${friendlyInputName(x.key)} (${x.key})`,
    value: Number(x.value || 0).toFixed(3),
    weight: Number(x.weight || 0).toFixed(2),
    help: x.help || inputHelpText(x.key),
  }));
  if (!rows.length) {
    inputsEl.innerHTML = `<div class="empty">No candidate input breakdown found for this trade</div>`;
    return;
  }
  const grid = "280px 70px 70px 1fr";
  const head = `<div class="row header" style="grid-template-columns:${grid}"><div>Input</div><div>Value</div><div>Weight</div><div>What it means</div></div>`;
  const body = rows
    .map((r) => `<div class="row" style="grid-template-columns:${grid}"><div>${r.input}</div><div>${r.value}</div><div>${r.weight}</div><div>${r.help}</div></div>`)
    .join("");
  inputsEl.innerHTML = head + body;
}

function bindTradeReplayFeedback(allInputSources) {
  const idEl = document.getElementById("trade-review-identifier");
  const btnLoad = document.getElementById("btn-trade-review-load");
  const btnSubmit = document.getElementById("btn-trade-review-submit");
  const btnWeekly = document.getElementById("btn-trade-review-weekly");
  const status = document.getElementById("trade-review-status");
  const actionEl = document.getElementById("trade-review-action");
  const applyEl = document.getElementById("trade-review-apply-now");
  const notesEl = document.getElementById("trade-review-notes");
  const inputKeyEl = document.getElementById("trade-review-input-key-select");
  if (!idEl || !btnLoad || !btnSubmit || !btnWeekly || !status || !actionEl || !applyEl || !notesEl || !inputKeyEl) return;

  if (!btnLoad.dataset.wired) {
    btnLoad.dataset.wired = "1";
    btnLoad.onclick = async () => {
      const identifier = String(idEl.value || "").trim();
      if (!identifier) {
        status.textContent = "Enter a trade identifier first";
        return;
      }
      status.textContent = "Loading trade...";
      tradeReviewExplain = await fetchJsonSafe(`/api/trade-explain?identifier=${encodeURIComponent(identifier)}`, { ok: false, error: "load failed" });
      renderTradeReplayExplain(tradeReviewExplain);
      populateTradeReviewInputChoices(tradeReviewExplain, allInputSources || []);
    };
  }

  if (!btnSubmit.dataset.wired) {
    btnSubmit.dataset.wired = "1";
    btnSubmit.onclick = async () => {
      const identifier = String(idEl.value || "").trim();
      if (!identifier) {
        status.textContent = "Enter a trade identifier first";
        return;
      }
      const selectedKey = String(inputKeyEl.value || "").trim();
      if (!selectedKey) {
        status.textContent = "Choose an input to adjust";
        return;
      }
      status.textContent = "Saving feedback...";
      const payload = {
        identifier,
        feedback_action: String(actionEl.value || "neutral"),
        apply_now: String(applyEl.value || "1") === "1",
        notes: String(notesEl.value || "").trim(),
        selected_input_key: selectedKey,
      };
      const out = await postJson("/api/trade-feedback", payload);
      if (!out || !out.ok) {
        status.textContent = `Feedback failed: ${(out && out.error) || "unknown"}`;
        return;
      }
      const applied = out.applied?.updated || 0;
      status.textContent = out.apply_now
        ? `Saved feedback. Updated ${applied} input weight(s).`
        : `Saved feedback for weekly batch.`;
      if (out.apply_now) {
        await boot();
      }
    };
  }

  if (!btnWeekly.dataset.wired) {
    btnWeekly.dataset.wired = "1";
    btnWeekly.onclick = async () => {
      status.textContent = "Running weekly apply...";
      const out = await postJson("/api/trade-feedback/apply-weekly", { max_reviews: 400 });
      if (!out || !out.ok) {
        status.textContent = `Weekly apply failed: ${(out && out.error) || "unknown"}`;
        return;
      }
      status.textContent = `Weekly apply done: ${Number(out.applied_reviews || 0)} reviews, ${Number(out.updated_inputs || 0)} inputs updated.`;
      await boot();
    };
  }
}

function renderTickerProfiles(rows) {
  const el = document.getElementById("ticker-profiles-list");
  if (!el) return;
  if (!rows || rows.length === 0) {
    el.innerHTML = `<div class="empty">No ticker profiles configured</div>`;
    return;
  }
  const grid = "90px 70px 90px 170px 180px 70px 90px 180px";
  const head = `<div class="row header" style="grid-template-columns:${grid}"><div>Ticker</div><div>On</div><div>Pref Venue</div><div>Allowed</div><div>Required Inputs</div><div>Min</div><div>Notional</div><div>Notes</div></div>`;
  const body = rows.slice(0, 50).map((r) => {
    const allowed = Array.isArray(r.allowed_venues) ? r.allowed_venues.join(",") : String(r.allowed_venues_json || "");
    const req = Array.isArray(r.required_inputs) ? r.required_inputs.join(",") : String(r.required_inputs_json || "");
    return `<div class="row" style="grid-template-columns:${grid}"><div>${r.ticker || ""}</div><div>${Number(r.active || 0) === 1 ? "yes" : "no"}</div><div>${r.preferred_venue || "best"}</div><div>${allowed || "all"}</div><div>${req || "-"}</div><div>${Number(r.min_score || 0).toFixed(0)}</div><div>${Number(r.notional_override || 0).toFixed(2)}</div><div>${r.notes || ""}</div></div>`;
  }).join("");
  el.innerHTML = head + body;
}

function bindTickerProfileControls(rows) {
  const btn = document.getElementById("btn-ticker-profile-save");
  if (!btn) return;
  const tickerEl = document.getElementById("ticker-profile-ticker");
  const prefEl = document.getElementById("ticker-profile-pref-venue");
  const allowedEl = document.getElementById("ticker-profile-allowed");
  const reqEl = document.getElementById("ticker-profile-inputs");
  const minEl = document.getElementById("ticker-profile-min-score");
  const notionalEl = document.getElementById("ticker-profile-notional");
  const activeEl = document.getElementById("ticker-profile-active");
  const notesEl = document.getElementById("ticker-profile-notes");
  const status = document.getElementById("ticker-profile-status");

  btn.onclick = async () => {
    const ticker = String(tickerEl?.value || "").trim().toUpperCase();
    if (!ticker) {
      if (status) status.textContent = "ticker is required";
      return;
    }
    try {
      const allowed = String(allowedEl?.value || "")
        .split(",")
        .map((x) => x.trim().toLowerCase())
        .filter((x) => !!x);
      const requiredInputs = String(reqEl?.value || "")
        .split(",")
        .map((x) => x.trim().toLowerCase())
        .filter((x) => !!x);
      const payload = {
        ticker,
        active: String(activeEl?.value || "1") === "1",
        preferred_venue: String(prefEl?.value || "").trim().toLowerCase(),
        allowed_venues: allowed,
        required_inputs: requiredInputs,
        min_score: Number(minEl?.value || 0),
        notional_override: Number(notionalEl?.value || 0),
        notes: String(notesEl?.value || "").trim(),
      };
      const out = await postJson("/api/ticker-trade-profiles", payload);
      if (!out || !out.ok) throw new Error((out && out.error) || "save failed");
      if (status) status.textContent = `Saved ticker profile ${out.ticker}`;
      await boot();
    } catch (err) {
      if (status) status.textContent = `Save failed: ${(err && err.message) || err || "request error"}`;
    }
  };

  if (Array.isArray(rows) && rows.length > 0 && tickerEl && !String(tickerEl.value || "").trim()) {
    const first = rows[0];
    tickerEl.value = String(first.ticker || "");
    if (prefEl) prefEl.value = String(first.preferred_venue || "");
    if (allowedEl) {
      const allowed = Array.isArray(first.allowed_venues) ? first.allowed_venues.join(",") : String(first.allowed_venues_json || "");
      allowedEl.value = allowed || "stocks,crypto,prediction";
    }
    if (reqEl) {
      const req = Array.isArray(first.required_inputs) ? first.required_inputs.join(",") : String(first.required_inputs_json || "");
      reqEl.value = req || "";
    }
    if (minEl) minEl.value = String(first.min_score ?? 0);
    if (notionalEl) notionalEl.value = String(first.notional_override ?? 0);
    if (activeEl) activeEl.value = String(first.active ?? 1);
    if (notesEl) notesEl.value = String(first.notes || "");
  }
}

function bindMainInputSourceControls(rows) {
  const btn = document.getElementById("btn-input-source-save-main");
  if (!btn) return;
  const keyEl = document.getElementById("input-source-key-select-main");
  const wEl = document.getElementById("input-source-weight-main");
  const enEl = document.getElementById("input-source-enabled-main");
  const status = document.getElementById("input-source-status-main");
  const helpEl = document.getElementById("input-source-help-main");

  const options = (rows || [])
    .filter((r) => {
      const key = String(r.source_key || "");
      return key.startsWith("family:") || key.startsWith("strategy:") || key.startsWith("source:") || key.startsWith("pipeline:") || key.startsWith("x:");
    })
    .sort((a, b) => String(a.source_key || "").localeCompare(String(b.source_key || "")));

  if (keyEl) {
    const current = String(keyEl.value || "");
    const opts = ['<option value="">Select an input...</option>'].concat(
      options.map((r) => {
        const key = String(r.source_key || "");
        const label = friendlyInputName(key);
        return `<option value="${key}">${label} (${key})</option>`;
      })
    );
    keyEl.innerHTML = opts.join("");
    if (current && options.some((r) => String(r.source_key || "") === current)) {
      keyEl.value = current;
    }
  }

  const applySelected = () => {
    const selectedKey = String(keyEl?.value || "").trim();
    const selected = options.find((r) => String(r.source_key || "") === selectedKey);
    if (selected) {
      if (wEl) wEl.value = String(selected.manual_weight ?? 1.0);
      if (enEl) enEl.value = String(selected.enabled ?? 1);
    }
    if (helpEl) {
      const text = inputHelpText(selectedKey);
      helpEl.innerHTML = `<div class="item"><span class="label">${friendlyInputName(selectedKey || "Input")}</span><span>${text}</span></div>`;
    }
  };

  if (keyEl && !keyEl.dataset.wired) {
    keyEl.dataset.wired = "1";
    keyEl.addEventListener("change", applySelected);
  }

  btn.onclick = async () => {
    const sourceKey = String(keyEl?.value || "").trim();
    if (!sourceKey) {
      if (status) status.textContent = "Select an input first";
      return;
    }
    try {
      const selected = options.find((r) => String(r.source_key || "") === sourceKey);
      const payload = {
        source_key: sourceKey,
        source_label: selected?.source_label || friendlyInputName(sourceKey),
        source_class: selected?.source_class || (sourceKey.includes(":") ? sourceKey.split(":", 1)[0] : "custom"),
        manual_weight: Number(wEl?.value || 1),
        enabled: String(enEl?.value || "1") === "1",
      };
      const out = await postJson("/api/input-sources", payload);
      if (!out || !out.ok) throw new Error((out && out.error) || "save failed");
      if (status) status.textContent = `Saved ${sourceKey}`;
      await boot();
    } catch (err) {
      if (status) status.textContent = `Save failed: ${(err && err.message) || err || "request error"}`;
    }
  };

  if (Array.isArray(options) && options.length > 0 && keyEl && !String(keyEl.value || "").trim()) {
    const seed = options.find((r) => String(r.source_key || "").startsWith("family:liquidity")) || options[0];
    if (seed) {
      keyEl.value = String(seed.source_key || "");
    }
  }
  applySelected();
}

function bindTrackedSources(rows) {
  const btn = document.getElementById("btn-x-save");
  const status = document.getElementById("x-source-status");
  const handle = document.getElementById("x-handle");
  const weight = document.getElementById("x-weight");
  const copy = document.getElementById("x-copy");
  const alpha = document.getElementById("x-alpha");
  const active = document.getElementById("x-active");
  const xapi = document.getElementById("x-api-enabled");
  const notes = document.getElementById("x-notes");
  if (!btn || !handle) return;
  btn.onclick = async () => {
    try {
      const rawHandle = resolveHandleInput(["x-handle", "src-handle", "polyw-handle"], "btn-x-save");
      const normalizedHandle = normalizeXHandle(rawHandle);
      const payload = {
        handle: normalizedHandle || rawHandle,
        x_handle: rawHandle,
        source_weight: Number(weight?.value || 1),
        role_copy: String(copy?.value || "1") === "1",
        role_alpha: String(alpha?.value || "1") === "1",
        active: String(active?.value || "1") === "1",
        x_api_enabled: String(xapi?.value || "1") === "1",
        notes: (notes?.value || "").trim(),
      };
      if (!rawHandle) {
        if (status) status.textContent = `Handle is required (example: @NoLimitGains or x.com/NoLimitGains) [build ${UI_BUILD}]`;
        console.error("x-handle missing at submit", {
          build: UI_BUILD,
          xHandle: document.getElementById("x-handle")?.value || "",
          srcHandle: document.getElementById("src-handle")?.value || "",
          polywHandle: document.getElementById("polyw-handle")?.value || "",
        });
        return;
      }
      const out = await postJson("/api/tracked-sources", payload);
      if (out && out.ok) {
        if (status) status.textContent = `Saved @${payload.handle} to DB`;
        renderTrackedSources(out.sources || []);
        await boot();
      } else {
        if (status) status.textContent = `Save failed: ${(out && out.error) || "unknown"}`;
      }
    } catch (err) {
      if (status) status.textContent = `Save failed: ${(err && err.message) || err || "request error"}`;
    }
  };
  if (Array.isArray(rows) && rows.length > 0 && !handle.value) {
    const first = rows[0];
    if (weight) weight.value = String(first.source_weight ?? 1);
    if (copy) copy.value = String(first.role_copy ?? 1);
    if (alpha) alpha.value = String(first.role_alpha ?? 1);
    if (active) active.value = String(first.active ?? 1);
    if (xapi) xapi.value = String(first.x_api_enabled ?? 1);
  }
}

let booting = false;
async function boot() {
  if (booting) return;
  booting = true;
  try {
    setStatus("loading");
    pnlBreakdownCache = null;
    setupRefreshControls();
    bindPnlDrilldown();
    const [summary, systemHealth, readiness, controls, walletConfig, exOrders, polyOrders, portfolioSnapshot, tradeDecisions, awareness, performanceCurve, tradeClaimGuard, masterOverview, positionManagementIntents, trackedSources, learningMonitor, inputSources, tickerProfiles] = await Promise.all([
      fetchJsonSafe("/api/summary", {}),
      fetchJsonSafe("/api/system-health", { overall: "warn", checks: [] }),
      fetchJsonSafe("/api/signal-readiness", { score: 0, checks: [], blockers: [] }),
      fetchJsonSafe("/api/risk-controls", []),
      fetchJsonSafe("/api/wallet-config", []),
      fetchJsonSafe("/api/execution-orders?limit=80", []),
      fetchJsonSafe("/api/polymarket-orders?limit=80", []),
      fetchJsonSafe("/api/portfolio-snapshot", {}),
      fetchJsonSafe("/api/recent-trade-decisions?limit=30", []),
      fetchJsonSafe("/api/agent-awareness", { overall: "warn", checks: [], blockers: [], warnings: [] }),
      fetchJsonSafe("/api/performance-curve", { by_time: [], by_trade: [] }),
      fetchJsonSafe("/api/trade-claim-guard", { state: "bad", trade_ready: false, checks: [], blockers: ["endpoint unavailable"], warnings: [] }),
      fetchJsonSafe("/api/master-overview", {}),
      fetchJsonSafe("/api/position-management-intents?limit=120", []),
      fetchJsonSafe("/api/tracked-sources", []),
      fetchJsonSafe("/api/learning-monitor", {}),
      fetchJsonSafe("/api/input-sources", []),
      fetchJsonSafe("/api/ticker-trade-profiles", []),
    ]);

    runUiStep("bindControls", () => bindControls(controls));
    runUiStep("bindPositionPlanControls", () => bindPositionPlanControls(controls));
    runUiStep("bindPositionProtectionActions", () => bindPositionProtectionActions(positionManagementIntents || [], portfolioSnapshot || {}, controls));
    runUiStep("bindTrackedSources", () => bindTrackedSources(trackedSources || []));
    runUiStep("bindMainInputSourceControls", () => bindMainInputSourceControls(inputSources || []));
    runUiStep("bindTradeReplayFeedback", () => bindTradeReplayFeedback(inputSources || []));
    runUiStep("bindTickerProfileControls", () => bindTickerProfileControls(tickerProfiles || []));
    runUiStep("bindCurveButtons", () => bindCurveButtons(performanceCurve || {}));

    runUiStep("renderHero", () => renderHero(summary, controls));
    runUiStep("renderPulse", () => renderPulse(systemHealth, readiness, controls));
    runUiStep("renderHealthOverview", () => renderHealthOverview(systemHealth, readiness, learningMonitor || {}, masterOverview || {}));
    runUiStep("renderAlerts", () => renderAlerts(systemHealth, readiness, awareness, tradeClaimGuard));
    runUiStep("renderExecutionReadiness", () => renderExecutionReadiness(walletConfig, awareness, tradeClaimGuard));
    runUiStep("renderFlow", () => renderFlow(exOrders, polyOrders));
    runUiStep("renderPortfolio", () => renderPortfolio(portfolioSnapshot));
    runUiStep("renderTradeDecisions", () => renderTradeDecisions(tradeDecisions));
    runUiStep("renderExecutionOpportunity", () => renderExecutionOpportunity(masterOverview || {}, learningMonitor || {}));
    runUiStep("renderPositionPlan", () => renderPositionPlan(positionManagementIntents || []));
    runUiStep("renderLearningMonitor", () => renderLearningMonitor(learningMonitor || {}));
    runUiStep("renderPerformanceCurve", () => renderPerformanceCurve(performanceCurve || {}));
    runUiStep("renderRiskControls", () => {
      renderTable("risk-controls", controls, ["Key", "Value", "Updated"], ["key", "value", "updated_at"]);
    });
    runUiStep("renderTrackedSources", () => renderTrackedSources(trackedSources || []));
    runUiStep("renderMainInputSources", () => renderMainInputSources(inputSources || []));
    runUiStep("renderTickerProfiles", () => renderTickerProfiles(tickerProfiles || []));

    const topState = (systemHealth && systemHealth.overall) || "warn";
    const awareState = (awareness && awareness.overall) || "warn";
    const guardState = (tradeClaimGuard && tradeClaimGuard.state) || "warn";
    const merged = topState === "bad" || awareState === "bad" || guardState === "bad"
      ? "bad"
      : (topState === "warn" || awareState === "warn" || guardState === "warn" ? "warn" : "good");
    setStatus("online", merged === "good" ? "good" : (merged === "warn" ? "warn" : "bad"));
  } catch (err) {
    console.error(err);
    setStatus("offline", "bad");
  } finally {
    booting = false;
  }
}

boot();
