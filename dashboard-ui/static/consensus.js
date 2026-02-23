async function fetchJson(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${url} failed ${r.status}`);
  return r.json();
}

async function postJson(url, body) {
  const r = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
  });
  if (!r.ok) throw new Error(`${url} failed ${r.status}`);
  return r.json();
}

function setStatus(text, cls = "") {
  const el = document.getElementById("status-pill");
  if (!el) return;
  el.textContent = text;
  el.className = `status ${cls}`;
}

function setControlStatus(text, cls = "warn") {
  const el = document.getElementById("control-status");
  if (!el) return;
  el.textContent = text || "";
  el.className = `control-warning ${cls}`;
}

function renderTable(elId, rows, headers, fields) {
  const el = document.getElementById(elId);
  if (!el) return;
  if (!rows || rows.length === 0) {
    el.innerHTML = `<div class="empty">No data</div>`;
    return;
  }
  const cols = Math.max(1, headers.length);
  const grid = `style="grid-template-columns: repeat(${cols}, minmax(150px, 1fr));"`;
  const head = `<div class="row header" ${grid}>${headers.map((h) => `<div>${h}</div>`).join("")}</div>`;
  const body = rows.map((r) => `<div class="row" ${grid}>${fields.map((f) => `<div>${r[f] ?? ""}</div>`).join("")}</div>`).join("");
  el.innerHTML = head + body;
}

function formatEvidence(r) {
  const list = Array.isArray(r.evidence_ratings) ? r.evidence_ratings : [];
  if (list.length === 0) return "";
  return list.slice(0, 6).map((x) => {
    const src = x.source || "";
    const wr = Number(x.win_rate || 0).toFixed(1);
    const n = Number(x.sample_size || 0);
    return `${src} (${wr}% / n=${n})`;
  }).join("<br/>");
}

function formatPolymarket(r) {
  const list = Array.isArray(r.polymarket_matches) ? r.polymarket_matches : [];
  if (list.length === 0) return "No direct market match";
  return list.slice(0, 3).map((m) => {
    const q = m.question || "market";
    const liq = Number(m.liquidity || 0).toFixed(0);
    const s = Number(m.match_score || 0).toFixed(0);
    const url = m.market_url || "";
    if (url) return `<a href="${url}" target="_blank" rel="noopener">${q}</a> (score ${s}, liq $${liq})`;
    return `${q} (score ${s}, liq $${liq})`;
  }).join("<br/>");
}

function renderTrust(panel) {
  const el = document.getElementById("trust-state");
  if (!el) return;
  const th = panel.consensus_thresholds || {};
  const stateCls = panel.state === "good" ? "good" : (panel.state === "warn" ? "warn" : "bad");
  el.innerHTML = [
    `<div class="item"><span class="label">State</span><span class="${stateCls}">${String(panel.state || "unknown").toUpperCase()}</span></div>`,
    `<div class="item"><span class="label">Master</span><span>${panel.master_enabled ? "ON" : "OFF"}</span></div>`,
    `<div class="item"><span class="label">Consensus</span><span>${panel.consensus_enforce ? "ON" : "OFF"}</span></div>`,
    `<div class="item"><span class="label">Thresholds</span><span>${th.min_confirmations || 0} / ${th.min_ratio || 0} / ${th.min_score || 0}</span></div>`,
    `<div class="item"><span class="label">Flagged</span><span>${panel.candidates_flagged || 0} / ${panel.candidates_total || 0}</span></div>`,
  ].join("");

  const controls = window._controls || {};
  document.getElementById("ctl-master").checked = (controls.agent_master_enabled || "0") === "1";
  document.getElementById("ctl-consensus").checked = (controls.consensus_enforce || "1") === "1";
  document.getElementById("ctl-c-min").value = controls.consensus_min_confirmations || "3";
  document.getElementById("ctl-c-ratio").value = controls.consensus_min_ratio || "0.6";
  document.getElementById("ctl-c-score").value = controls.consensus_min_score || "60";
}

function wireControls() {
  const save = document.getElementById("btn-save");
  const scan = document.getElementById("btn-scan");
  const align = document.getElementById("btn-poly-align");

  if (save && !save.dataset.wired) {
    save.dataset.wired = "1";
    save.addEventListener("click", async () => {
      try {
        const updates = {
          agent_master_enabled: document.getElementById("ctl-master").checked ? "1" : "0",
          consensus_enforce: document.getElementById("ctl-consensus").checked ? "1" : "0",
          consensus_min_confirmations: String(document.getElementById("ctl-c-min").value || "3"),
          consensus_min_ratio: String(document.getElementById("ctl-c-ratio").value || "0.6"),
          consensus_min_score: String(document.getElementById("ctl-c-score").value || "60"),
        };
        await postJson("/api/risk-controls", { updates });
        setControlStatus("Controls saved", "good");
        await boot();
      } catch (e) {
        console.error(e);
        setControlStatus("Save failed", "bad");
      }
    });
  }

  if (scan && !scan.dataset.wired) {
    scan.dataset.wired = "1";
    scan.addEventListener("click", async () => {
      try {
        await postJson("/api/actions", { action: "run_scan" });
        setControlStatus("Scan triggered", "good");
        setTimeout(() => boot(), 1500);
      } catch (e) {
        console.error(e);
        setControlStatus("Scan trigger failed", "bad");
      }
    });
  }

  if (align && !align.dataset.wired) {
    align.dataset.wired = "1";
    align.addEventListener("click", async () => {
      try {
        await postJson("/api/actions", { action: "run_poly_align" });
        setControlStatus("Polymarket alignment triggered", "good");
        setTimeout(() => boot(), 1200);
      } catch (e) {
        console.error(e);
        setControlStatus("Polymarket alignment failed", "bad");
      }
    });
  }
}

async function boot() {
  try {
    setStatus("loading");
    const mode = document.getElementById("aligned-mode")?.value || "all";
    const [trust, controls, candidates, sources, aligned] = await Promise.all([
      fetchJson("/api/trust-panel"),
      fetchJson("/api/risk-controls"),
      fetchJson("/api/consensus-candidates?flagged_only=1"),
      fetchJson("/api/source-ratings"),
      fetchJson(`/api/polymarket-aligned-setups?mode=${encodeURIComponent(mode)}`),
    ]);

    window._controls = {};
    (controls || []).forEach((r) => { window._controls[r.key] = String(r.value || ""); });

    renderTrust(trust || {});
    wireControls();

    renderTable(
      "consensus-candidates",
      (candidates || []).slice(0, 40).map((r) => ({
        ticker: r.ticker,
        dir: r.direction,
        score: r.score,
        conf: `${r.confirmations}/${r.sources_total}`,
        ratio: r.consensus_ratio,
        source: r.source_tag || "",
        evidence: formatEvidence(r),
        poly: formatPolymarket(r),
      })),
      ["Ticker", "Dir", "Score", "N/M", "Ratio", "Primary", "Why Flagged (with source rating)", "Polymarket Match"],
      ["ticker", "dir", "score", "conf", "ratio", "source", "evidence", "poly"],
    );

    renderTable(
      "source-ratings",
      (sources || []).slice(0, 25),
      ["Source", "Samples", "Win%", "Avg PnL%"],
      ["source", "sample_size", "win_rate", "avg_pnl_pct"],
    );

    renderTable(
      "aligned-poly-setups",
      (aligned || []).slice(0, 35).map((r) => ({
        play: `${r.ticker || ""} ${String(r.direction || "").toUpperCase()}`.trim(),
        score: Number(r.candidate_score || 0).toFixed(2),
        alpha: Number(r.alpha_score || 0).toFixed(3),
        consensus: `${r.confirmations || 0}/${r.sources_total || 0} (${Number(r.consensus_ratio || 0).toFixed(2)})`,
        classTag: r.class_tag || "",
        market: r.market_url ? `<a href="${r.market_url}" target="_blank" rel="noopener">${r.question || r.market_slug || "open market"}</a>` : (r.question || r.market_slug || ""),
        confidence: Number(r.alignment_confidence || 0).toFixed(3),
        crowding: Number(r.crowding_penalty || 0).toFixed(3),
        liq: `$${Number(r.liquidity || 0).toFixed(0)}`,
        mscore: Number(r.match_score || 0).toFixed(1),
      })),
      ["Play", "Signal", "Alpha", "Consensus", "Class", "Polymarket Market", "Align Conf", "Crowding", "Liquidity", "Match"],
      ["play", "score", "alpha", "consensus", "classTag", "market", "confidence", "crowding", "liq", "mscore"],
    );

    setStatus("online", (trust?.state === "good") ? "good" : ((trust?.state === "warn") ? "warn" : "bad"));
  } catch (e) {
    console.error(e);
    setStatus("offline", "bad");
  }
}

boot();

const modeSel = document.getElementById("aligned-mode");
if (modeSel && !modeSel.dataset.wired) {
  modeSel.dataset.wired = "1";
  modeSel.addEventListener("change", () => boot());
}
