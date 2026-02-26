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
    body: JSON.stringify(body),
  });
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
  const body = rows
    .map((r) => `<div class="row">${fields.map((f) => `<div>${r[f] ?? ""}</div>`).join("")}</div>`)
    .join("");
  el.innerHTML = head + body;
}

function friendlyInputName(key) {
  const k = String(key || "").trim().toLowerCase();
  if (k === "family:liquidity") return "Liquidity";
  if (k === "family:pipeline") return "Strategy engine";
  if (k === "family:pattern") return "Pattern quality";
  if (k === "family:social") return "Social sentiment";
  if (k === "family:external") return "External signals";
  if (k === "family:copy") return "Copy signals";
  if (k.startsWith("kelly:")) return k.replace(/^kelly:/, "").replace(":", " ").toUpperCase();
  if (k.startsWith("strategy:")) return "Strategy x signal";
  if (k.startsWith("source:")) return "Source feed";
  if (k.startsWith("pipeline:")) return "Pipeline lane";
  if (k.startsWith("x:")) return `X handle @${k.replace(/^x:/, "")}`;
  return String(key || "").replace(/_/g, " ");
}

function inputHelpText(key) {
  const k = String(key || "").trim().toLowerCase();
  if (k === "family:liquidity") return "Entry timing and stop/target structure quality.";
  if (k === "family:pipeline") return "Main strategy score that gates route decisions.";
  if (k === "family:pattern") return "Pattern reliability (breakout, reversal, fakeout quality).";
  if (k === "family:social") return "Social sentiment pressure from social feeds.";
  if (k === "family:external") return "External news/event signal influence.";
  if (k === "family:copy") return "Copy-trade style influence from tracked call sources.";
  if (k.startsWith("strategy:")) return "Per-strategy override that adjusts the family signal mix.";
  if (k.startsWith("source:")) return "Per-source override for one feed/source tag.";
  if (k.startsWith("pipeline:")) return "Per-pipeline override (not a separate base signal).";
  if (k.startsWith("x:")) return "One tracked X handle contribution.";
  return "This input contributes to overall signal scoring.";
}

function fmtTs(iso) {
  const s = String(iso || "").trim();
  if (!s) return "-";
  const d = new Date(s);
  if (Number.isNaN(d.getTime())) return s;
  return d.toLocaleString();
}

function yn(v) {
  return Number(v || 0) === 1 ? "yes" : "no";
}

function escapeHtml(s) {
  return String(s || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll("\"", "&quot;")
    .replaceAll("'", "&#39;");
}

async function saveCoreSubInput(rowEl) {
  const statusEl = document.getElementById("core-controls-status");
  const sourceKey = String(rowEl?.dataset?.sourceKey || "").trim();
  const sourceLabel = String(rowEl?.dataset?.sourceLabel || "").trim();
  const sourceClass = String(rowEl?.dataset?.sourceClass || "").trim();
  const notes = String(rowEl?.dataset?.notes || "").trim();
  if (!sourceKey) return;
  const enabledEl = rowEl.querySelector("input[data-field='enabled']");
  const manualEl = rowEl.querySelector("input[data-field='manual_weight']");
  const autoEl = rowEl.querySelector("input[data-field='auto_weight']");
  const payload = {
    source_key: sourceKey,
    source_label: sourceLabel,
    source_class: sourceClass,
    enabled: !!enabledEl?.checked,
    manual_weight: Number(manualEl?.value || 1),
    auto_weight: Number(autoEl?.value || 1),
    notes,
  };
  if (statusEl) statusEl.textContent = `Saving ${sourceKey}...`;
  try {
    const out = await postJson("/api/input-sources", payload);
    if (!out || !out.ok) {
      if (statusEl) statusEl.textContent = `Save failed: ${(out && out.error) || "unknown"}`;
      return;
    }
    if (statusEl) statusEl.textContent = `Saved ${sourceKey}`;
    await refreshCorePanel();
  } catch (err) {
    if (statusEl) statusEl.textContent = `Save failed: ${err.message}`;
  }
}

function bindCoreSignalEditors() {
  document.querySelectorAll(".core-sub-save").forEach((btn) => {
    if (btn.dataset.wired === "1") return;
    btn.dataset.wired = "1";
    btn.addEventListener("click", async () => {
      const row = btn.closest(".sub-input-row");
      if (!row) return;
      await saveCoreSubInput(row);
    });
  });

  // Family-level weight save buttons
  document.querySelectorAll(".family-save-btn").forEach((btn) => {
    if (btn.dataset.wired === "1") return;
    btn.dataset.wired = "1";
    btn.addEventListener("click", async () => {
      const strip = btn.closest(".family-weight-strip");
      if (!strip) return;
      const familyKey = strip.dataset.familyKey;
      const familyLabel = strip.dataset.familyLabel || familyKey;
      const enabledEl = strip.querySelector(".family-enabled");
      const manualEl = strip.querySelector(".family-manual-weight");
      const statusEl = strip.querySelector(".family-save-status");
      if (!familyKey || !manualEl) return;
      const enabled = enabledEl ? enabledEl.checked : true;
      const manualWeight = parseFloat(manualEl.value) || 1.0;
      btn.disabled = true;
      if (statusEl) statusEl.textContent = "saving…";
      try {
        const res = await postJson("/api/input-sources", {
          source_key: familyKey,
          source_label: familyLabel,
          source_class: "family",
          enabled: enabled,
          manual_weight: manualWeight,
          auto_weight: 1.0,
          notes: "",
        });
        if (statusEl) statusEl.textContent = res.ok ? "saved ✓" : `error: ${res.error || "unknown"}`;
        setTimeout(() => { if (statusEl) statusEl.textContent = ""; }, 3000);
        // Refresh core signals to reflect new weight
        await refreshCorePanel();
      } catch (err) {
        if (statusEl) statusEl.textContent = `failed: ${err.message}`;
      } finally {
        btn.disabled = false;
      }
    });
  });
}

function renderCoreSignals(core) {
  const summaryEl = document.getElementById("core-signals-summary");
  const wrapEl = document.getElementById("core-signals-list");
  if (!summaryEl || !wrapEl) return;

  const signals = Array.isArray(core?.signals) ? core.signals : [];
  const enabled = signals.filter((x) => Number(x.enabled || 0) === 1).length;
  const total = signals.length;
  const totalHits = signals.reduce((s, x) => s + Number(x.recent_hits || 0), 0);
  const lookback = Number(core?.lookback_hours || 72);

  summaryEl.innerHTML = [
    ["Signals enabled", `${enabled}/${total || 0}`],
    ["Recent signal hits", `${totalHits} in last ${lookback}h`],
    ["As of", fmtTs(core?.as_of_utc)],
  ]
    .map(([k, v]) => `<div class="item"><span class="label">${k}</span><span>${v}</span></div>`)
    .join("");

  if (!signals.length) {
    wrapEl.innerHTML = `<div class="empty">No core signal data</div>`;
    return;
  }

  const items = signals.map((r, idx) => {
    const subInputs = Array.isArray(r.sub_inputs) ? r.sub_inputs : [];
    const summary = `
      <div class="signal-item-summary">
        <div class="name">${escapeHtml(r.label || r.key)}</div>
        <div>${yn(r.enabled)}</div>
        <div>${Number(r.effective_weight || 1).toFixed(2)} eff</div>
        <div>${Number(r.recent_hits || 0)} hits</div>
        <div class="muted">${escapeHtml(r.description || "")}</div>
      </div>
    `;
    const helpNote = (r.key === "social" && subInputs.length <= 1)
      ? `<div class="sub" style="margin-top:6px;">Only one social input key is currently configured. We can split it into platform-level controls next.</div>`
      : "";
    const isKelly = (r.key === "kelly");
    const header = isKelly
      ? `<div class="sub-input-row header"><div>Candidate</div><div>Pass</div><div>Full K%</div><div>b (payout)</div><div>¼ Kelly%</div><div>Samples</div><div>EV%</div><div>Win%</div><div></div></div>`
      : `<div class="sub-input-row header"><div>Input</div><div>On</div><div>Manual</div><div>Auto</div><div>Eff</div><div>Hits</div><div>Score</div><div>Win%</div><div>Save</div></div>`;
    const rows = subInputs.map((s) => {
      const label = escapeHtml(s.source_label || friendlyInputName(s.source_key));
      const key = escapeHtml(s.source_key || "");
      const perfScore = Number(s.score_pct || 0).toFixed(1);
      const win = Number(s.win_rate || 0).toFixed(1);
      if (isKelly) {
        const kf = Number(s.manual_weight || 0);
        const b = Number(s.auto_weight || 0);
        const fk = Number(s.effective_weight || 0);
        const ev = Number(s.score_pct || 0);
        const kColor = kf > 0 ? "#4ade80" : "#f87171";
        const evColor = ev > 0 ? "#4ade80" : "#f87171";
        const bColor = b >= 2 ? "#4ade80" : b >= 1 ? "#facc15" : "#f87171";
        return `
          <div class="sub-input-row" title="${escapeHtml(s.notes || "")}">
            <div><div>${label}</div></div>
            <div>${Number(s.enabled || 0) === 1 ? `<span style="color:#4ade80;">✓</span>` : `<span style="color:#f87171;">✗</span>`}</div>
            <div style="color:${kColor};font-weight:bold;">${(kf * 100).toFixed(1)}%</div>
            <div style="color:${bColor};font-weight:bold;">${b.toFixed(2)}×</div>
            <div style="color:${kColor};">${(fk * 100).toFixed(2)}%</div>
            <div style="opacity:0.6;">${Number(s.recent_hits || 0)}</div>
            <div style="color:${evColor};">${ev > 0 ? "+" : ""}${ev.toFixed(2)}%</div>
            <div>${win}%</div>
            <div></div>
          </div>
        `;
      }
      return `
        <div class="sub-input-row" data-source-key="${key}" data-source-label="${escapeHtml(s.source_label || "")}" data-source-class="${escapeHtml(s.source_class || "")}" data-notes="${escapeHtml(s.notes || "")}">
          <div><div>${label}</div><div class="sub-key">${key}</div></div>
          <div><input type="checkbox" data-field="enabled" ${Number(s.enabled || 0) === 1 ? "checked" : ""} /></div>
          <div><input type="number" data-field="manual_weight" min="0" max="5" step="0.05" value="${Number(s.manual_weight || 1).toFixed(2)}" /></div>
          <div><input type="number" data-field="auto_weight" min="0.1" max="5" step="0.05" value="${Number(s.auto_weight || 1).toFixed(2)}" /></div>
          <div>${Number(s.effective_weight || 1).toFixed(2)}</div>
          <div>${Number(s.recent_hits || 0)}</div>
          <div>${perfScore}</div>
          <div>${win}</div>
          <div><button class="core-sub-save">Save</button></div>
        </div>
      `;
    }).join("");
    const noRows = !subInputs.length ? `<div class="empty" style="margin-top:6px;">No sub-input controls mapped yet for this signal.</div>` : "";

    // Family-level weight edit strip (shown for all signals that have a family key)
    const familyKey = escapeHtml(r.family_source_key || "");
    const familyStrip = familyKey ? `
      <div class="family-weight-strip" data-family-key="${familyKey}" data-family-label="${escapeHtml(r.label || r.key)}" style="display:flex;align-items:center;gap:10px;padding:8px 0;border-bottom:1px solid #1e293b;margin-bottom:8px;">
        <span style="font-size:0.82em;opacity:0.7;min-width:80px;">Family weight</span>
        <label style="font-size:0.8em;display:flex;align-items:center;gap:4px;">
          <input type="checkbox" class="family-enabled" ${Number(r.enabled || 0) === 1 ? "checked" : ""} title="Enable/disable this signal family" />
          <span>enabled</span>
        </label>
        <label style="font-size:0.8em;display:flex;align-items:center;gap:4px;">
          <span>manual</span>
          <input type="number" class="family-manual-weight" min="0" max="5" step="0.05" value="${Number(r.manual_weight || 1).toFixed(2)}" style="width:60px;" title="Manual weight multiplier for this signal family" />
        </label>
        <span style="font-size:0.78em;opacity:0.5;">auto: ${Number(r.auto_weight || 1).toFixed(2)} · eff: ${Number(r.effective_weight || 1).toFixed(2)}</span>
        <button class="family-save-btn" style="font-size:0.78em;padding:2px 10px;">Save</button>
        <span class="family-save-status" style="font-size:0.75em;opacity:0.6;"></span>
      </div>
    ` : "";

    return `
      <details class="signal-item" ${idx < 2 ? "open" : ""}>
        <summary>${summary}</summary>
        <div class="signal-item-body">
          ${helpNote}
          ${familyStrip}
          <div class="sub">Sub-inputs: ${Number(r.sub_inputs_enabled || 0)} enabled / ${Number(r.sub_inputs_total || 0)} total. Last seen: ${escapeHtml(fmtTs(r.last_seen_utc))}</div>
          <div class="sub-input-grid">${header}${rows || ""}</div>
          ${noRows}
        </div>
      </details>
    `;
  });
  wrapEl.innerHTML = `<div class="signal-accordion">${items.join("")}</div>`;
  bindCoreSignalEditors();
}

async function refreshCorePanel() {
  const core = await fetchJsonSafe("/api/core-signals", { signals: [], x_sources: [], lookback_hours: 72 });
  renderCoreSignals(core || {});
  return core || {};
}

let tradeReviewExplain = null;

function populateTradeReviewInputChoices(explain, allInputSources, xSources) {
  const select = document.getElementById("trade-review-input-key-select");
  if (!select) return;
  const fromExplain = (explain?.candidate?.input_breakdown || [])
    .map((x) => String(x.key || "").trim())
    .filter((x) => !!x);
  const fromAll = (allInputSources || [])
    .map((r) => String(r.source_key || "").trim())
    .filter((k) => k.startsWith("family:") || k.startsWith("strategy:") || k.startsWith("source:") || k.startsWith("pipeline:") || k.startsWith("x:"));
  const fromX = (xSources || []).map((x) => `x:${String(x.handle || "").toLowerCase()}`);
  const merged = Array.from(new Set([...fromExplain, ...fromAll, ...fromX])).sort((a, b) => a.localeCompare(b));
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
  ]
    .map(([k, v]) => `<div class="item"><span class="label">${k}</span><span>${v}</span></div>`)
    .join("");

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

function bindTradeReplayFeedback(allInputSources, coreSignals) {
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
      populateTradeReviewInputChoices(tradeReviewExplain, allInputSources || [], coreSignals?.x_sources || []);
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
      try {
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
        const applied = Number(out.applied?.updated || 0);
        status.textContent = out.apply_now
          ? `Saved feedback. Updated ${applied} input weight(s).`
          : "Saved feedback for weekly batch.";
        if (out.apply_now) {
          await refreshCorePanel();
        }
      } catch (err) {
        status.textContent = `Feedback failed: ${err.message}`;
      }
    };
  }

  if (!btnWeekly.dataset.wired) {
    btnWeekly.dataset.wired = "1";
    btnWeekly.onclick = async () => {
      status.textContent = "Running weekly apply...";
      try {
        const out = await postJson("/api/trade-feedback/apply-weekly", { max_reviews: 400 });
        if (!out || !out.ok) {
          status.textContent = `Weekly apply failed: ${(out && out.error) || "unknown"}`;
          return;
        }
        status.textContent = `Weekly apply done: ${Number(out.applied_reviews || 0)} reviews, ${Number(out.updated_inputs || 0)} inputs updated.`;
        await refreshCorePanel();
      } catch (err) {
        status.textContent = `Weekly apply failed: ${err.message}`;
      }
    };
  }
}

function renderChartLiquidity(rows) {
  const el = document.getElementById("chart-liquidity");
  if (!el) return;
  if (!rows || rows.length === 0) {
    el.innerHTML = `<div class="empty">No data</div>`;
    return;
  }
  const head = `<div class="row header"><div>Ticker</div><div>Dir</div><div>Pattern</div><div>Chart</div></div>`;
  const body = rows
    .slice(0, 20)
    .map((r) => {
      const link = r.chart_url ? `<a href="${r.chart_url}" target="_blank" rel="noreferrer">open chart</a>` : "";
      return `<div class="row"><div>${r.ticker || ""}</div><div>${r.direction || ""}</div><div>${r.pattern || ""}</div><div>${link}</div></div>`;
    })
    .join("");
  el.innerHTML = head + body;
}

function renderSignalReadiness(readiness) {
  const checks = readiness?.checks || [];
  const first = {
    state: readiness?.state || "unknown",
    score: readiness?.score ?? 0,
    blockers: (readiness?.blockers || []).length,
    checks: checks.length,
  };
  renderTable("signal-readiness", [first], ["State", "Score", "Blockers", "Checks"], ["state", "score", "blockers", "checks"]);
}

function renderBreakthroughEvents(rows) {
  const view = (rows || []).slice(0, 20).map((r) => ({
    ...r,
    source_short: (r.source || "").slice(0, 22),
    title_short: (r.title || "").slice(0, 90),
  }));
  renderTable("breakthrough-events", view, ["Source", "Modality", "Score", "Title"], ["source_short", "modality", "score", "title_short"]);
}

function renderBreakthroughMap(rows) {
  const view = (rows || []).slice(0, 20).map((r) => ({
    modality: r.modality || "",
    mapped_tickers: r.mapped_tickers || "",
    confidence: r.confidence || "",
  }));
  renderTable("breakthrough-map", view, ["Modality", "Tickers", "Conf"], ["modality", "mapped_tickers", "confidence"]);
}

function renderAllocator(rows) {
  const view = (rows || []).slice(0, 30).map((r) => ({
    ...r,
    allowed_txt: Number(r.allowed || 0) === 1 ? "yes" : "no",
    factor_txt: Number(r.factor || 1).toFixed(2),
    notional_pair: `${Number(r.base_notional || 0).toFixed(0)} -> ${Number(r.adjusted_notional || 0).toFixed(0)}`,
  }));
  renderTable("allocator-decisions", view, ["Ticker", "Source", "Regime", "Factor", "Notional", "Allowed"], ["ticker", "source_tag", "regime", "factor_txt", "notional_pair", "allowed_txt"]);

  const el = document.getElementById("allocator-summary");
  if (!el) return;
  const n = view.length;
  if (!n) {
    el.innerHTML = `<div class="empty">No allocator decisions yet</div>`;
    return;
  }
  const blocked = view.filter((x) => x.allowed_txt === "no").length;
  const avgFactor = view.reduce((s, x) => s + Number(x.factor || 1), 0) / n;
  const regimes = {};
  view.forEach((x) => {
    regimes[x.regime || "unknown"] = (regimes[x.regime || "unknown"] || 0) + 1;
  });
  const topRegime = Object.entries(regimes).sort((a, b) => b[1] - a[1])[0]?.[0] || "unknown";
  renderTable(
    "allocator-summary",
    [{ total: n, blocked, avg_factor: avgFactor.toFixed(2), regime: topRegime }],
    ["Decisions", "Blocked", "Avg Factor", "Top Regime"],
    ["total", "blocked", "avg_factor", "regime"]
  );
}

function bindActions() {
  const btn = document.getElementById("btn-validate-signals");
  const status = document.getElementById("action-status");
  if (!btn || btn.dataset.wired === "1") return;
  btn.dataset.wired = "1";
  btn.onclick = async () => {
    try {
      if (status) status.textContent = "Running validate_signals...";
      const res = await postJson("/api/actions", { action: "validate_signals" });
      if (status) status.textContent = res.ok ? `Started validate_signals (pid ${res.pid})` : `Failed: ${res.error || "unknown"}`;
    } catch (err) {
      if (status) status.textContent = `Failed: ${err.message}`;
    }
  };
}

let advancedLoaded = false;

async function loadAdvancedDiagnostics(force = false) {
  if (advancedLoaded && !force) return;
  const details = document.getElementById("advanced-signals");
  if (!details || !details.open) return;
  const [signalReadiness, signalRoutes, bookmarkTheses, pipelineSignals, executionOrders, sourceScores, eventAlerts, quantValidations, chartLiquidity, breakthroughEvents, allocatorDecisions] = await Promise.all([
    fetchJsonSafe("/api/signal-readiness", {}),
    fetchJsonSafe("/api/signal-routes", []),
    fetchJsonSafe("/api/bookmark-theses", []),
    fetchJsonSafe("/api/pipeline-signals", []),
    fetchJsonSafe("/api/execution-orders", []),
    fetchJsonSafe("/api/source-scores", []),
    fetchJsonSafe("/api/event-alerts", []),
    fetchJsonSafe("/api/quant-validations", []),
    fetchJsonSafe("/api/chart-liquidity", []),
    fetchJsonSafe("/api/breakthrough-events", []),
    fetchJsonSafe("/api/allocator-decisions", []),
  ]);

  renderSignalReadiness(signalReadiness || {});
  renderTable("signal-routes", (signalRoutes || []).slice(0, 30), ["Ticker", "Score", "Decision", "Reason"], ["ticker", "score", "decision", "reason"]);
  renderTable("bookmark-theses", (bookmarkTheses || []).slice(0, 20), ["Source", "Type", "Horizon", "Conf"], ["source_handle", "thesis_type", "horizon", "confidence"]);
  renderTable("pipeline-signals", (pipelineSignals || []).slice(0, 30), ["Pipe", "Asset", "Dir", "Score"], ["pipeline_id", "asset", "direction", "score"]);
  const execRows = (executionOrders || []).slice(0, 30).map((r) => ({
    ...r,
    leverage_allowed: Number(r.leverage_capable || 0) === 1 ? "yes" : "no",
    leverage: `${Number(r.leverage_used || 1).toFixed(2)}x`,
  }));
  renderTable("execution-orders", execRows, ["Ticker", "Dir", "Mode", "Lev Allowed", "Leverage", "Status"], ["ticker", "direction", "mode", "leverage_allowed", "leverage", "order_status"]);
  renderTable("source-scores", (sourceScores || []).slice(0, 20), ["Source", "N", "Appr", "Reliability"], ["source_tag", "sample_size", "approved_rate", "reliability_score"]);
  renderTable("event-alerts", (eventAlerts || []).slice(0, 20), ["Playbook", "Asset", "Dir", "Priority"], ["playbook_id", "proposed_asset", "direction", "priority"]);
  renderTable("quant-validations", (quantValidations || []).slice(0, 40), ["Ticker", "Pass", "EV%", "Win%"], ["ticker", "passed", "expected_value_percent", "win_rate"]);
  renderChartLiquidity(chartLiquidity || []);
  renderBreakthroughEvents(breakthroughEvents || []);
  renderBreakthroughMap(breakthroughEvents || []);
  renderAllocator(allocatorDecisions || []);
  bindActions();
  advancedLoaded = true;
}

function bindAdvancedToggle() {
  const details = document.getElementById("advanced-signals");
  if (!details || details.dataset.wired === "1") return;
  details.dataset.wired = "1";
  details.addEventListener("toggle", async () => {
    if (details.open) {
      await loadAdvancedDiagnostics(false);
    }
  });
}

// ─── Kelly Signal ─────────────────────────────────────────────────────────────

function kellyVerdict(verdict) {
  if (verdict === "pass") return `<span style="color:#4ade80;font-weight:bold;">✓ pass</span>`;
  if (verdict === "warmup") return `<span style="color:#facc15;">⚡ warmup</span>`;
  if (verdict === "warn") return `<span style="color:#fb923c;">⚠ warn</span>`;
  if (verdict === "budget_exceeded") return `<span style="color:#c084fc;">🔒 budget</span>`;
  return `<span style="color:#f87171;">✗ ${escapeHtml(verdict)}</span>`;
}

function convexityBadge(b) {
  const n = Number(b || 0);
  if (n >= 5) return `<span style="color:#4ade80;font-weight:bold;">${n.toFixed(2)} ✦</span>`;
  if (n >= 2) return `<span style="color:#86efac;">${n.toFixed(2)}</span>`;
  if (n >= 1) return `<span style="color:#facc15;">${n.toFixed(2)}</span>`;
  return `<span style="color:#f87171;">${n.toFixed(2)} ▼</span>`;
}

function renderKellyPortfolio(portfolio) {
  const el = document.getElementById("kelly-portfolio-budget");
  if (!el) return;
  const used = Number(portfolio.portfolio_used ?? portfolio.used ?? 0);
  const max = Number(portfolio.portfolio_max ?? portfolio.max ?? 0.20);
  const remaining = Number(portfolio.portfolio_remaining ?? portfolio.remaining ?? max);
  const pct = max > 0 ? Math.min(100, (used / max) * 100) : 0;
  const barColor = pct >= 90 ? "#f87171" : pct >= 70 ? "#facc15" : "#4ade80";
  el.innerHTML = `
    <div class="item">
      <span class="label">Portfolio Kelly Budget</span>
      <span>
        <span style="color:${barColor};font-weight:bold;">${(used * 100).toFixed(1)}%</span>
        used of <strong>${(max * 100).toFixed(0)}%</strong> max
        &nbsp;·&nbsp; <span style="color:#4ade80;">${(remaining * 100).toFixed(1)}% remaining</span>
      </span>
    </div>
    <div style="background:#1e293b;border-radius:4px;height:6px;margin:4px 0 2px;">
      <div style="background:${barColor};width:${pct.toFixed(1)}%;height:6px;border-radius:4px;transition:width 0.4s;"></div>
    </div>`;
}

function renderKellyTable(rows) {
  const el = document.getElementById("kelly-signals-table");
  if (!el) return;
  if (!rows || rows.length === 0) {
    el.innerHTML = `<div class="empty">No Kelly scores yet — runs after candidates are generated.</div>`;
    return;
  }
  const head = `<div class="row header"><div>Ticker</div><div>Dir</div><div>Source</div><div>p (win%)</div><div>b (payout)</div><div>Convexity</div><div>Kelly%</div><div>¼Kelly%</div><div>EV%</div><div>Verdict</div></div>`;
  const body = rows.map((r) => {
    const kelly = Number(r.kelly_fraction || 0);
    const fkelly = Number(r.frac_kelly || 0);
    const kellyColor = kelly > 0.15 ? "#4ade80" : kelly > 0 ? "#86efac" : "#f87171";
    const evColor = Number(r.ev_percent || 0) > 0 ? "#4ade80" : "#f87171";
    const n = r.sample_size || 0;
    return `<div class="row">
      <div><strong>${escapeHtml(r.ticker || "")}</strong></div>
      <div>${dirBadge(r.direction)}</div>
      <div style="font-size:0.75em;opacity:0.75;">${escapeHtml(r.source_tag || "")}</div>
      <div>${(Number(r.win_prob || 0) * 100).toFixed(1)}%<span style="font-size:0.7em;opacity:0.5;margin-left:3px;">(n=${n})</span></div>
      <div>${convexityBadge(r.payout_ratio)}</div>
      <div style="font-size:0.78em;opacity:0.6;">${Number(r.avg_win_pct||0).toFixed(2)}w / ${Number(r.avg_loss_pct||0).toFixed(2)}l</div>
      <div style="color:${kellyColor};font-weight:bold;">${(kelly * 100).toFixed(1)}%</div>
      <div style="color:${kellyColor};">${(fkelly * 100).toFixed(2)}%</div>
      <div style="color:${evColor};">${Number(r.ev_percent || 0) > 0 ? "+" : ""}${Number(r.ev_percent || 0).toFixed(2)}%</div>
      <div>${kellyVerdict(r.verdict)}<div style="font-size:0.7em;opacity:0.5;max-width:120px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="${escapeHtml(r.verdict_reason||"")}">${escapeHtml(r.verdict_reason||"")}</div></div>
    </div>`;
  }).join("");
  el.innerHTML = head + body;
}

async function loadKellySignals() {
  const data = await fetchJsonSafe("/api/kelly-signals", { rows: [], portfolio: {}, summary: {} });
  renderKellyPortfolio(data.portfolio || {});
  renderKellyTable(data.rows || []);
}

// ─── END Kelly Signal ─────────────────────────────────────────────────────────

// ─── Missed Wins ──────────────────────────────────────────────────────────────

function dirBadge(dir) {
  const d = String(dir || "").toUpperCase();
  if (d === "LONG") return `<span style="color:#4ade80;font-weight:bold;">▲ LONG</span>`;
  if (d === "SHORT") return `<span style="color:#f87171;font-weight:bold;">▼ SHORT</span>`;
  return `<span style="opacity:0.5;">${escapeHtml(d)}</span>`;
}

function feedbackBadge(fb) {
  if (fb === "upvote") return `<span style="color:#4ade80;">👍</span>`;
  if (fb === "downvote") return `<span style="color:#f87171;">👎</span>`;
  return "";
}

function renderMissedWinsStats(stats) {
  const el = document.getElementById("missed-wins-stats");
  if (!el) return;
  if (!stats || stats.length === 0) { el.innerHTML = ""; return; }
  el.innerHTML = stats.map((s) => `
    <div class="item">
      <span class="label">${escapeHtml(s.source || s.source_tag || "unknown")}</span>
      <span>${s.total_wins ?? 0} win${(s.total_wins ?? 0) !== 1 ? "s" : ""} (taken: ${s.taken_wins ?? 0}, not-taken: ${s.not_taken_wins ?? 0}) · 👍${s.upvoted ?? 0} 👎${s.downvoted ?? 0}</span>
    </div>`).join("");
}

function renderMissedWinsTable(rows, horizonHours) {
  const el = document.getElementById("missed-wins-table");
  if (!el) return;
  if (!rows || rows.length === 0) {
    el.innerHTML = `<div class="empty">No missed wins at this horizon yet — resolvers will populate this as outcomes come in.</div>`;
    return;
  }
  const head = `<div class="row header"><div>Ticker</div><div>Dir</div><div>Source</div><div>PnL%</div><div>Trade Taken</div><div>Resolved At</div><div>Feedback</div><div>Actions</div></div>`;
  const body = rows.map((r) => {
    const fb = r.user_feedback || "";
    const rid = r.route_id;
    const pnl = r.pnl_percent != null ? `${Number(r.pnl_percent) > 0 ? "+" : ""}${Number(r.pnl_percent).toFixed(2)}%` : "-";
    const taken = String(r.decision || "").toLowerCase() === "approved"
      ? `<span style="color:#4ade80;">yes</span>`
      : `<span style="opacity:0.45;">no</span>`;
    return `<div class="row" data-route-id="${rid}">
      <div><strong>${escapeHtml(r.ticker || "")}</strong></div>
      <div>${dirBadge(r.direction)}</div>
      <div style="font-size:0.78em;opacity:0.75;">${escapeHtml(r.source_tag || "")}</div>
      <div style="color:#4ade80;font-weight:bold;">${pnl}</div>
      <div>${taken}</div>
      <div style="font-size:0.75em;opacity:0.6;">${fmtTs(r.evaluated_at || r.routed_at)}</div>
      <div>${feedbackBadge(fb)}</div>
      <div style="display:flex;gap:6px;">
        <button class="btn-cfb-up" data-rid="${rid}" data-horizon="${horizonHours}" style="font-size:0.75em;padding:2px 8px;background:#1a3a1a;border:1px solid #4ade80;color:#4ade80;cursor:pointer;" title="Upvote: this source reads correctly">👍</button>
        <button class="btn-cfb-down" data-rid="${rid}" data-horizon="${horizonHours}" style="font-size:0.75em;padding:2px 8px;background:#3a1a1a;border:1px solid #f87171;color:#f87171;cursor:pointer;" title="Downvote: this was luck, not skill">👎</button>
      </div>
    </div>`;
  }).join("");
  el.innerHTML = head + body;

  el.querySelectorAll(".btn-cfb-up,.btn-cfb-down").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const rid = parseInt(btn.dataset.rid, 10);
      const horizon = parseInt(btn.dataset.horizon, 10);
      const fb = btn.classList.contains("btn-cfb-up") ? "upvote" : "downvote";
      btn.disabled = true;
      try {
        const res = await postJson("/api/counterfactual-feedback", { route_id: rid, horizon_hours: horizon, feedback: fb });
        const row = btn.closest(".row[data-route-id]");
        if (row) {
          const fbCell = row.querySelector("div:nth-child(7)");
          if (fbCell) fbCell.innerHTML = feedbackBadge(fb);
        }
        btn.parentElement.querySelectorAll("button").forEach((b) => b.disabled = true);
      } catch (err) {
        btn.disabled = false;
        alert(`Failed: ${err.message}`);
      }
    });
  });
}

async function loadMissedWins(force = false) {
  const horizonEl = document.getElementById("missed-wins-horizon");
  const horizon = parseInt((horizonEl && horizonEl.value) || "24", 10);
  const countEl = document.getElementById("missed-wins-count");
  if (countEl) countEl.textContent = "loading…";
  try {
    const data = await fetchJsonSafe(`/api/counterfactual-wins?horizon_hours=${horizon}`, { rows: [], stats: [], total: 0 });
    const rows = data.rows || [];
    const stats = data.stats || [];
    if (countEl) countEl.textContent = rows.length > 0 ? `(${rows.length} found)` : "(none yet)";
    renderMissedWinsStats(stats);
    renderMissedWinsTable(rows, horizon);
  } catch (err) {
    if (countEl) countEl.textContent = "(error)";
  }
}

function renderHorizonRatings(rows) {
  const el = document.getElementById("horizon-ratings-table");
  if (!el) return;
  if (!rows || rows.length === 0) {
    el.innerHTML = `<div class="empty">No horizon data yet — will populate after resolver runs.</div>`;
    return;
  }
  const head = `<div class="row header"><div>Source</div><div>1d</div><div>7d</div><div>14d</div><div>30d</div></div>`;
  const body = rows.map((r) => {
    function hrCell(wr, n) {
      if (n == null || n === 0) return `<div style="opacity:0.3;">-</div>`;
      const pct = Number(wr || 0);
      const color = pct >= 60 ? "#4ade80" : pct >= 50 ? "#facc15" : "#f87171";
      return `<div style="color:${color};font-weight:bold;">${pct.toFixed(0)}%<span style="font-size:0.7em;opacity:0.55;margin-left:3px;">(${n})</span></div>`;
    }
    return `<div class="row">
      <div style="font-size:0.78em;">${escapeHtml(r.source || r.source_tag || "")}</div>
      ${hrCell(r["1d_win_rate"], r["1d_sample"])}
      ${hrCell(r["7d_win_rate"], r["7d_sample"])}
      ${hrCell(r["14d_win_rate"], r["14d_sample"])}
      ${hrCell(r["30d_win_rate"], r["30d_sample"])}
    </div>`;
  }).join("");
  el.innerHTML = head + body;
}

async function loadHorizonRatings() {
  const rows = await fetchJsonSafe("/api/source-horizon-ratings", []);
  renderHorizonRatings(rows || []);
}

function bindMissedWins() {
  const reloadBtn = document.getElementById("btn-missed-wins-reload");
  const horizonEl = document.getElementById("missed-wins-horizon");
  if (reloadBtn) reloadBtn.addEventListener("click", () => loadMissedWins(true));
  if (horizonEl) horizonEl.addEventListener("change", () => loadMissedWins(true));
}

// ─── END Missed Wins ──────────────────────────────────────────────────────────

async function boot() {
  try {
    setStatus("loading");
    const [systemHealth, coreSignals, inputSources] = await Promise.all([
      fetchJsonSafe("/api/system-health", { overall: "warn" }),
      fetchJsonSafe("/api/core-signals", { signals: [], x_sources: [], lookback_hours: 72 }),
      fetchJsonSafe("/api/input-sources", []),
    ]);

    renderCoreSignals(coreSignals || {});
    bindTradeReplayFeedback(inputSources || [], coreSignals || {});
    bindAdvancedToggle();
    bindMissedWins();
    await Promise.all([
      loadKellySignals(),
      loadMissedWins(),
      loadHorizonRatings(),
      loadAdvancedDiagnostics(false),
    ]);

    const topState = (systemHealth && systemHealth.overall) || "good";
    setStatus("online", topState === "good" ? "good" : topState === "warn" ? "warn" : "bad");
  } catch (err) {
    console.error(err);
    setStatus("offline", "bad");
  }
}

boot();
