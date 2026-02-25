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
    set_execution_controls,
    set_venue_matrix,
    get_signal_routes,
    get_source_ratings,
    get_input_source_controls,
    get_ticker_trade_profiles,
    get_summary,
    get_agent_awareness,
    get_trade_candidates,
    get_trades,
    get_tracked_sources,
    get_tracked_polymarket_wallets,
    get_trust_panel,
    get_polymarket_wallet_scores,
    upsert_tracked_source,
    upsert_input_source_control,
    upsert_ticker_trade_profile,
    upsert_tracked_polymarket_wallet,
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


if __name__ == "__main__":
    # Local-only by default; change host to 0.0.0.0 if needed.
    app.run(host="127.0.0.1", port=8090, debug=False)
