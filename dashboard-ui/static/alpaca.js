async function fetchJson(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${url} failed: ${res.status}`);
  return res.json();
}

async function fetchJsonSafe(url, fallback) {
  try {
    return await fetchJson(url);
  } catch (_) {
    return fallback;
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

function runUiStep(name, fn) {
  try {
    fn();
  } catch (err) {
    const el = document.getElementById("status-pill");
    if (el) el.textContent = `err: ${name}`;
  }
}

function setStatus(text, cls) {
  const el = document.getElementById("status-pill");
  if (!el) return;
  el.textContent = text;
  el.className = "status" + (cls ? ` ${cls}` : "");
}

function fmtUsd(v) {
  const n = Number(v) || 0;
  return n.toLocaleString("en-US", { style: "currency", currency: "USD" });
}

function fmtPct(v) {
  const n = Number(v) || 0;
  return (n >= 0 ? "+" : "") + (n * 100).toFixed(2) + "%";
}

function pnlClass(v) {
  const n = Number(v) || 0;
  if (n > 0) return "pnl-pos";
  if (n < 0) return "pnl-neg";
  return "";
}

// ── Render helpers ────────────────────────────────────────────────────────

function renderOverview(snapshot) {
  const el = document.getElementById("alpaca-overview");
  if (!el) return;
  const a = snapshot.alpaca || {};
  if (!a.ok) {
    el.innerHTML = `<p class="warn">Alpaca offline: ${a.error || "unknown"}</p>`;
    return;
  }
  el.innerHTML = [
    `<div class="kv"><span>Equity</span><span>${fmtUsd(a.equity)}</span></div>`,
    `<div class="kv"><span>Cash</span><span>${fmtUsd(a.cash)}</span></div>`,
    `<div class="kv"><span>Buying Power</span><span>${fmtUsd(a.buying_power)}</span></div>`,
    `<div class="kv"><span>Open Positions</span><span>${(a.positions || []).length}</span></div>`,
  ].join("");
}

function renderPositions(snapshot) {
  const el = document.getElementById("alpaca-positions");
  if (!el) return;
  const positions = (snapshot.alpaca || {}).positions || [];
  if (!positions.length) {
    el.innerHTML = "<p class='muted'>No open positions</p>";
    return;
  }
  const grid = "80px 60px 60px 100px 100px 80px";
  const head = `<div class="row header" style="grid-template-columns:${grid}">
    <span>Symbol</span><span>Qty</span><span>Side</span><span>Mkt Value</span><span>uPnL</span><span>uPnL%</span>
  </div>`;
  const body = positions
    .map((p) => {
      const cls = pnlClass(p.unrealized_pl);
      return `<div class="row" style="grid-template-columns:${grid}">
        <span>${p.symbol}</span><span>${p.qty}</span><span>${p.side}</span>
        <span>${fmtUsd(p.market_value)}</span>
        <span class="${cls}">${fmtUsd(p.unrealized_pl)}</span>
        <span class="${cls}">${fmtPct(p.unrealized_plpc)}</span>
      </div>`;
    })
    .join("");
  el.innerHTML = head + body;
}

function renderOrders(rows) {
  const el = document.getElementById("alpaca-orders");
  if (!el) return;
  if (!rows.length) {
    el.innerHTML = "<p class='muted'>No execution orders</p>";
    return;
  }
  const grid = "140px 80px 60px 60px 90px 90px 80px";
  const head = `<div class="row header" style="grid-template-columns:${grid}">
    <span>Time</span><span>Ticker</span><span>Dir</span><span>Mode</span><span>Notional</span><span>Fill Price</span><span>Status</span>
  </div>`;
  const body = rows
    .slice(0, 50)
    .map((r) => {
      const ts = (r.created_at || "").replace("T", " ").slice(0, 16);
      const fillPrice = r.filled_price ? fmtUsd(r.filled_price) : "-";
      return `<div class="row" style="grid-template-columns:${grid}">
        <span>${ts}</span><span>${r.ticker}</span><span>${r.direction}</span><span>${r.mode}</span>
        <span>${fmtUsd(r.notional)}</span><span>${fillPrice}</span><span>${r.order_status || "-"}</span>
      </div>`;
    })
    .join("");
  el.innerHTML = head + body;
}

function renderRoutes(routes) {
  const el = document.getElementById("alpaca-routes");
  if (!el) return;
  const filtered = (routes || []).filter(
    (r) => (r.preferred_venue || "").toLowerCase() === "stocks"
  );
  if (!filtered.length) {
    el.innerHTML = "<p class='muted'>No stock-routed signals</p>";
    return;
  }
  const grid = "140px 70px 60px 70px 80px 1fr";
  const head = `<div class="row header" style="grid-template-columns:${grid}">
    <span>Time</span><span>Ticker</span><span>Dir</span><span>Score</span><span>Venue</span><span>Reason</span>
  </div>`;
  const body = filtered
    .slice(0, 40)
    .map((r) => {
      const ts = (r.routed_at || "").replace("T", " ").slice(0, 16);
      return `<div class="row" style="grid-template-columns:${grid}">
        <span>${ts}</span><span>${r.ticker || r.asset || ""}</span><span>${r.direction || ""}</span>
        <span>${Number(r.score || 0).toFixed(1)}</span><span>${r.preferred_venue || ""}</span>
        <span class="muted">${(r.reason || "").slice(0, 60)}</span>
      </div>`;
    })
    .join("");
  el.innerHTML = head + body;
}

function renderClosed(pnlData) {
  const el = document.getElementById("alpaca-closed");
  if (!el) return;
  const trades = (pnlData || {}).closed_trades || [];
  if (!trades.length) {
    el.innerHTML = "<p class='muted'>No closed trades</p>";
    return;
  }
  const grid = "80px 60px 80px 80px 80px 60px";
  const head = `<div class="row header" style="grid-template-columns:${grid}">
    <span>Ticker</span><span>Side</span><span>Entry</span><span>Exit</span><span>PnL</span><span>PnL%</span>
  </div>`;
  const body = trades
    .slice(0, 40)
    .map((t) => {
      const cls = pnlClass(t.pnl_pct || t.pnl_percent);
      return `<div class="row" style="grid-template-columns:${grid}">
        <span>${t.ticker}</span><span>${t.entry_side || ""}</span>
        <span>${fmtUsd(t.entry_price)}</span><span>${fmtUsd(t.exit_price)}</span>
        <span class="${cls}">${fmtUsd(t.pnl || 0)}</span>
        <span class="${cls}">${Number(t.pnl_pct || t.pnl_percent || 0).toFixed(2)}%</span>
      </div>`;
    })
    .join("");
  el.innerHTML = head + body;
}

// ── Controls ──────────────────────────────────────────────────────────────

function wireStocksControls(venueMatrix, riskControls) {
  const stocks = (venueMatrix || []).find(
    (v) => (v.venue || "").toLowerCase() === "stocks"
  );
  if (stocks) {
    const en = document.getElementById("ctl-stocks-enabled");
    if (en) en.checked = Number(stocks.enabled) === 1;
    const mode = document.getElementById("ctl-stocks-mode");
    if (mode) mode.value = stocks.mode || "paper";
    const minScore = document.getElementById("ctl-stocks-min-score");
    if (minScore) minScore.value = stocks.min_score || 0;
    const maxNot = document.getElementById("ctl-stocks-max-notional");
    if (maxNot) maxNot.value = stocks.max_notional || 0;
  }

  const controls = {};
  (riskControls || []).forEach((c) => {
    controls[c.key] = c.value;
  });

  const setCheck = (id, key, def) => {
    const el = document.getElementById(id);
    if (el) el.checked = String(controls[key] ?? def) === "1";
  };
  const setNum = (id, key, def) => {
    const el = document.getElementById(id);
    if (el) el.value = controls[key] ?? def;
  };

  setCheck("ctl-allow-shorts", "allow_equity_shorts", "1");
  setCheck("ctl-high-beta", "high_beta_only", "1");
  setCheck("ctl-consensus-enforce", "consensus_enforce", "1");
  setNum("ctl-alp-min-route", "alpaca_min_route_score", "60");
  setCheck("ctl-pg-kw", "premium_gate_kw_stocks", "0");
  setCheck("ctl-pg-liq", "premium_gate_liq_stocks", "0");
  setCheck("ctl-pg-mom", "premium_gate_mom_stocks", "0");
  setNum("ctl-pg-min", "premium_gate_stocks_min", "0");

  const saveBtn = document.getElementById("btn-stocks-save");
  if (saveBtn && !saveBtn.dataset.wired) {
    saveBtn.dataset.wired = "1";
    saveBtn.addEventListener("click", async () => {
      const status = document.getElementById("stocks-control-status");
      try {
        await postJson("/api/venue-matrix", {
          updates: [
            {
              venue: "stocks",
              enabled: document.getElementById("ctl-stocks-enabled").checked
                ? 1
                : 0,
              mode: document.getElementById("ctl-stocks-mode").value,
              min_score: Number(
                document.getElementById("ctl-stocks-min-score").value
              ),
              max_notional: Number(
                document.getElementById("ctl-stocks-max-notional").value
              ),
            },
          ],
        });
        await postJson("/api/risk-controls", {
          updates: {
            allow_equity_shorts: document.getElementById("ctl-allow-shorts").checked ? "1" : "0",
            high_beta_only: document.getElementById("ctl-high-beta").checked ? "1" : "0",
            consensus_enforce: document.getElementById("ctl-consensus-enforce").checked ? "1" : "0",
            alpaca_min_route_score: document.getElementById("ctl-alp-min-route").value,
            premium_gate_kw_stocks: document.getElementById("ctl-pg-kw").checked ? "1" : "0",
            premium_gate_liq_stocks: document.getElementById("ctl-pg-liq").checked ? "1" : "0",
            premium_gate_mom_stocks: document.getElementById("ctl-pg-mom").checked ? "1" : "0",
            premium_gate_stocks_min: document.getElementById("ctl-pg-min").value,
          },
        });
        if (status) {
          status.textContent = "Saved";
          status.className = "control-warning good";
        }
      } catch (err) {
        if (status) {
          status.textContent = `Error: ${err.message}`;
          status.className = "control-warning bad";
        }
      }
    });
  }
}

function renderMarginInfo(snapshot) {
  const el = document.getElementById("qt-alp-margin");
  if (!el) return;
  const a = snapshot.alpaca || {};
  if (!a.ok || !a.equity) {
    el.textContent = "";
    return;
  }
  const equity = Number(a.equity) || 0;
  const bp = Number(a.buying_power) || 0;
  const margin = equity > 0 ? (bp / equity).toFixed(1) : "?";
  el.textContent = `Account: ${margin}x margin · Buying power: ${fmtUsd(bp)}`;
}

function wireAlpacaQuickTrade() {
  const buyBtn = document.getElementById("btn-alp-buy");
  const shortBtn = document.getElementById("btn-alp-short");
  const closeBtn = document.getElementById("btn-alp-close");
  const status = document.getElementById("qt-alp-status");

  async function submitTrade(side) {
    const symbol = (
      document.getElementById("qt-alp-symbol").value || ""
    ).trim();
    const notional = Number(
      document.getElementById("qt-alp-notional").value || 0
    );
    if (!symbol) {
      if (status) {
        status.textContent = "Enter a symbol";
        status.className = "control-warning bad";
      }
      return;
    }
    if (side !== "close" && notional <= 0) {
      if (status) {
        status.textContent = "Enter a positive notional";
        status.className = "control-warning bad";
      }
      return;
    }
    const label = side === "close" ? "close" : side === "sell" ? "short" : "buy";
    if (status) {
      status.textContent = `Submitting ${label} ${symbol}...`;
      status.className = "control-warning";
    }
    try {
      const body = side === "close"
        ? { symbol, side: "close", notional: 0 }
        : { symbol, side, notional };
      const result = await postJson("/api/alpaca-quick-trade", body);
      if (result.ok) {
        if (status) {
          status.textContent = `Order submitted: ${result.order_id || "ok"}`;
          status.className = "control-warning good";
        }
        setTimeout(() => boot(), 2000);
      } else {
        if (status) {
          status.textContent = `Failed: ${result.error}`;
          status.className = "control-warning bad";
        }
      }
    } catch (err) {
      if (status) {
        status.textContent = `Error: ${err.message}`;
        status.className = "control-warning bad";
      }
    }
  }

  if (buyBtn && !buyBtn.dataset.wired) {
    buyBtn.dataset.wired = "1";
    buyBtn.addEventListener("click", () => submitTrade("buy"));
  }
  if (shortBtn && !shortBtn.dataset.wired) {
    shortBtn.dataset.wired = "1";
    shortBtn.addEventListener("click", () => submitTrade("sell"));
  }
  if (closeBtn && !closeBtn.dataset.wired) {
    closeBtn.dataset.wired = "1";
    closeBtn.addEventListener("click", () => submitTrade("close"));
  }
}

// ── Boot ──────────────────────────────────────────────────────────────────

async function boot() {
  setStatus("loading");
  const [snapshot, orders, routes, pnlData, riskControls, venueMatrix] =
    await Promise.all([
      fetchJsonSafe("/api/portfolio-snapshot", { alpaca: {} }),
      fetchJsonSafe("/api/alpaca-orders?limit=120", []),
      fetchJsonSafe("/api/signal-routes", []),
      fetchJsonSafe("/api/exchange-pnl", {}),
      fetchJsonSafe("/api/risk-controls", []),
      fetchJsonSafe("/api/venue-matrix", []),
    ]);

  runUiStep("overview", () => renderOverview(snapshot));
  runUiStep("positions", () => renderPositions(snapshot));
  runUiStep("marginInfo", () => renderMarginInfo(snapshot));
  runUiStep("orders", () => renderOrders(orders));
  runUiStep("routes", () => renderRoutes(routes));
  runUiStep("closed", () => renderClosed(pnlData));
  runUiStep("wireControls", () =>
    wireStocksControls(venueMatrix, riskControls)
  );
  runUiStep("wireQuickTrade", () => wireAlpacaQuickTrade());

  setStatus("online", "good");
}

boot();
