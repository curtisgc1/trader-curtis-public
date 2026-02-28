from flask import Flask, jsonify, request, send_from_directory
from data import (
    approve_polymarket_candidates,
    get_bookmark_theses,
    get_bookmark_alpha_ideas,
    get_breakthrough_events,
    get_allocator_decisions,
    get_bookmarks,
    get_copy_trades,
    get_chart_liquidity_signals,
    get_consensus_candidates,
    get_event_alerts,
    get_execution_orders,
    get_execution_learning,
    get_external_signals,
    get_learning_health,
    get_learning_monitor,
    get_patterns,
    get_polymarket_candidates,
    get_polymarket_aligned_setups,
    get_polymarket_markets,
    get_polymarket_mm_overview,
    get_polymarket_mm_snapshots,
    get_polymarket_orders,
    get_polymarket_overview,
    get_weather_market_probs,
    get_pipeline_signals,
    get_source_scores,
    get_source_learning_stats,
    get_strategy_learning_stats,
    get_input_feature_stats,
    get_memory_integrity,
    get_missed_opportunities,
    get_signal_readiness,
    get_system_health,
    get_trade_claim_guard,
    get_master_overview,
    get_venue_matrix,
    get_venue_readiness,
    get_trade_intents,
    get_position_management_intents,
    get_risk_controls,
    get_wallet_config,
    get_portfolio_snapshot,
    get_recent_trade_decisions,
    get_performance_curve,
    get_pnl_breakdown,
    get_trade_explain,
    submit_trade_feedback,
    apply_weekly_trade_feedback,
    get_quant_validations,
    run_system_action,
    apply_position_protection,
    set_execution_controls,
    set_venue_matrix,
    get_signal_routes,
    get_source_ratings,
    get_input_source_controls,
    get_ticker_trade_profiles,
    get_summary,
    get_agent_awareness,
    get_trade_candidates,
    get_core_signal_overview,
    get_trades,
    get_tracked_sources,
    get_tracked_polymarket_wallets,
    get_trust_panel,
    get_polymarket_wallet_scores,
    upsert_tracked_source,
    upsert_input_source_control,
    upsert_ticker_trade_profile,
    upsert_tracked_polymarket_wallet,
    get_source_horizon_ratings,
    get_counterfactual_wins,
    submit_counterfactual_feedback,
    get_kelly_signals,
    get_exchange_pnl_summary,
    get_alpaca_orders,
    get_hyperliquid_intents,
    submit_alpaca_quick_trade,
    submit_hyperliquid_quick_trade,
    get_system_intelligence,
)
from data_scorecard import (
    get_signal_scorecard,
    get_source_premium_breakdown,
    get_weight_change_history,
    get_polymarket_scorecard,
)

app = Flask(__name__, static_folder="static", static_url_path="/static")
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0


@app.after_request
def add_no_cache_headers(resp):
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp


@app.get("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.get("/learning")
def learning_page():
    return send_from_directory(app.static_folder, "learning.html")


@app.get("/signals")
def signals_page():
    return send_from_directory(app.static_folder, "signals.html")


@app.get("/polymarket")
def polymarket_page():
    return send_from_directory(app.static_folder, "polymarket.html")


@app.get("/consensus")
def consensus_page():
    return send_from_directory(app.static_folder, "consensus.html")


@app.get("/alpaca")
def alpaca_page():
    return send_from_directory(app.static_folder, "alpaca.html")


@app.get("/hyperliquid")
def hyperliquid_page():
    return send_from_directory(app.static_folder, "hyperliquid.html")


@app.get("/api/summary")
def api_summary():
    return jsonify(get_summary())


@app.get("/api/system-health")
def api_system_health():
    return jsonify(get_system_health())


@app.get("/api/trade-claim-guard")
def api_trade_claim_guard():
    return jsonify(get_trade_claim_guard())


@app.get("/api/master-overview")
def api_master_overview():
    return jsonify(get_master_overview())


@app.get("/api/missed-opportunities")
def api_missed_opportunities():
    lookback_days = int(request.args.get("lookback_days", 7))
    return jsonify(get_missed_opportunities(lookback_days=lookback_days))


@app.get("/api/learning-health")
def api_learning_health():
    return jsonify(get_learning_health())


@app.get("/api/learning-monitor")
def api_learning_monitor():
    return jsonify(get_learning_monitor())


@app.get("/api/trades")
def api_trades():
    return jsonify(get_trades())


@app.get("/api/patterns")
def api_patterns():
    return jsonify(get_patterns())


@app.get("/api/copy-trades")
def api_copy_trades():
    return jsonify(get_copy_trades())


@app.get("/api/bookmarks")
def api_bookmarks():
    return jsonify(get_bookmarks())


@app.get("/api/external-signals")
def api_external_signals():
    return jsonify(get_external_signals())


@app.get("/api/candidates")
def api_candidates():
    return jsonify(get_trade_candidates())


@app.get("/api/core-signals")
def api_core_signals():
    lookback_hours = int(request.args.get("lookback_hours", 72))
    return jsonify(get_core_signal_overview(lookback_hours=lookback_hours))


@app.get("/api/risk-controls")
def api_risk_controls():
    return jsonify(get_risk_controls())


@app.get("/api/wallet-config")
def api_wallet_config():
    return jsonify(get_wallet_config())


@app.get("/api/portfolio-snapshot")
def api_portfolio_snapshot():
    return jsonify(get_portfolio_snapshot())


@app.get("/api/recent-trade-decisions")
def api_recent_trade_decisions():
    limit = int(request.args.get("limit", 20))
    return jsonify(get_recent_trade_decisions(limit=limit))


@app.get("/api/agent-awareness")
def api_agent_awareness():
    return jsonify(get_agent_awareness())


@app.get("/api/performance-curve")
def api_performance_curve():
    return jsonify(get_performance_curve())


@app.get("/api/system-intelligence")
def api_system_intelligence():
    return jsonify(get_system_intelligence())


@app.get("/api/pnl-breakdown")
def api_pnl_breakdown():
    limit = int(request.args.get("limit", 120))
    return jsonify(get_pnl_breakdown(limit=limit))


@app.get("/api/trade-explain")
def api_trade_explain():
    identifier = str(request.args.get("identifier", "") or "").strip()
    return jsonify(get_trade_explain(identifier))


@app.post("/api/trade-feedback")
def api_trade_feedback():
    payload = request.get_json(silent=True) or {}
    return jsonify(submit_trade_feedback(payload))


@app.post("/api/trade-feedback/apply-weekly")
def api_trade_feedback_apply_weekly():
    payload = request.get_json(silent=True) or {}
    max_reviews = int(payload.get("max_reviews", 300) or 300)
    return jsonify(apply_weekly_trade_feedback(max_reviews=max_reviews))


@app.post("/api/risk-controls")
def api_risk_controls_update():
    payload = request.get_json(silent=True) or {}
    updates = payload.get("updates", {})
    return jsonify(set_execution_controls(updates))


@app.get("/api/venue-matrix")
def api_venue_matrix():
    return jsonify(get_venue_matrix())


@app.post("/api/venue-matrix")
def api_venue_matrix_update():
    payload = request.get_json(silent=True) or {}
    updates = payload.get("updates", [])
    return jsonify(set_venue_matrix(updates))


@app.get("/api/venue-readiness")
def api_venue_readiness():
    return jsonify(get_venue_readiness())


@app.post("/api/actions")
def api_actions():
    payload = request.get_json(silent=True) or {}
    action = str(payload.get("action", "")).strip()
    return jsonify(run_system_action(action))


@app.post("/api/position-protection")
def api_position_protection():
    payload = request.get_json(silent=True) or {}
    return jsonify(apply_position_protection(payload))


@app.get("/api/signal-routes")
def api_signal_routes():
    return jsonify(get_signal_routes())


@app.get("/api/bookmark-theses")
def api_bookmark_theses():
    return jsonify(get_bookmark_theses())


@app.get("/api/pipeline-signals")
def api_pipeline_signals():
    return jsonify(get_pipeline_signals())


@app.get("/api/execution-orders")
def api_execution_orders():
    limit = int(request.args.get("limit", 120))
    return jsonify(get_execution_orders(limit=limit))


@app.get("/api/source-scores")
def api_source_scores():
    return jsonify(get_source_scores())


@app.get("/api/event-alerts")
def api_event_alerts():
    return jsonify(get_event_alerts())


@app.get("/api/trade-intents")
def api_trade_intents():
    return jsonify(get_trade_intents())


@app.get("/api/id-lookup")
def api_id_lookup():
    """Universal ID lookup — accepts trade_id, route_id (int or 'route_N'), or intent_id."""
    import sqlite3 as _sqlite3
    from pathlib import Path as _Path
    raw = str(request.args.get("id", "") or "").strip()
    if not raw:
        return jsonify({"ok": False, "error": "no id"})

    db = _Path(app.root_path).parent / "data" / "trades.db"
    conn = _sqlite3.connect(str(db), timeout=10)
    conn.row_factory = _sqlite3.Row
    results = []

    # Normalise: strip 'route_' / 'intent_' prefix
    numeric = raw.lstrip("route_").lstrip("intent_")
    try:
        num = int(numeric)
    except ValueError:
        num = None

    # 1. trade_intents by id
    if num is not None:
        rows = conn.execute(
            "SELECT id, created_at, venue, symbol, side, qty, notional, status, details FROM trade_intents WHERE id=?",
            (num,)
        ).fetchall()
        for r in rows:
            results.append({"type": "intent", **dict(r)})

    # 2. trades by route_id
    if num is not None:
        rows = conn.execute(
            "SELECT trade_id, ticker, entry_side, entry_date, entry_price, exit_price, status, pnl_percent, route_id FROM trades WHERE route_id=?",
            (num,)
        ).fetchall()
        for r in rows:
            results.append({"type": "trade_by_route", **dict(r)})

    # 3. trades by trade_id (string match)
    rows = conn.execute(
        "SELECT trade_id, ticker, entry_side, entry_date, entry_price, exit_price, status, pnl_percent, route_id FROM trades WHERE trade_id=? OR trade_id LIKE ?",
        (raw, f"%{raw}%")
    ).fetchall()
    for r in rows:
        if not any(x.get("trade_id") == r["trade_id"] for x in results):
            results.append({"type": "trade", **dict(r)})

    # 4. trade_intents by symbol (if raw looks like a ticker)
    if raw.upper() == raw and len(raw) <= 6 and raw.isalpha():
        rows = conn.execute(
            "SELECT id, created_at, venue, symbol, side, status, details FROM trade_intents WHERE symbol=? ORDER BY created_at DESC LIMIT 10",
            (raw.upper(),)
        ).fetchall()
        for r in rows:
            results.append({"type": "intent_by_ticker", **dict(r)})

    conn.close()
    return jsonify({"ok": True, "query": raw, "results": results})


@app.get("/api/position-management-intents")
def api_position_management_intents():
    limit = int(request.args.get("limit", 120))
    return jsonify(get_position_management_intents(limit=limit))


@app.get("/api/execution-learning")
def api_execution_learning():
    return jsonify(get_execution_learning())


@app.get("/api/source-learning")
def api_source_learning():
    return jsonify(get_source_learning_stats())


@app.get("/api/strategy-learning")
def api_strategy_learning():
    return jsonify(get_strategy_learning_stats())


@app.get("/api/input-feature-stats")
def api_input_feature_stats():
    dimension = str(request.args.get("dimension", "") or "").strip()
    return jsonify(get_input_feature_stats(dimension=dimension))


@app.get("/api/memory-integrity")
def api_memory_integrity():
    return jsonify(get_memory_integrity())


@app.get("/api/signal-readiness")
def api_signal_readiness():
    return jsonify(get_signal_readiness())


@app.get("/api/quant-validations")
def api_quant_validations():
    return jsonify(get_quant_validations())


@app.get("/api/chart-liquidity")
def api_chart_liquidity():
    return jsonify(get_chart_liquidity_signals())


@app.get("/api/bookmark-alpha-ideas")
def api_bookmark_alpha_ideas():
    return jsonify(get_bookmark_alpha_ideas())


@app.get("/api/breakthrough-events")
def api_breakthrough_events():
    return jsonify(get_breakthrough_events())


@app.get("/api/allocator-decisions")
def api_allocator_decisions():
    return jsonify(get_allocator_decisions())


@app.get("/api/polymarket-markets")
def api_polymarket_markets():
    return jsonify(get_polymarket_markets())


@app.get("/api/polymarket-candidates")
def api_polymarket_candidates():
    return jsonify(get_polymarket_candidates())


@app.get("/api/polymarket-aligned-setups")
def api_polymarket_aligned_setups():
    mode = str(request.args.get("mode", "all")).strip()
    return jsonify(get_polymarket_aligned_setups(mode=mode))


@app.get("/api/polymarket-orders")
def api_polymarket_orders():
    limit = int(request.args.get("limit", 120))
    return jsonify(get_polymarket_orders(limit=limit))


@app.get("/api/polymarket-overview")
def api_polymarket_overview():
    return jsonify(get_polymarket_overview())


@app.get("/api/weather-market-probs")
def api_weather_market_probs():
    return jsonify(get_weather_market_probs())


@app.get("/api/polymarket-mm-overview")
def api_polymarket_mm_overview():
    return jsonify(get_polymarket_mm_overview())


@app.get("/api/polymarket-mm-snapshots")
def api_polymarket_mm_snapshots():
    ready_only = str(request.args.get("ready_only", "0")).strip() == "1"
    return jsonify(get_polymarket_mm_snapshots(ready_only=ready_only))


@app.post("/api/polymarket-approve")
def api_polymarket_approve():
    payload = request.get_json(silent=True) or {}
    ids = payload.get("ids", [])
    return jsonify(approve_polymarket_candidates(ids))


@app.get("/api/tracked-sources")
def api_tracked_sources():
    return jsonify(get_tracked_sources())


@app.post("/api/tracked-sources")
def api_tracked_sources_upsert():
    payload = request.get_json(silent=True) or {}
    return jsonify(upsert_tracked_source(payload))


@app.get("/api/input-sources")
def api_input_sources():
    return jsonify(get_input_source_controls())


@app.post("/api/input-sources")
def api_input_sources_upsert():
    payload = request.get_json(silent=True) or {}
    return jsonify(upsert_input_source_control(payload))


@app.get("/api/ticker-trade-profiles")
def api_ticker_trade_profiles():
    return jsonify(get_ticker_trade_profiles())


@app.post("/api/ticker-trade-profiles")
def api_ticker_trade_profiles_upsert():
    payload = request.get_json(silent=True) or {}
    return jsonify(upsert_ticker_trade_profile(payload))


@app.get("/api/tracked-poly-wallets")
def api_tracked_poly_wallets():
    return jsonify(get_tracked_polymarket_wallets())


@app.post("/api/tracked-poly-wallets")
def api_tracked_poly_wallets_upsert():
    payload = request.get_json(silent=True) or {}
    return jsonify(upsert_tracked_polymarket_wallet(payload))


@app.get("/api/polymarket-wallet-scores")
def api_polymarket_wallet_scores():
    return jsonify(get_polymarket_wallet_scores())


@app.get("/api/trust-panel")
def api_trust_panel():
    return jsonify(get_trust_panel())


@app.get("/api/consensus-candidates")
def api_consensus_candidates():
    flagged_only = str(request.args.get("flagged_only", "1")).strip() != "0"
    return jsonify(get_consensus_candidates(flagged_only=flagged_only))


@app.get("/api/source-ratings")
def api_source_ratings():
    return jsonify(get_source_ratings())


@app.get("/api/source-horizon-ratings")
def api_source_horizon_ratings():
    return jsonify(get_source_horizon_ratings())


@app.get("/api/counterfactual-wins")
def api_counterfactual_wins():
    horizon = int(request.args.get("horizon_hours", 24))
    limit = int(request.args.get("limit", 200))
    return jsonify(get_counterfactual_wins(limit=limit, horizon_hours=horizon))


@app.get("/api/kelly-signals")
def api_kelly_signals():
    return jsonify(get_kelly_signals())


@app.get("/api/exchange-pnl")
def api_exchange_pnl():
    return jsonify(get_exchange_pnl_summary())


@app.post("/api/counterfactual-feedback")
def api_counterfactual_feedback():
    data = request.get_json(force=True) or {}
    return jsonify(submit_counterfactual_feedback(
        route_id=int(data.get("route_id", 0)),
        horizon_hours=int(data.get("horizon_hours", 24)),
        feedback=str(data.get("feedback", "pending")),
        notes=str(data.get("notes", "")),
    ))


@app.get("/api/polymarket-scorecard")
def api_polymarket_scorecard():
    return jsonify(get_polymarket_scorecard())


@app.get("/api/signal-scorecard")
def api_signal_scorecard():
    lookback_days = request.args.get("lookback_days")
    min_samples = request.args.get("min_samples")
    return jsonify(get_signal_scorecard(
        lookback_days=int(lookback_days) if lookback_days else None,
        min_samples=int(min_samples) if min_samples else None,
    ))


@app.get("/api/source-premium-breakdown")
def api_source_premium_breakdown():
    source_tag = str(request.args.get("source_tag", "") or "").strip()
    return jsonify(get_source_premium_breakdown(source_tag))


@app.get("/api/weight-history")
def api_weight_history():
    limit = int(request.args.get("limit", 50))
    return jsonify(get_weight_change_history(limit=limit))


@app.get("/api/alpaca-orders")
def api_alpaca_orders():
    limit = int(request.args.get("limit", 120))
    return jsonify(get_alpaca_orders(limit=limit))


@app.get("/api/hyperliquid-intents")
def api_hyperliquid_intents():
    limit = int(request.args.get("limit", 120))
    return jsonify(get_hyperliquid_intents(limit=limit))


@app.post("/api/alpaca-quick-trade")
def api_alpaca_quick_trade():
    payload = request.get_json(silent=True) or {}
    symbol = str(payload.get("symbol", "")).strip()
    side = str(payload.get("side", "")).strip()
    notional = float(payload.get("notional", 0))
    return jsonify(submit_alpaca_quick_trade(symbol, side, notional))


@app.post("/api/hyperliquid-quick-trade")
def api_hyperliquid_quick_trade():
    payload = request.get_json(silent=True) or {}
    symbol = str(payload.get("symbol", "")).strip()
    side = str(payload.get("side", "")).strip()
    notional = float(payload.get("notional", 0))
    return jsonify(submit_hyperliquid_quick_trade(symbol, side, notional))


if __name__ == "__main__":
    # Local-only by default; change host to 0.0.0.0 if needed.
    app.run(host="127.0.0.1", port=8090, debug=False)
