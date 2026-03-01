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

function fmtCoin(v) {
  const n = Number(v) || 0;
  return n.toFixed(4);
}

// ── Render helpers ────────────────────────────────────────────────────────

function renderOverview(snapshot) {
  const el = document.getElementById("hl-overview");
  if (!el) return;
  const hl = snapshot.hyperliquid || {};
  if (!hl.ok) {
    el.innerHTML = `<p class="warn">Hyperliquid offline: ${hl.error || "unknown"}</p>`;
    return;
  }
  const network = hl.network || "unknown";
  const badge =
    network === "mainnet"
      ? '<span class="badge good">mainnet</span>'
      : '<span class="badge warn">testnet</span>';
  const wallet = (hl.wallet || "").slice(0, 10) + "...";
  const accountValue = Number(hl.perp_account_value || hl.account_value || 0);
  const marginUsed = Number(hl.total_margin_used || 0);
  const available = accountValue - marginUsed;
  const marginRatio = Number(hl.margin_ratio || 0);
  const marginPct = Math.round(marginRatio * 100);
  const positions = hl.positions || [];
  const totalPnl = positions.reduce((s, p) => s + (Number(p.unrealized_pnl) || 0), 0);
  const pnlCls = pnlClass(totalPnl);

  let barColor = "var(--accent)";
  if (marginPct >= 75) barColor = "var(--danger)";
  else if (marginPct >= 50) barColor = "var(--warn)";

  el.innerHTML = `
    <div class="account-header">
      <span>${badge} <span class="mono muted">${wallet}</span></span>
      <span>${positions.length} position${positions.length !== 1 ? "s" : ""}</span>
    </div>
    <div class="account-stats">
      <div class="stat-box">
        <span class="stat-label">Account Value</span>
        <span class="stat-value">${fmtUsd(accountValue)}</span>
      </div>
      <div class="stat-box">
        <span class="stat-label">Margin Used</span>
        <span class="stat-value">${fmtUsd(marginUsed)} <span class="muted">(${marginPct}%)</span></span>
      </div>
      <div class="stat-box">
        <span class="stat-label">Available</span>
        <span class="stat-value">${fmtUsd(available)}</span>
      </div>
      <div class="stat-box">
        <span class="stat-label">Total uPnL</span>
        <span class="stat-value ${pnlCls}">${fmtUsd(totalPnl)}</span>
      </div>
    </div>
    <div class="margin-bar">
      <div class="margin-bar-fill" style="width:${Math.min(marginPct, 100)}%;background:${barColor}"></div>
    </div>
    <div class="margin-bar-label muted">${marginPct}% margin utilization</div>
  `;
}

function renderPerpPositions(snapshot) {
  const el = document.getElementById("hl-perp-positions");
  if (!el) return;
  const positions = (snapshot.hyperliquid || {}).positions || [];
  if (!positions.length) {
    el.innerHTML = "<div class='card span-3'><p class='muted'>No perp positions</p></div>";
    return;
  }
  el.innerHTML = positions
    .map((p) => {
      const pnl = Number(p.unrealized_pnl) || 0;
      const cls = pnlClass(pnl);
      const szi = Number(p.szi) || 0;
      const side = szi >= 0 ? "LONG" : "SHORT";
      const sideBadge = szi >= 0
        ? '<span class="badge good">LONG</span>'
        : '<span class="badge bad-bg">SHORT</span>';
      const pnlPct = Number(p.unrealized_pnl_pct) || 0;
      const lev = Number(p.leverage || 1).toFixed(1);
      const liqPrice = Number(p.liquidation_price) || 0;
      const marginUsed = Number(p.margin_used) || 0;
      const funding = Number(p.cum_funding) || 0;
      const tint = pnl >= 0
        ? "rgba(99, 240, 179, 0.04)"
        : "rgba(255, 123, 123, 0.04)";

      return `<div class="position-card" style="background:linear-gradient(180deg,${tint},#121720 90%)" data-symbol="${p.coin}">
        <div class="position-header">
          <span class="position-coin">${p.coin}</span>
          ${sideBadge}
          <span class="muted">${lev}x</span>
          <span class="muted position-size">${fmtCoin(p.szi)} ${p.coin}</span>
          <span class="muted">Margin ${fmtUsd(marginUsed)}</span>
        </div>
        <div class="position-prices">
          <div class="stat-box">
            <span class="stat-label">Entry</span>
            <span class="stat-value">${fmtUsd(p.entry_price)}</span>
          </div>
          <div class="stat-box">
            <span class="stat-label">Mark</span>
            <span class="stat-value">${fmtUsd(p.mark_price)}</span>
          </div>
          <div class="stat-box">
            <span class="stat-label">Liq Price</span>
            <span class="stat-value ${liqPrice > 0 ? '' : 'muted'}">${liqPrice > 0 ? fmtUsd(liqPrice) : "—"}</span>
          </div>
        </div>
        <div class="position-stats">
          <div class="stat-box">
            <span class="stat-label">Position Value</span>
            <span class="stat-value">${fmtUsd(p.position_value)}</span>
          </div>
          <div class="stat-box">
            <span class="stat-label">uPnL</span>
            <span class="stat-value ${cls}">${fmtUsd(pnl)}</span>
          </div>
          <div class="stat-box">
            <span class="stat-label">ROE%</span>
            <span class="stat-value ${cls}">${pnlPct >= 0 ? "+" : ""}${pnlPct.toFixed(2)}%</span>
          </div>
          <div class="stat-box">
            <span class="stat-label">Funding</span>
            <span class="stat-value ${pnlClass(-funding)}">${fmtUsd(-funding)}</span>
          </div>
        </div>
        <div class="position-actions">
          <button class="btn-close-pos" data-symbol="${p.coin}">Close Position</button>
        </div>
      </div>`;
    })
    .join("");
}

function wireCloseButtons() {
  document.querySelectorAll(".btn-close-pos").forEach((btn) => {
    if (btn.dataset.wired) return;
    btn.dataset.wired = "1";
    btn.addEventListener("click", async (e) => {
      const symbol = e.target.dataset.symbol;
      if (!symbol) return;
      if (!confirm(`Close entire ${symbol} position?`)) return;
      e.target.disabled = true;
      e.target.textContent = "Closing...";
      try {
        const result = await postJson("/api/hyperliquid-close-position", { symbol });
        if (result.ok) {
          e.target.textContent = "Closed";
          setTimeout(() => boot(), 2000);
        } else {
          e.target.textContent = `Failed: ${result.error || "unknown"}`;
          e.target.disabled = false;
        }
      } catch (err) {
        e.target.textContent = "Error";
        e.target.disabled = false;
      }
    });
  });
}

function renderSpotBalances(snapshot) {
  const el = document.getElementById("hl-spot-balances");
  if (!el) return;
  const balances = (snapshot.hyperliquid || {}).spot_balances || [];
  if (!balances.length) {
    const usdc = (snapshot.hyperliquid || {}).spot_total_usdc || 0;
    el.innerHTML = usdc > 0
      ? `<p>USDC: ${fmtUsd(usdc)}</p>`
      : "<p class='muted'>No spot balances</p>";
    return;
  }
  const grid = "80px 100px";
  const head = `<div class="row header" style="grid-template-columns:${grid}">
    <span>Token</span><span>Balance</span>
  </div>`;
  const body = balances
    .map(
      (b) =>
        `<div class="row" style="grid-template-columns:${grid}">
        <span>${b.coin || b.token || "?"}</span><span>${fmtUsd(b.total || b.balance || 0)}</span>
      </div>`
    )
    .join("");
  el.innerHTML = head + body;
}

function formatIntentDetails(raw) {
  if (!raw) return "";
  let obj;
  try {
    obj = typeof raw === "string" ? JSON.parse(raw) : raw;
  } catch (_) {
    const truncated = String(raw).slice(0, 120);
    return `<span title="${String(raw).replace(/"/g, "&quot;")}">${truncated}${raw.length > 120 ? "..." : ""}</span>`;
  }

  const parts = [];
  if (obj.action) parts.push(`<b>${obj.action}</b>`);
  if (obj.reason) parts.push(obj.reason);
  if (obj.pnl_pct != null) {
    const pct = Number(obj.pnl_pct) || 0;
    parts.push(`<span class="${pnlClass(pct)}">PnL: ${pct >= 0 ? "+" : ""}${pct.toFixed(2)}%</span>`);
  }
  if (obj.unrealized_pnl_pct != null) {
    const pct = Number(obj.unrealized_pnl_pct) || 0;
    parts.push(`<span class="${pnlClass(pct)}">uPnL: ${pct >= 0 ? "+" : ""}${pct.toFixed(2)}%</span>`);
  }
  if (obj.error) parts.push(`<span class="badge-error">${obj.error}</span>`);
  if (obj.stop_price) parts.push(`Stop: ${fmtUsd(obj.stop_price)}`);
  if (obj.missing_dependencies) parts.push(`<span class="badge-error">Missing: ${obj.missing_dependencies}</span>`);

  if (parts.length) return parts.join(" &middot; ");

  const fallback = JSON.stringify(obj).slice(0, 120);
  return `<span title="${JSON.stringify(obj).replace(/"/g, "&quot;")}">${fallback}${JSON.stringify(obj).length > 120 ? "..." : ""}</span>`;
}

function renderIntents(rows) {
  const el = document.getElementById("hl-intents");
  if (!el) return;
  if (!rows.length) {
    el.innerHTML = "<p class='muted'>No Hyperliquid trade intents</p>";
    return;
  }
  const grid = "140px 60px 50px 80px 80px 80px 1fr";
  const head = `<div class="row header" style="grid-template-columns:${grid}">
    <span>Time</span><span>Symbol</span><span>Side</span><span>Qty</span><span>Notional</span><span>Status</span><span>Details</span>
  </div>`;
  const body = rows
    .slice(0, 50)
    .map((r) => {
      const ts = (r.created_at || "").replace("T", " ").slice(0, 16);
      const details = formatIntentDetails(r.details);
      return `<div class="row" style="grid-template-columns:${grid}">
        <span>${ts}</span><span>${r.symbol}</span><span>${r.side}</span>
        <span>${r.qty || "-"}</span><span>${fmtUsd(r.notional)}</span>
        <span>${r.status}</span><span>${details}</span>
      </div>`;
    })
    .join("");
  el.innerHTML = head + body;
}

function renderPosMgmt(rows) {
  const el = document.getElementById("hl-pos-mgmt");
  if (!el) return;
  if (!rows.length) {
    el.innerHTML = "<p class='muted'>No position management actions</p>";
    return;
  }
  const grid = "140px 60px 60px 80px 80px 1fr";
  const head = `<div class="row header" style="grid-template-columns:${grid}">
    <span>Time</span><span>Symbol</span><span>Action</span><span>Side</span><span>Status</span><span>Reason</span>
  </div>`;
  const body = rows
    .slice(0, 40)
    .map((r) => {
      const ts = (r.created_at || "").replace("T", " ").slice(0, 16);
      return `<div class="row" style="grid-template-columns:${grid}">
        <span>${ts}</span><span>${r.symbol}</span><span>${r.action || ""}</span>
        <span>${r.side}</span><span>${r.status}</span>
        <span class="muted">${(r.reason || "").slice(0, 60)}</span>
      </div>`;
    })
    .join("");
  el.innerHTML = head + body;
}

function renderRoutes(routes) {
  const el = document.getElementById("hl-routes");
  if (!el) return;
  const filtered = (routes || []).filter(
    (r) => (r.preferred_venue || "").toLowerCase() === "crypto"
  );
  if (!filtered.length) {
    el.innerHTML = "<p class='muted'>No crypto-routed signals</p>";
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

// ── Controls ──────────────────────────────────────────────────────────────

function wireCryptoControls(venueMatrix) {
  const crypto = (venueMatrix || []).find(
    (v) => (v.venue || "").toLowerCase() === "crypto"
  );
  if (crypto) {
    const en = document.getElementById("ctl-crypto-enabled");
    if (en) en.checked = Number(crypto.enabled) === 1;
    const mode = document.getElementById("ctl-crypto-mode");
    if (mode) mode.value = crypto.mode || "paper";
    const minScore = document.getElementById("ctl-crypto-min-score");
    if (minScore) minScore.value = crypto.min_score || 0;
    const maxNot = document.getElementById("ctl-crypto-max-notional");
    if (maxNot) maxNot.value = crypto.max_notional || 0;
  }

  const saveBtn = document.getElementById("btn-crypto-save");
  if (saveBtn && !saveBtn.dataset.wired) {
    saveBtn.dataset.wired = "1";
    saveBtn.addEventListener("click", async () => {
      const status = document.getElementById("crypto-control-status");
      try {
        await postJson("/api/venue-matrix", {
          updates: [
            {
              venue: "crypto",
              enabled: document.getElementById("ctl-crypto-enabled").checked
                ? 1
                : 0,
              mode: document.getElementById("ctl-crypto-mode").value,
              min_score: Number(
                document.getElementById("ctl-crypto-min-score").value
              ),
              max_notional: Number(
                document.getElementById("ctl-crypto-max-notional").value
              ),
            },
          ],
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

function wireHlQuickTrade() {
  const buyBtn = document.getElementById("btn-hl-buy");
  const sellBtn = document.getElementById("btn-hl-sell");
  const status = document.getElementById("qt-hl-status");

  async function submitTrade(side) {
    const symbol = document.getElementById("qt-hl-symbol").value || "";
    const notional = Number(
      document.getElementById("qt-hl-notional").value || 0
    );
    if (!symbol) {
      if (status) {
        status.textContent = "Select a symbol";
        status.className = "control-warning bad";
      }
      return;
    }
    if (notional <= 0) {
      if (status) {
        status.textContent = "Enter a positive notional";
        status.className = "control-warning bad";
      }
      return;
    }
    if (status) {
      status.textContent = `Submitting ${side} ${symbol}...`;
      status.className = "control-warning";
    }
    try {
      const result = await postJson("/api/hyperliquid-quick-trade", {
        symbol,
        side,
        notional,
      });
      if (result.ok) {
        if (status) {
          status.textContent = `Intent recorded: ${result.intent_id || "ok"}`;
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
  if (sellBtn && !sellBtn.dataset.wired) {
    sellBtn.dataset.wired = "1";
    sellBtn.addEventListener("click", () => submitTrade("sell"));
  }
}

// ── Boot ──────────────────────────────────────────────────────────────────

async function boot() {
  setStatus("loading");
  const [snapshot, intents, posMgmt, routes, riskControls, venueMatrix] =
    await Promise.all([
      fetchJsonSafe("/api/portfolio-snapshot", { hyperliquid: {} }),
      fetchJsonSafe("/api/hyperliquid-intents?limit=120", []),
      fetchJsonSafe("/api/position-management-intents?limit=120", []),
      fetchJsonSafe("/api/signal-routes", []),
      fetchJsonSafe("/api/risk-controls", []),
      fetchJsonSafe("/api/venue-matrix", []),
    ]);

  runUiStep("overview", () => renderOverview(snapshot));
  runUiStep("perpPositions", () => renderPerpPositions(snapshot));
  runUiStep("wireClose", () => wireCloseButtons());
  runUiStep("spotBalances", () => renderSpotBalances(snapshot));
  runUiStep("intents", () => renderIntents(intents));
  runUiStep("posMgmt", () => renderPosMgmt(posMgmt));
  runUiStep("routes", () => renderRoutes(routes));
  runUiStep("wireControls", () => wireCryptoControls(venueMatrix));
  runUiStep("wireQuickTrade", () => wireHlQuickTrade());

  setStatus("online", "good");
}

boot();
