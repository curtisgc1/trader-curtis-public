async function fetchJson(url) {
  const res = await fetch(url);
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

function renderPolymarketCandidates(rows) {
  const el = document.getElementById("polymarket-candidates");
  if (!el) return;
  if (!rows || rows.length === 0) {
    el.innerHTML = `<div class="empty">No data</div>`;
    return;
  }
  const head = `<div class="row header"><div>Strategy</div><div>Edge %</div><div>Outcome</div><div>Market</div></div>`;
  const body = rows.slice(0, 40).map((r) => {
    const link = r.market_url ? `<a href="${r.market_url}" target="_blank" rel="noreferrer">open</a>` : "";
    return `<div class="row"><div>${r.strategy_id || ""}</div><div>${r.edge || ""}</div><div>${r.outcome || ""}</div><div>${link}</div></div>`;
  }).join("");
  el.innerHTML = head + body;
}

function renderPolymarketMarkets(rows) {
  const el = document.getElementById("polymarket-markets");
  if (!el) return;
  if (!rows || rows.length === 0) {
    el.innerHTML = `<div class="empty">No data</div>`;
    return;
  }
  const head = `<div class="row header"><div>Slug</div><div>Liq</div><div>Vol 24h</div><div>URL</div></div>`;
  const body = rows.slice(0, 30).map((r) => {
    const link = r.market_url ? `<a href="${r.market_url}" target="_blank" rel="noreferrer">open</a>` : "";
    return `<div class="row"><div>${r.slug || ""}</div><div>${r.liquidity || ""}</div><div>${r.volume_24h || ""}</div><div>${link}</div></div>`;
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
  const head = `<div class="row header"><div>Source</div><div>Strategy</div><div>Thesis</div><div>URL</div></div>`;
  const body = rows.slice(0, 30).map((r) => {
    const link = r.source_url ? `<a href="${r.source_url}" target="_blank" rel="noreferrer">open</a>` : "";
    return `<div class="row"><div>${r.source_handle || ""}</div><div>${r.strategy_tag || ""}</div><div>${r.thesis_type || ""}</div><div>${link}</div></div>`;
  }).join("");
  el.innerHTML = head + body;
}

async function boot() {
  try {
    setStatus("loading");
    const [systemHealth, polymarketCandidates, polymarketMarkets, bookmarkAlphaIdeas, externalSignals] = await Promise.all([
      fetchJson("/api/system-health"),
      fetchJson("/api/polymarket-candidates"),
      fetchJson("/api/polymarket-markets"),
      fetchJson("/api/bookmark-alpha-ideas"),
      fetchJson("/api/external-signals"),
    ]);

    renderPolymarketCandidates(polymarketCandidates || []);
    renderPolymarketMarkets(polymarketMarkets || []);
    renderBookmarkAlphaIdeas(bookmarkAlphaIdeas || []);
    renderTable("external-signals", (externalSignals || []).slice(0, 20), ["Source", "Ticker", "Dir", "Conf"], ["source", "ticker", "direction", "confidence"]);

    const topState = (systemHealth && systemHealth.overall) || "good";
    setStatus("online", topState === "good" ? "good" : (topState === "warn" ? "warn" : "bad"));
  } catch (err) {
    console.error(err);
    setStatus("offline", "bad");
  }
}

boot();
