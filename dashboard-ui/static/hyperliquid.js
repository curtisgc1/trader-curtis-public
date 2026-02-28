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
  el.innerHTML = [
    `<div class="kv"><span>Network</span><span>${badge}</span></div>`,
    `<div class="kv"><span>Wallet</span><span class="mono">${(hl.wallet || "").slice(0, 10)}...</span></div>`,
    `<div class="kv"><span>Perp Account Value</span><span>${fmtUsd(hl.perp_account_value || hl.account_value)}</span></div>`,
    `<div class="kv"><span>Withdrawable</span><span>${fmtUsd(hl.perp_withdrawable || hl.withdrawable)}</span></div>`,
    `<div class="kv"><span>Spot USDC</span><span>${fmtUsd(hl.spot_total_usdc)}</span></div>`,
    `<div class="kv"><span>Perp Positions</span><span>${(hl.positions || []).length}</span></div>`,
  ].join("");
}

function renderPerpPositions(snapshot) {
  const el = document.getElementById("hl-perp-positions");
  if (!el) return;
  const positions = (snapshot.hyperliquid || {}).positions || [];
  if (!positions.length) {
    el.innerHTML = "<p class='muted'>No perp positions</p>";
    return;
  }
  const grid = "60px 70px 50px 90px 90px 90px";
  const head = `<div class="row header" style="grid-template-columns:${grid}">
    <span>Coin</span><span>Size</span><span>Lev</span><span>Entry</span><span>Mark</span><span>uPnL</span>
  </div>`;
  const body = positions
    .map((p) => {
      const cls = pnlClass(p.unrealized_pnl_usd);
      return `<div class="row" style="grid-template-columns:${grid}">
        <span>${p.coin}</span><span>${fmtCoin(p.szi)}</span><span>${Number(p.leverage || 1).toFixed(1)}x</span>
        <span>${fmtUsd(p.entry_price)}</span><span>${fmtUsd(p.mark_price)}</span>
        <span class="${cls}">${fmtUsd(p.unrealized_pnl_usd)}</span>
      </div>`;
    })
    .join("");
  el.innerHTML = head + body;
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
      let details = r.details || "";
      if (details.length > 80) details = details.slice(0, 80) + "...";
      return `<div class="row" style="grid-template-columns:${grid}">
        <span>${ts}</span><span>${r.symbol}</span><span>${r.side}</span>
        <span>${r.qty || "-"}</span><span>${fmtUsd(r.notional)}</span>
        <span>${r.status}</span><span class="muted">${details}</span>
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
  runUiStep("spotBalances", () => renderSpotBalances(snapshot));
  runUiStep("intents", () => renderIntents(intents));
  runUiStep("posMgmt", () => renderPosMgmt(posMgmt));
  runUiStep("routes", () => renderRoutes(routes));
  runUiStep("wireControls", () => wireCryptoControls(venueMatrix));
  runUiStep("wireQuickTrade", () => wireHlQuickTrade());

  setStatus("online", "good");
}

boot();
