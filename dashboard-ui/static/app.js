async function fetchJson(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${url} failed: ${res.status}`);
  return res.json();
}

const UI_BUILD = "20260227b";

function escHtml(s) {
  return String(s ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}

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

function renderExchangePnl(data) {
  const summaryEl = document.getElementById("exchange-pnl-summary");
  const closedEl = document.getElementById("exchange-closed-trades");
  const actionsEl = document.getElementById("exchange-agent-actions");
  if (!summaryEl) return;

  const exchanges = data.exchanges || {};
  const pnlColor = v => v > 0 ? "color:#4ade80" : v < 0 ? "color:#f87171" : "";

  // Per-exchange summary tiles
  summaryEl.innerHTML = Object.entries(exchanges).map(([key, ex]) => {
    const realized = ex.realized_pnl || 0;
    const unrealized = ex.unrealized_pnl || 0;
    const total = realized + unrealized;
    const openPositions = (ex.open_details || []).map(p =>
      `<span style="font-size:0.78em;opacity:0.7;margin-left:8px;">${p.symbol} ${p.side} ${p.unrealized_pnl_pct > 0 ? "+" : ""}${p.unrealized_pnl_pct}% ($${p.unrealized_pnl_usd}) · ${p.action || ""}</span>`
    ).join("");
    return `<div class="item" style="flex-direction:column;align-items:flex-start;gap:4px;padding:8px 0;border-bottom:1px solid #1e293b;">
      <div style="display:flex;gap:16px;align-items:center;">
        <span class="label">${ex.label}</span>
        <span style="${pnlColor(total)}">Total ${total >= 0 ? "+" : ""}$${total.toFixed(2)}</span>
        ${realized !== 0 ? `<span style="font-size:0.82em;opacity:0.7;">Realized $${realized.toFixed(2)}</span>` : ""}
        ${unrealized !== 0 ? `<span style="font-size:0.82em;opacity:0.7;${pnlColor(unrealized)}">Unrealized $${unrealized.toFixed(2)}</span>` : ""}
        <span style="font-size:0.8em;opacity:0.6;">${ex.trades_closed || 0} closed · ${ex.open_positions || 0} open · ${ex.win_rate || 0}% win rate</span>
      </div>
      ${openPositions ? `<div style="display:flex;flex-wrap:wrap;">${openPositions}</div>` : ""}
    </div>`;
  }).join("") || `<div class="item"><span>No exchange data available</span></div>`;

  // Closed trades table
  const closed = data.closed_trades || [];
  if (closedEl) {
    closedEl.innerHTML = closed.length ? `
      <div class="row header"><div>ID</div><div>Ticker</div><div>Side</div><div>Entry</div><div>Exit</div><div>P&amp;L</div><div>P&amp;L %</div><div>Closed</div></div>
      ${closed.map(t => {
        const id = t.lookup_id || t.route_id || (t.trade_id||"").slice(0,12) || "—";
        return `<div class="row">
          <div style="font-size:0.78em;opacity:0.7;cursor:pointer;" title="Click to look up" onclick="document.getElementById('id-lookup-input').value='${id}';document.getElementById('btn-id-lookup').click();">${id}</div>
          <div><b>${t.ticker}</b></div>
          <div>${t.side}</div>
          <div>$${Number(t.entry_price||0).toFixed(2)}</div>
          <div>$${Number(t.exit_price||0).toFixed(2)}</div>
          <div style="${pnlColor(t.pnl)}">$${Number(t.pnl||0).toFixed(2)}</div>
          <div style="${pnlColor(t.pnl_percent)}">${Number(t.pnl_percent||0).toFixed(2)}%</div>
          <div style="font-size:0.78em;opacity:0.7;">${(t.closed_at||"").slice(0,10)}</div>
        </div>`;
      }).join("")}` : `<div class="empty">No closed trades</div>`;
  }

  // Agent actions
  const actions = data.agent_actions || [];
  const summaryLabel = document.getElementById("agent-actions-summary");
  if (summaryLabel) summaryLabel.textContent = `Actions (${actions.length})`;
  if (actionsEl) {
    const typeIcon = t => ({
      stop_placed: "🛑", take_profit_alert: "🎯", order_filled: "✅",
      reassess_tighten: "⚠️", reassess_exit: "🔴", reassess_take_profit: "💰",
      veto_hold: "🛡️",
    }[t] || "•");
    actionsEl.innerHTML = actions.map(a => `
      <div class="flow-item" style="padding:5px 0;border-bottom:1px solid #1e293b;">
        <span style="font-size:1em;margin-right:6px;">${typeIcon(a.action_type)}</span>
        <span><b>${a.symbol}</b> ${a.side || ""} · <span style="opacity:0.7;font-size:0.82em;">${a.description}</span></span>
        <span style="float:right;font-size:0.75em;opacity:0.5;">${(a.acted_at||"").slice(11,16)} ${(a.acted_at||"").slice(0,10)}</span>
      </div>`).join("") || `<div class="empty">No agent actions yet</div>`;
  }
}

function setupIdLookup() {
  const input = document.getElementById("id-lookup-input");
  const btn = document.getElementById("btn-id-lookup");
  const statusEl = document.getElementById("id-lookup-status");
  const resultsEl = document.getElementById("id-lookup-results");
  if (!btn || btn.dataset.wired) return;
  btn.dataset.wired = "1";

  // Generation counter — incremented on every new lookup so stale async
  // callbacks from a previous call do nothing and don't corrupt the DOM.
  let gen = 0;

  const doLookup = async () => {
    const q = (input?.value || "").trim();
    if (!q) return;
    const myGen = ++gen;
    statusEl.textContent = "Looking up…";
    resultsEl.innerHTML = "";
    try {
      const data = await fetchJsonSafe(`/api/id-lookup?id=${encodeURIComponent(q)}`, {});
      if (myGen !== gen) return; // a newer lookup started — abort
      if (!data.ok || !data.results?.length) {
        statusEl.textContent = `No results for "${q}"`;
        return;
      }
      statusEl.textContent = `${data.results.length} result(s) for "${q}"`;

      // Extract route_id to fetch full trade explanation
      const routeResult = data.results.find(r => r.route_id || r.type === "trade_by_route");
      const routeId = routeResult?.route_id;

      // Render basic results first
      resultsEl.innerHTML = data.results.map(r => {
        if (r.type === "intent" || r.type === "intent_by_ticker") {
          let details = "";
          try {
            const d = JSON.parse(r.details || "{}");
            if (d.signals) {
              const sigs = Object.entries(d.signals)
                .filter(([k]) => k !== "net")
                .map(([k, v]) => `${k}: ${v.score > 0 ? "+" : ""}${v.score} (${v.reason})`)
                .join(" · ");
              details = `net=${d.net_score} | ${sigs}`;
            } else if (d.reason) {
              details = d.reason;
            }
          } catch {}
          return `<div style="padding:8px 0;border-bottom:1px solid #1e293b;">
            <div><span class="label">intent #${r.id}</span> <b>${r.symbol||"—"}</b> ${r.side||""} · <code>${r.status}</code> · ${(r.created_at||"").slice(0,16)}</div>
            ${details ? `<div style="font-size:0.82em;opacity:0.7;margin-top:4px;">${details}</div>` : ""}
          </div>`;
        }
        if (r.type === "trade" || r.type === "trade_by_route") {
          const pnl = r.pnl_percent != null ? ` · PnL <b style="${Number(r.pnl_percent)>=0?'color:#4ade80':'color:#f87171'}">${Number(r.pnl_percent).toFixed(2)}%</b>` : "";
          return `<div style="padding:8px 0;border-bottom:1px solid #1e293b;">
            <span class="label">${r.route_id ? `route #${r.route_id}` : "trade"}</span>
            <b>${r.ticker||"—"}</b> ${r.entry_side||""} · <code>${r.status}</code> · entry $${r.entry_price||"—"}${pnl} · ${(r.entry_date||"").slice(0,10)}
          </div>`;
        }
        return "";
      }).join("");

      // If we have a route_id, fetch and render the full trade explanation
      if (routeId) {
        const loadId = `te-loading-${myGen}`;
        resultsEl.innerHTML += `<div id="${loadId}" style="opacity:0.5;padding:8px 0;">Loading signal breakdown…</div>`;
        const ex = await fetchJsonSafe(`/api/trade-explain?identifier=${routeId}`, {});
        if (myGen !== gen) return; // stale — a newer lookup took over
        document.getElementById(loadId)?.remove();

        if (ex && ex.ok) {
          const c = ex.candidate || {};
          const rt = ex.route || {};
          const outcome = ex.outcome || {};
          const inputs = (c.input_breakdown || []);
          const pnlColor = outcome.pnl_percent >= 0 ? "color:#4ade80" : "color:#f87171";

          resultsEl.innerHTML += `
            <div style="margin-top:12px;padding:12px;background:#0f172a;border-radius:6px;border:1px solid #1e293b;">
              <div style="font-size:0.95em;line-height:1.6;margin-bottom:10px;">${ex.simple_explanation || ""}</div>

              <div style="display:flex;gap:16px;flex-wrap:wrap;margin-bottom:10px;font-size:0.82em;">
                <span>Score <b>${Number(rt.score||0).toFixed(1)}</b></span>
                <span>Source <b>${rt.source_tag||"—"}</b></span>
                <span>Direction <b>${rt.direction||"—"}</b></span>
                <span>Decision <b>${rt.decision||"—"}</b></span>
                ${outcome.resolution ? `<span style="${pnlColor}">Outcome <b>${outcome.resolution?.toUpperCase()} ${Number(outcome.pnl_percent||0).toFixed(2)}%</b></span>` : ""}
              </div>

              ${inputs.length ? `
              <div style="font-size:0.82em;font-weight:600;opacity:0.6;margin-bottom:4px;">INPUTS THAT TRIGGERED THIS TRADE</div>
              ${inputs.map(inp => {
                const isPipeline = inp.key === "family:pipeline";
                const pipeBreakdown = isPipeline ? (c.pipeline_breakdown || []) : [];
                const evItems = isPipeline ? (c.evidence_items || []) : [];
                // parse non-pipeline evidence items (external + liquidity_map)
                const evExtra = evItems.filter(e => !e.startsWith("pipeline:")).map(e => {
                  if (e.startsWith("liquidity_map:")) {
                    const parts = e.replace("liquidity_map:","").split(":");
                    const rr = (parts[1]||"").replace("rr=","");
                    return `<div style="padding:3px 0 3px 12px;font-size:0.82em;border-left:2px solid #0ea5e9;margin:2px 0;opacity:0.8;">
                      📍 Liquidity Map: <b>${parts[0]||e}</b>${rr ? ` · R:R <b>${rr}</b>` : ""}
                    </div>`;
                  }
                  if (e.startsWith("external:")) {
                    return `<div style="padding:3px 0 3px 12px;font-size:0.82em;border-left:2px solid #8b5cf6;margin:2px 0;opacity:0.7;">
                      🌐 External: ${e.replace("external:","").replace(/:/g," › ")}
                    </div>`;
                  }
                  return `<div style="padding:3px 0 3px 12px;font-size:0.82em;opacity:0.6;margin:2px 0;">${e}</div>`;
                }).join("");
                const pipeHtml = pipeBreakdown.length ? `
                  <details style="margin-top:4px;">
                    <summary style="font-size:0.82em;cursor:pointer;opacity:0.7;padding:2px 0;">▶ ${pipeBreakdown.length} strategy sub-signal${pipeBreakdown.length>1?"s":""} fired</summary>
                    <div style="margin-top:4px;">
                    ${pipeBreakdown.map(p => `
                      <div style="padding:5px 0 5px 12px;border-left:2px solid #22c55e;margin:3px 0;">
                        <div style="display:flex;gap:12px;align-items:baseline;flex-wrap:wrap;">
                          <span style="font-weight:600;font-size:0.85em;">${p.pipeline_id}</span>
                          <span style="font-size:0.8em;opacity:0.6;">${p.direction||""}</span>
                          <span style="font-size:0.85em;">score <b>${Number(p.score||0).toFixed(1)}</b></span>
                          <span style="font-size:0.8em;opacity:0.5;">${(p.generated_at||"").slice(0,16)}</span>
                        </div>
                        <div style="font-size:0.8em;opacity:0.7;margin-top:2px;">${p.rationale||""}</div>
                        ${p.source ? `<div style="font-size:0.75em;opacity:0.4;margin-top:1px;">src: ${p.source.length>80?p.source.slice(0,80)+"…":p.source}</div>` : ""}
                      </div>`).join("")}
                    </div>
                  </details>` : "";
                return `<div style="padding:5px 0;border-bottom:1px solid #1e293b;">
                  <div style="display:flex;align-items:center;gap:10px;">
                    <span style="min-width:160px;opacity:0.8;">${inp.name||inp.key}</span>
                    <div style="flex:1;background:#1e293b;border-radius:3px;height:6px;">
                      <div style="width:${Math.min(100, Math.round((inp.value||0)*200))}%;background:#3b82f6;height:6px;border-radius:3px;"></div>
                    </div>
                    <span style="min-width:50px;text-align:right;">${Number(inp.value||0).toFixed(3)}</span>
                    <span style="opacity:0.5;min-width:60px;">wt ${Number(inp.weight||1).toFixed(2)}</span>
                    <span style="opacity:0.4;font-size:0.9em;max-width:220px;">${inp.help||""}</span>
                  </div>
                  ${pipeHtml}${evExtra}
                </div>`;
              }).join("")}` : ""}

              ${c.confirmations > 0 ? `<div style="font-size:0.82em;opacity:0.6;margin-top:6px;">Confirmations: <b>${c.confirmations}</b> · Pattern: <b>${c.pattern_type||"none"}</b> (${Number(c.pattern_score||0).toFixed(2)}) · Ext confidence: <b>${Number(c.external_confidence||0).toFixed(2)}</b></div>` : ""}
              ${c.rationale ? `<div style="margin-top:8px;font-size:0.78em;opacity:0.5;font-family:monospace;">${c.rationale}</div>` : ""}

              ${(() => {
                const cards = [];
                // Trigger Checklist
                const pg = ex.premium_gate;
                if (pg) {
                  const check = v => v ? '<span style="color:#4ade80;">&#10003;</span>' : '<span style="color:#f87171;">&#10007;</span>';
                  cards.push(`<div style="margin-top:10px;padding:8px;background:#1e293b;border-radius:4px;">
                    <div style="font-size:0.82em;font-weight:600;opacity:0.7;margin-bottom:4px;">TRIGGER CHECKLIST</div>
                    <div style="display:flex;gap:12px;font-size:0.82em;flex-wrap:wrap;">
                      <span>${check(pg.kelly_hit)} Kyle Williams</span>
                      <span>${check(pg.liquidity_hit)} Liquidity</span>
                      <span>${check(pg.momentum_hit)} Momentum</span>
                      <span style="opacity:0.6;">Hits: <b>${pg.hits}/3</b></span>
                      <span style="${pg.passed?'color:#4ade80':'color:#f87171'}">${pg.passed?'PASSED':'BLOCKED'}</span>
                    </div>
                  </div>`);
                }
                // Kelly Verdict
                const k = ex.kelly;
                if (k) {
                  const vColors = {pass:'#4ade80',skip:'#f87171',warn:'#fbbf24',warmup:'#94a3b8',budget_exceeded:'#f87171'};
                  cards.push(`<div style="margin-top:8px;padding:8px;background:#1e293b;border-radius:4px;">
                    <div style="font-size:0.82em;font-weight:600;opacity:0.7;margin-bottom:4px;">KELLY VERDICT</div>
                    <div style="display:flex;gap:12px;font-size:0.82em;flex-wrap:wrap;">
                      <span style="color:${vColors[k.verdict]||'#94a3b8'};font-weight:700;">${(k.verdict||'—').toUpperCase()}</span>
                      <span>Fraction <b>${Number(k.fraction||0).toFixed(3)}</b></span>
                      <span>Win prob <b>${Number(k.win_prob||0).toFixed(2)}</b></span>
                      <span>Payout <b>${Number(k.payout_ratio||0).toFixed(2)}</b></span>
                      <span>EV <b>${Number(k.ev_percent||0).toFixed(1)}%</b></span>
                      <span style="opacity:0.6;">n=${k.sample_size||0}</span>
                    </div>
                    ${k.verdict_reason ? `<div style="font-size:0.75em;opacity:0.5;margin-top:3px;">${k.verdict_reason}</div>` : ''}
                  </div>`);
                }
                // Source Stats
                const ss = ex.source_stats;
                if (ss) {
                  const wrColor = ss.win_rate >= 55 ? '#4ade80' : ss.win_rate <= 45 ? '#f87171' : '#fbbf24';
                  cards.push(`<div style="margin-top:8px;padding:8px;background:#1e293b;border-radius:4px;">
                    <div style="font-size:0.82em;font-weight:600;opacity:0.7;margin-bottom:4px;">SOURCE STATS (${rt.source_tag||'—'})</div>
                    <div style="display:flex;gap:12px;font-size:0.82em;">
                      <span>Win rate <b style="color:${wrColor}">${Number(ss.win_rate||0).toFixed(1)}%</b></span>
                      <span>Samples <b>${ss.sample_size||0}</b></span>
                      <span>Avg PnL <b>${Number(ss.avg_pnl_percent||0).toFixed(2)}%</b></span>
                    </div>
                  </div>`);
                }
                // Position Intents
                const pi = ex.position_intents || [];
                if (pi.length) {
                  const intentRows = pi.map(i => {
                    const statusBadge = i.status === 'submitted_stop' ? '<span style="color:#4ade80;">submitted</span>'
                      : i.status === 'alert_sent' ? '<span style="color:#fbbf24;">alert</span>'
                      : i.status === 'failed' ? '<span style="color:#f87171;">failed</span>'
                      : `<span style="opacity:0.6;">${i.status}</span>`;
                    return `<div style="display:flex;gap:8px;font-size:0.8em;padding:3px 0;border-bottom:1px solid #0f172a;">
                      <span style="opacity:0.5;min-width:120px;">${(i.created_at||'').slice(0,16)}</span>
                      <span style="min-width:50px;">${i.side||''}</span>
                      <span style="min-width:80px;">${statusBadge}</span>
                      <span style="opacity:0.6;flex:1;">${(i.details||'').slice(0,100)}</span>
                    </div>`;
                  }).join('');
                  cards.push(`<div style="margin-top:8px;padding:8px;background:#1e293b;border-radius:4px;">
                    <div style="font-size:0.82em;font-weight:600;opacity:0.7;margin-bottom:4px;">POSITION PROTECTION (${pi.length} intents)</div>
                    ${intentRows}
                  </div>`);
                }
                return cards.join('');
              })()}
            </div>`;
        }
      }

    } catch (e) {
      if (myGen === gen) statusEl.textContent = `Error: ${e.message}`;
    }
  };

  btn.onclick = doLookup;
  input?.addEventListener("keydown", e => { if (e.key === "Enter") doLookup(); });

  // Quick-select dropdown: populate when exchange-pnl loads, selecting fills the input
  const quickSel = document.getElementById("id-lookup-quick");
  if (quickSel) {
    quickSel.addEventListener("change", () => {
      const v = quickSel.value;
      if (v && input) { input.value = v; doLookup(); quickSel.value = ""; }
    });
  }
}

function populateIdLookupDropdown(exchangeData) {
  const winsGroup = document.getElementById("id-lookup-wins");
  const lossesGroup = document.getElementById("id-lookup-losses");
  const openGroup = document.getElementById("id-lookup-open");
  if (!winsGroup || !lossesGroup) return;

  const closed = (exchangeData.closed_trades || []);
  const wins = closed.filter(t => t.pnl > 0).sort((a, b) => b.pnl_percent - a.pnl_percent);
  // Only include actual entry positions as losses (buy entries, or routed sell/short positions)
  // Excludes closing-leg orders (alpaca_unmatched :close: entries, sell-side without route)
  const losses = closed.filter(t => t.pnl <= 0 && (t.side === 'buy' || t.route_id != null))
    .sort((a, b) => a.pnl_percent - b.pnl_percent);

  winsGroup.innerHTML = wins.map(t => {
    const id = t.lookup_id || t.route_id || t.trade_id || t.ticker;
    const label = `${t.ticker} ${t.side} +${t.pnl_percent.toFixed(2)}% ($${t.pnl.toFixed(2)}) — ${id}`;
    return `<option value="${id}">${label}</option>`;
  }).join("");

  lossesGroup.innerHTML = losses.map(t => {
    const id = t.lookup_id || t.route_id || t.trade_id || t.ticker;
    const label = `${t.ticker} ${t.side} ${t.pnl_percent.toFixed(2)}% ($${t.pnl.toFixed(2)}) — ${id}`;
    return `<option value="${id}">${label}</option>`;
  }).join("");

  // Open positions from live_positions
  const livePosAll = Object.values(exchangeData.live_positions || {}).flat();
  if (openGroup) {
    openGroup.innerHTML = livePosAll.map(p => {
      const id = p.symbol;
      const pnl = p.unrealized_pnl_pct >= 0 ? `+${p.unrealized_pnl_pct}%` : `${p.unrealized_pnl_pct}%`;
      return `<option value="${id}">${p.symbol} ${p.side} ${pnl} (${p.venue || "HL"})</option>`;
    }).join("");
  }
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

function renderPremiumGate(controls) {
  const c = controlMap(controls);
  const get = (k, def) => String(c[k] !== undefined ? c[k] : def);

  // Populate checkboxes
  const cb = (id, key, def) => {
    const el = document.getElementById(id);
    if (el) el.checked = get(key, def) === "1";
  };
  cb("pg-kw-stocks",  "premium_gate_kw_stocks",  "1");
  cb("pg-kw-crypto",  "premium_gate_kw_crypto",   "0");
  cb("pg-liq-stocks", "premium_gate_liq_stocks",  "1");
  cb("pg-liq-crypto", "premium_gate_liq_crypto",  "1");
  cb("pg-mom-stocks", "premium_gate_mom_stocks",  "1");
  cb("pg-mom-crypto", "premium_gate_mom_crypto",  "1");

  // Populate min-required selectors
  const sel = (id, key) => {
    const el = document.getElementById(id);
    if (el) el.value = get(key, "0");
  };
  sel("pg-stocks-min", "premium_gate_stocks_min");
  sel("pg-crypto-min", "premium_gate_crypto_min");

  // Save button
  const btn = document.getElementById("btn-premium-gate-save");
  const status = document.getElementById("premium-gate-status");
  if (!btn) return;
  btn.onclick = async () => {
    const val = (id) => document.getElementById(id)?.checked ? "1" : "0";
    const sval = (id) => document.getElementById(id)?.value ?? "0";
    const updates = {
      premium_gate_kw_stocks:  val("pg-kw-stocks"),
      premium_gate_kw_crypto:  val("pg-kw-crypto"),
      premium_gate_liq_stocks: val("pg-liq-stocks"),
      premium_gate_liq_crypto: val("pg-liq-crypto"),
      premium_gate_mom_stocks: val("pg-mom-stocks"),
      premium_gate_mom_crypto: val("pg-mom-crypto"),
      premium_gate_stocks_min: sval("pg-stocks-min"),
      premium_gate_crypto_min: sval("pg-crypto-min"),
    };
    if (status) status.textContent = "Saving…";
    const res = await postJson("/api/risk-controls", { updates });
    if (status) status.textContent = res.ok !== false
      ? "Saved. Will apply on next generate_trade_candidates run."
      : `Error: ${res.error || "save failed"}`;
    setTimeout(() => { if (status) status.textContent = ""; }, 4000);
  };
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
    const cat = String(r.kol_category || "stocks");
    const catColors = { stocks: "#60a5fa", crypto: "#fbbf24", polymarket: "#a78bfa", mixed: "#94a3b8" };
    const catBadge = `<span style="font-size:0.75em;padding:1px 6px;border-radius:4px;background:${catColors[cat] || "#94a3b8"}22;color:${catColors[cat] || "#94a3b8"};">${cat}</span>`;
    return `<div class="flow-item"><div><strong>${h}</strong> ${catBadge} ${active}</div><div>${copy} | ${alpha} | ${xapi} | w=${weight}</div>${notes ? `<div>${notes}</div>` : ""}</div>`;
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
      const catEl = document.getElementById("x-category");
      const payload = {
        handle: normalizedHandle || rawHandle,
        x_handle: rawHandle,
        source_weight: Number(weight?.value || 1),
        role_copy: String(copy?.value || "1") === "1",
        role_alpha: String(alpha?.value || "1") === "1",
        active: String(active?.value || "1") === "1",
        x_api_enabled: String(xapi?.value || "1") === "1",
        notes: (notes?.value || "").trim(),
        kol_category: (catEl?.value || "stocks"),
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
function renderSystemIntelligence(data) {
  const chartEl = document.getElementById("intel-chart");
  const statsEl = document.getElementById("intel-stats");
  const gateEl = document.getElementById("intel-gate");
  const barsEl = document.getElementById("intel-source-bars");

  // --- Panel 1: Rolling Sharpe + Win Rate dual-line chart ---
  if (chartEl) {
    const rolling = data.rolling || [];
    if (!rolling.length) {
      chartEl.innerHTML = `<div class="empty">Not enough resolved trades for rolling analysis</div>`;
      if (statsEl) statsEl.innerHTML = "";
    } else {
      const width = 860, height = 220, pad = 26;
      const sharpePts = rolling.map(r => ({ y: r.sharpe }));
      const winPts = rolling.map(r => ({ y: r.win_rate }));
      const sharpeResult = buildLinePath(sharpePts, width, height, pad);
      const winResult = buildLinePath(winPts, width, height, pad);

      // Sharpe line uses its own Y scale; win rate uses its own
      // We render two SVGs stacked or overlay with dual Y-axes
      // Simpler: render in same SVG with normalized Y (0..1 range)
      const allSharpe = rolling.map(r => r.sharpe);
      const allWin = rolling.map(r => r.win_rate);
      const sMin = Math.min(...allSharpe), sMax = Math.max(...allSharpe);
      const wMin = Math.min(...allWin), wMax = Math.max(...allWin);
      const sRange = sMax === sMin ? 1 : sMax - sMin;
      const wRange = wMax === wMin ? 1 : wMax - wMin;
      const innerW = width - pad * 2, innerH = height - pad * 2;
      const toX = (i) => pad + (rolling.length <= 1 ? innerW / 2 : (i / (rolling.length - 1)) * innerW);
      const toYS = (v) => pad + (sMax - v) / sRange * innerH;
      const toYW = (v) => pad + (wMax - v) / wRange * innerH;

      const sharpePath = rolling.map((r, i) => `${i === 0 ? "M" : "L"} ${toX(i).toFixed(2)} ${toYS(r.sharpe).toFixed(2)}`).join(" ");
      const winPath = rolling.map((r, i) => `${i === 0 ? "M" : "L"} ${toX(i).toFixed(2)} ${toYW(r.win_rate).toFixed(2)}`).join(" ");

      chartEl.innerHTML = `
        <svg viewBox="0 0 ${width} ${height}" preserveAspectRatio="none">
          <line class="perf-axis" x1="${pad}" y1="${height - pad}" x2="${width - pad}" y2="${height - pad}" />
          <line class="perf-axis" x1="${pad}" y1="${pad}" x2="${pad}" y2="${height - pad}" />
          <path d="${sharpePath}" fill="none" stroke="#4caf50" stroke-width="2" />
          <path d="${winPath}" fill="none" stroke="#2196f3" stroke-width="2" />
          <text class="perf-label" x="${pad}" y="${pad - 6}" fill="#4caf50">Sharpe ${sMax.toFixed(2)}</text>
          <text class="perf-label" x="${pad + 120}" y="${pad - 6}" fill="#2196f3">WR ${wMax.toFixed(1)}%</text>
          <text class="perf-label" x="${pad}" y="${height - 8}" fill="#4caf50">${sMin.toFixed(2)}</text>
          <text class="perf-label" x="${pad + 120}" y="${height - 8}" fill="#2196f3">${wMin.toFixed(1)}%</text>
        </svg>
      `;

      if (statsEl) {
        const cur = rolling[rolling.length - 1] || {};
        const prev = rolling.length > 12 ? rolling[rolling.length - 13] : rolling[0];
        const sharpeTrend = cur.sharpe > (prev?.sharpe || 0) ? "\u2191" : (cur.sharpe < (prev?.sharpe || 0) ? "\u2193" : "\u2192");
        const wrTrend = cur.win_rate > (prev?.win_rate || 0) ? "\u2191" : (cur.win_rate < (prev?.win_rate || 0) ? "\u2193" : "\u2192");
        statsEl.innerHTML = [
          ["Sharpe", `${cur.sharpe.toFixed(3)} ${sharpeTrend}`],
          ["Win Rate", `${cur.win_rate.toFixed(1)}% ${wrTrend}`],
          ["Window", "30 trades"],
          ["Data Points", String(rolling.length)],
          ["Trades Covered", String(cur.idx || 0)],
        ].map(([k, v]) => `<div class="item"><span class="label">${k}</span><span>${v}</span></div>`).join("");
      }
    }
  }

  // --- Panel 2: Quant Gate Proof ---
  if (gateEl) {
    const gate = data.gate_effectiveness || {};
    const passed = gate.passed || {};
    const rejected = gate.rejected || {};
    if (!passed.n && !rejected.n) {
      gateEl.innerHTML = `<div class="empty">No gate data yet</div>`;
    } else {
      const delta = (passed.win_rate || 0) - (rejected.win_rate || 0);
      const deltaClass = delta > 0 ? "good" : (delta < 0 ? "bad" : "");
      const deltaLabel = delta > 0
        ? `Gate adds +${delta.toFixed(1)}% win rate`
        : (delta < 0 ? `Gate NOT helping (${delta.toFixed(1)}%)` : "No difference");
      gateEl.innerHTML = `
        <div class="item"><span class="label">Passed</span><span>${passed.n || 0} trades, ${(passed.win_rate || 0).toFixed(1)}% WR, ${(passed.avg_pnl_pct || 0).toFixed(2)}% avg</span></div>
        <div class="item"><span class="label">Rejected</span><span>${rejected.n || 0} trades, ${(rejected.win_rate || 0).toFixed(1)}% WR, ${(rejected.avg_pnl_pct || 0).toFixed(2)}% avg</span></div>
        <div class="item ${deltaClass}" style="font-weight:600;"><span class="label">Delta</span><span>${deltaLabel}</span></div>
      `;
    }
  }

  // --- Panel 3: Source P&L Contribution horizontal bars ---
  if (barsEl) {
    const sources = data.source_contribution || [];
    if (!sources.length) {
      barsEl.innerHTML = `<div class="empty">No source contribution data</div>`;
    } else {
      const maxAbs = Math.max(...sources.map(s => Math.abs(s.total_pnl_pct)), 0.01);
      const barHeight = 28;
      const labelWidth = 160;
      const barAreaWidth = 500;
      const svgWidth = labelWidth + barAreaWidth + 80;
      const svgHeight = sources.length * barHeight + 10;

      const bars = sources.map((s, i) => {
        const pct = s.total_pnl_pct || 0;
        const barW = Math.abs(pct) / maxAbs * barAreaWidth;
        const fill = pct >= 0 ? "#4caf50" : "#ef5350";
        const y = i * barHeight + 4;
        const barX = pct >= 0 ? labelWidth : labelWidth - barW;
        return `
          <text x="${2}" y="${y + 18}" fill="#ccc" font-size="12">${s.source_tag || "unknown"}</text>
          <rect x="${labelWidth}" y="${y + 4}" width="${barW.toFixed(1)}" height="18" fill="${fill}" rx="2" />
          <text x="${labelWidth + barW + 4}" y="${y + 18}" fill="#aaa" font-size="11">${pct >= 0 ? "+" : ""}${pct.toFixed(1)}% (${s.n})</text>
        `;
      }).join("");

      barsEl.innerHTML = `
        <svg viewBox="0 0 ${svgWidth} ${svgHeight}" width="100%" preserveAspectRatio="xMinYMin meet" style="margin-top:8px;">
          ${bars}
        </svg>
      `;
    }
  }
}

async function boot() {
  if (booting) return;
  booting = true;
  try {
    setStatus("loading");
    pnlBreakdownCache = null;
    setupRefreshControls();
    setupIdLookup();
    bindPnlDrilldown();
    fetchJsonSafe("/api/exchange-pnl", {}).then(d => { renderExchangePnl(d || {}); populateIdLookupDropdown(d || {}); });
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
    runUiStep("renderPremiumGate", () => renderPremiumGate(controls));
    runUiStep("renderTrackedSources", () => renderTrackedSources(trackedSources || []));
    runUiStep("renderMainInputSources", () => renderMainInputSources(inputSources || []));
    runUiStep("renderTickerProfiles", () => renderTickerProfiles(tickerProfiles || []));

    // Health Pulse + Signal Scorecard (non-blocking)
    fetchJsonSafe("/api/health-pulse", {}).then(d => renderHealthPulse(d || {}));
    fetchJsonSafe("/api/signal-scorecard", {}).then(d => renderSignalScorecard(d || {}));
    fetchJsonSafe("/api/weight-history?limit=30", {}).then(d => renderWeightHistory(d || {}));
    fetchJsonSafe("/api/system-intelligence", {}).then(d => renderSystemIntelligence(d || {}));
    fetchJsonSafe("/api/source-decay", {}).then(d => renderSourceDecay(d || {}));
    fetchJsonSafe("/api/x-consensus", {}).then(d => { renderXConsensus(d || {}); bindXConsensus(); });

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

function renderSignalScorecard(data) {
  const el = document.getElementById("signal-scorecard-table");
  if (!el) return;
  const sources = (data && data.sources) || [];
  if (!sources.length) { el.innerHTML = '<div style="opacity:0.5;padding:8px;">No scorecard data yet. Run candidate scoring first.</div>'; return; }
  const rows = sources.map(s => {
    const wr = s.candidate_win_rate != null ? s.candidate_win_rate : (s.win_rate || 0);
    const gradeColors = {green:'#4ade80',yellow:'#fbbf24',red:'#f87171',insufficient_data:'#64748b'};
    const gc = gradeColors[s.grade] || '#64748b';
    const trend7d = s.trend_7d_win_rate != null ? `${Number(s.trend_7d_win_rate).toFixed(1)}%` : '\u2014';
    const dirAcc = s.direction_accuracy != null ? `${Number(s.direction_accuracy).toFixed(1)}%` : '\u2014';
    const samples = s.candidate_sample_size || s.sample_size || 0;
    const avgPnl = s.candidate_avg_pnl_pct != null ? s.candidate_avg_pnl_pct : (s.avg_pnl_pct || 0);
    return `<tr style="border-bottom:1px solid #1e293b;">
      <td style="padding:4px 8px;font-weight:600;">${s.source_tag}</td>
      <td style="padding:4px 8px;text-align:center;color:${gc}">${Number(wr).toFixed(1)}%</td>
      <td style="padding:4px 8px;text-align:center;">${trend7d}</td>
      <td style="padding:4px 8px;text-align:center;">${samples}</td>
      <td style="padding:4px 8px;text-align:center;${avgPnl>=0?'color:#4ade80':'color:#f87171'}">${Number(avgPnl).toFixed(2)}%</td>
      <td style="padding:4px 8px;text-align:center;">${dirAcc}</td>
      <td style="padding:4px 8px;text-align:center;">${Number(s.auto_weight||1).toFixed(2)}</td>
      <td style="padding:4px 8px;text-align:center;"><span style="color:${gc};font-weight:700;">${(s.grade||'\u2014').toUpperCase()}</span></td>
    </tr>`;
  }).join('');
  el.innerHTML = `<table style="width:100%;border-collapse:collapse;font-size:0.85em;">
    <thead><tr style="opacity:0.7;">
      <th style="text-align:left;padding:4px 8px;">Source</th>
      <th style="text-align:center;padding:4px 8px;">Win Rate</th>
      <th style="text-align:center;padding:4px 8px;">7d Trend</th>
      <th style="text-align:center;padding:4px 8px;">Samples</th>
      <th style="text-align:center;padding:4px 8px;">Avg P&amp;L</th>
      <th style="text-align:center;padding:4px 8px;">Dir Acc</th>
      <th style="text-align:center;padding:4px 8px;">Weight</th>
      <th style="text-align:center;padding:4px 8px;">Grade</th>
    </tr></thead>
    <tbody>${rows}</tbody>
  </table>`;
}

function renderWeightHistory(data) {
  const el = document.getElementById("weight-history-table");
  if (!el) return;
  const changes = (data && data.changes) || [];
  if (!changes.length) { el.innerHTML = '<div style="opacity:0.5;padding:8px;">No weight changes recorded yet.</div>'; return; }
  const rows = changes.map(c => {
    const delta = c.new_auto_weight - c.old_auto_weight;
    const arrow = delta > 0 ? '<span style="color:#4ade80;">\u25B2</span>' : '<span style="color:#f87171;">\u25BC</span>';
    return `<tr style="border-bottom:1px solid #1e293b;">
      <td style="padding:3px 6px;font-size:0.8em;opacity:0.6;">${(c.changed_at||'').slice(0,16)}</td>
      <td style="padding:3px 6px;">${c.source_key}</td>
      <td style="padding:3px 6px;text-align:center;">${Number(c.old_auto_weight).toFixed(3)}</td>
      <td style="padding:3px 6px;text-align:center;">${arrow} ${Number(c.new_auto_weight).toFixed(3)}</td>
      <td style="padding:3px 6px;text-align:center;">${Number(c.win_rate).toFixed(1)}%</td>
      <td style="padding:3px 6px;text-align:center;opacity:0.6;">${c.sample_size}</td>
      <td style="padding:3px 6px;font-size:0.8em;opacity:0.5;">${c.reason||''}</td>
    </tr>`;
  }).join('');
  el.innerHTML = `<table style="width:100%;border-collapse:collapse;font-size:0.85em;">
    <thead><tr style="opacity:0.7;">
      <th style="text-align:left;padding:3px 6px;">Time</th>
      <th style="text-align:left;padding:3px 6px;">Source</th>
      <th style="text-align:center;padding:3px 6px;">Old</th>
      <th style="text-align:center;padding:3px 6px;">New</th>
      <th style="text-align:center;padding:3px 6px;">Win Rate</th>
      <th style="text-align:center;padding:3px 6px;">Samples</th>
      <th style="text-align:left;padding:3px 6px;">Reason</th>
    </tr></thead>
    <tbody>${rows}</tbody>
  </table>`;
}

// ── Health Pulse ──
function renderHealthPulse(data) {
  const el = document.getElementById("health-pulse");
  if (!el) return;
  const indicators = (data && data.indicators) || [];
  if (!indicators.length) {
    el.innerHTML = '<div class="empty">No health pulse data available.</div>';
    return;
  }

  const categoryLabels = {
    performance: "Performance",
    signal_quality: "Signal Quality",
    pipeline: "Pipeline Health",
    execution: "Execution",
  };
  const categoryOrder = ["performance", "signal_quality", "pipeline", "execution"];
  const statusColors = {
    green: "var(--accent)",
    yellow: "var(--warn)",
    red: "var(--danger)",
    info: "var(--muted)",
  };

  let html = "";
  let currentCat = "";
  const grouped = [];
  for (const cat of categoryOrder) {
    grouped.push(...indicators.filter(i => i.category === cat));
  }

  for (const ind of grouped) {
    if (ind.category !== currentCat) {
      currentCat = ind.category;
      html += '<div class="pulse-group-label">' + escHtml(categoryLabels[currentCat] || currentCat) + '</div>';
    }

    const valColor = statusColors[ind.status] || "var(--text)";
    const deltaHtml = ind.delta
      ? '<div class="pulse-ind-delta" style="color:' + (ind.delta.startsWith("+") || ind.delta.startsWith("\u25B2") ? "var(--accent)" : (ind.delta.startsWith("-") || ind.delta.startsWith("\u25BC") ? "var(--danger)" : "var(--muted)")) + ';">' + escHtml(ind.delta) + '</div>'
      : "";
    const sparkHtml = buildMiniSparkline(ind.sparkline || [], 60, 20);

    html += '<div class="pulse-ind">'
      + '<div class="pulse-ind-header">'
      +   '<span>' + escHtml(ind.label) + '</span>'
      +   '<span class="pulse-help">?</span>'
      +   '<span class="pulse-dot ' + escHtml(ind.status) + '"></span>'
      + '</div>'
      + '<div class="pulse-ind-body">'
      +   '<div>'
      +     '<div class="pulse-ind-value" style="color:' + valColor + ';">' + escHtml(ind.display) + '</div>'
      +     deltaHtml
      +   '</div>'
      +   (sparkHtml ? '<div>' + sparkHtml + '</div>' : '')
      + '</div>'
      + '<div class="pulse-ind-thresholds">' + escHtml(ind.thresholds) + '</div>'
      + '<div class="pulse-tooltip">' + escHtml(ind.tooltip) + '</div>'
      + '</div>';
  }

  el.innerHTML = html;
}

function buildMiniSparkline(series, w, h) {
  if (!series || series.length < 2) return "";
  const min = Math.min(...series);
  const max = Math.max(...series);
  const range = max === min ? 1 : max - min;
  const stepX = w / (series.length - 1);
  const pts = series.map((v, i) => {
    const x = (i * stepX).toFixed(1);
    const y = (h - ((v - min) / range) * h).toFixed(1);
    return `${i === 0 ? "M" : "L"} ${x} ${y}`;
  }).join(" ");
  const color = series[series.length - 1] >= series[0] ? "#4ade80" : "#f87171";
  return `<svg width="${w}" height="${h}" viewBox="0 0 ${w} ${h}" style="vertical-align:middle;"><path d="${pts}" fill="none" stroke="${color}" stroke-width="1.5" /></svg>`;
}

function renderSourceDecay(data) {
  const summaryEl = document.getElementById("source-health-summary");
  const listEl = document.getElementById("source-health-list");
  if (!summaryEl || !listEl) return;

  const sources = (data && data.sources) || [];
  const summary = (data && data.summary) || {};

  if (!sources.length) {
    summaryEl.innerHTML = '<div class="item" style="opacity:0.5;">No source decay data yet.</div>';
    listEl.innerHTML = "";
    return;
  }

  // Summary line
  const parts = [];
  if (summary.healthy) parts.push(`<span style="color:#4ade80;">${summary.healthy} healthy</span>`);
  if (summary.decaying) parts.push(`<span style="color:#f87171;">${summary.decaying} decaying</span>`);
  if (summary.improving) parts.push(`<span style="color:#38bdf8;">${summary.improving} improving</span>`);
  summaryEl.innerHTML = `<div class="item"><span class="label">Sources</span><span>${parts.join(" &bull; ")}</span></div>`;

  // Per-source cards
  const cards = sources.map(s => {
    const badgeColors = { decaying: "#f87171", improving: "#38bdf8", stable: "#fbbf24" };
    const badgeClasses = { decaying: "bad", improving: "good", stable: "warn" };
    const bc = badgeColors[s.decay_signal] || "#64748b";
    const bcls = badgeClasses[s.decay_signal] || "";

    const ltWrColor = s.lifetime_win_rate >= 50 ? "#4ade80" : "#f87171";
    const rcWrColor = s.recent_win_rate >= s.lifetime_win_rate ? "#4ade80" : "#f87171";

    const sparkline = buildMiniSparkline(s.ema_series, 80, 24);
    const weightWarn = s.current_auto_weight < 0.95 ? ' style="color:#fbbf24;font-weight:600;"' : "";

    const btns = [];
    if (s.decay_signal === "decaying" || s.suggested_action === "dampen") {
      btns.push(`<button data-decay-tag="${s.source_tag}" data-decay-action="dampen" style="font-size:0.75em;padding:2px 8px;cursor:pointer;">Dampen</button>`);
    }
    btns.push(`<button data-decay-tag="${s.source_tag}" data-decay-action="restore" style="font-size:0.75em;padding:2px 8px;cursor:pointer;">Restore</button>`);
    btns.push(`<button data-decay-tag="${s.source_tag}" data-decay-action="disable" style="font-size:0.75em;padding:2px 8px;cursor:pointer;color:#f87171;">Disable</button>`);

    return `<div style="border:1px solid #1e293b;border-radius:6px;padding:10px 14px;margin-bottom:8px;">
      <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;">
        <strong>${s.source_tag}</strong>
        <span class="${bcls}" style="font-size:0.75em;font-weight:700;color:${bc};text-transform:uppercase;border:1px solid ${bc};border-radius:3px;padding:1px 6px;">${s.decay_signal}</span>${s.current_auto_weight <= 0.001 ? '<span style="font-size:0.7em;font-weight:700;color:#f87171;background:#450a0a;border:1px solid #f87171;border-radius:3px;padding:1px 6px;margin-left:4px;">AUTO-ZEROED</span>' : ''}
        <span style="margin-left:auto;">${sparkline}</span>
      </div>
      <div style="display:flex;gap:16px;flex-wrap:wrap;margin-top:6px;font-size:0.85em;">
        <span>Lifetime: <span style="color:${ltWrColor};font-weight:600;">${s.lifetime_win_rate.toFixed(1)}%</span> (${s.lifetime_n})</span>
        <span>14d: <span style="color:${rcWrColor};font-weight:600;">${s.recent_win_rate.toFixed(1)}%</span> (${s.recent_n})</span>
        <span>Avg P&L: <span style="${s.recent_avg_pnl_pct >= 0 ? 'color:#4ade80' : 'color:#f87171'}">${s.recent_avg_pnl_pct.toFixed(2)}%</span></span>
        <span${weightWarn}>Weight: ${s.current_auto_weight.toFixed(2)}</span>
      </div>
      <div style="margin-top:6px;display:flex;gap:6px;">${btns.join("")}</div>
    </div>`;
  }).join("");

  listEl.innerHTML = cards;

  // Event delegation for buttons
  listEl.onclick = async (e) => {
    const btn = e.target.closest("[data-decay-tag]");
    if (!btn) return;
    const tag = btn.getAttribute("data-decay-tag");
    const action = btn.getAttribute("data-decay-action");
    if (!tag || !action) return;
    btn.disabled = true;
    btn.textContent = "...";
    try {
      await postJson("/api/source-decay", { source_tag: tag, action: action });
      const fresh = await fetchJsonSafe("/api/source-decay", {});
      renderSourceDecay(fresh || {});
    } catch (err) {
      btn.textContent = "error";
    }
  };
}

function renderXConsensus(data) {
  const signalsEl = document.getElementById("x-consensus-signals");
  const discEl = document.getElementById("x-discovery-candidates");
  const minInput = document.getElementById("x-consensus-min-hits");
  if (!signalsEl || !discEl) return;

  const settings = (data && data.settings) || {};
  if (minInput && settings.x_consensus_min_hits != null) {
    minInput.value = settings.x_consensus_min_hits;
  }

  // Consensus signals table
  const signals = (data && data.consensus_signals) || [];
  if (!signals.length) {
    signalsEl.innerHTML = '<div class="empty">No active consensus signals. Need 3+ handles agreeing on same ticker.</div>';
  } else {
    const grid = "80px 60px 50px 1fr 80px";
    const head = `<div class="row header" style="grid-template-columns:${grid}"><div>Ticker</div><div>Dir</div><div>#</div><div>Sources</div><div>W.Conf</div></div>`;
    const body = signals.slice(0, 30).map((s) => {
      const sources = (() => { try { return JSON.parse(s.sources || "[]").map(escHtml).join(", "); } catch(e) { return escHtml(s.sources || ""); } })();
      const dirColor = s.direction === "long" ? "color:#4ade80" : (s.direction === "short" ? "color:#f87171" : "");
      return `<div class="row" style="grid-template-columns:${grid}"><div style="font-weight:600;">${escHtml(s.ticker)}</div><div style="${dirColor}">${escHtml(s.direction)}</div><div>${s.source_count}</div><div style="font-size:0.8em;opacity:0.7;">${sources}</div><div>${Number(s.weighted_confidence || 0).toFixed(2)}</div></div>`;
    }).join("");
    signalsEl.innerHTML = head + body;
  }

  // Discovery candidates
  const candidates = (data && data.discovery_candidates) || [];
  if (!candidates.length) {
    discEl.innerHTML = '<div class="empty">No discovery candidates. Run discover_x_accounts.py to find new accounts.</div>';
  } else {
    const cards = candidates.slice(0, 50).map((c) => {
      const statusColor = c.status === "new" ? "#fbbf24" : (c.status === "approved" ? "#4ade80" : "#64748b");
      const btns = c.status === "new"
        ? `<button data-disc-handle="${c.handle}" data-disc-action="approve" style="font-size:0.75em;padding:2px 8px;cursor:pointer;color:#4ade80;">Approve</button> <button data-disc-handle="${c.handle}" data-disc-action="reject" style="font-size:0.75em;padding:2px 8px;cursor:pointer;color:#f87171;">Reject</button>`
        : `<span style="font-size:0.75em;color:${statusColor};text-transform:uppercase;">${c.status}</span>`;
      const followers = c.followers ? `${(c.followers / 1000).toFixed(1)}k` : "?";
      const dCat = String(c.kol_category || "stocks");
      const dCatColors = { stocks: "#60a5fa", crypto: "#fbbf24", polymarket: "#a78bfa", mixed: "#94a3b8" };
      const dCatBadge = `<span style="font-size:0.7em;padding:1px 6px;border-radius:4px;background:${dCatColors[dCat] || "#94a3b8"}22;color:${dCatColors[dCat] || "#94a3b8"};font-weight:600;">${dCat}</span>`;
      return `<div style="border:1px solid #1e293b;border-radius:6px;padding:8px 12px;margin-bottom:6px;">
        <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;">
          <strong>@${escHtml(c.handle)}</strong>
          ${dCatBadge}
          <span style="font-size:0.8em;opacity:0.6;">${followers} followers</span>
          <span style="margin-left:auto;">${btns}</span>
        </div>
        ${c.display_name ? `<div style="font-size:0.85em;opacity:0.7;">${escHtml(c.display_name)}</div>` : ""}
        ${c.description ? `<div style="font-size:0.8em;opacity:0.5;margin-top:2px;">${escHtml(c.description.slice(0, 120))}</div>` : ""}
        ${c.sample_call ? `<div style="font-size:0.8em;opacity:0.4;margin-top:2px;font-style:italic;">${escHtml(c.sample_call.slice(0, 140))}</div>` : ""}
      </div>`;
    }).join("");
    discEl.innerHTML = cards;
  }

  // Event delegation for approve/reject
  discEl.onclick = async (e) => {
    const btn = e.target.closest("[data-disc-handle]");
    if (!btn) return;
    const handle = btn.getAttribute("data-disc-handle");
    const action = btn.getAttribute("data-disc-action");
    if (!handle || !action) return;
    btn.disabled = true;
    btn.textContent = "...";
    try {
      await postJson("/api/x-discovery", { handle, action });
      const fresh = await fetchJsonSafe("/api/x-consensus", {});
      renderXConsensus(fresh || {});
    } catch (err) {
      btn.textContent = "error";
    }
  };
}

function bindXConsensus() {
  const btnSave = document.getElementById("btn-x-consensus-save");
  const minInput = document.getElementById("x-consensus-min-hits");
  const statusEl = document.getElementById("x-consensus-status");
  if (!btnSave || !minInput) return;

  btnSave.onclick = async () => {
    const val = parseInt(minInput.value, 10);
    if (isNaN(val) || val < 1 || val > 10) {
      if (statusEl) statusEl.textContent = "Min hits must be 1-10";
      return;
    }
    btnSave.disabled = true;
    btnSave.textContent = "...";
    try {
      await postJson("/api/x-consensus-settings", { x_consensus_min_hits: val });
      if (statusEl) statusEl.textContent = `Saved: min_hits = ${val}`;
      const fresh = await fetchJsonSafe("/api/x-consensus", {});
      renderXConsensus(fresh || {});
    } catch (err) {
      if (statusEl) statusEl.textContent = "Save failed";
    } finally {
      btnSave.disabled = false;
      btnSave.textContent = "Save";
    }
  };
}

boot();
