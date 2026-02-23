from flask import Flask, jsonify, request, send_from_directory
from data import (
    get_bookmark_theses,
    get_bookmark_alpha_ideas,
    get_bookmarks,
    get_copy_trades,
    get_chart_liquidity_signals,
    get_event_alerts,
    get_execution_orders,
    get_execution_learning,
    get_external_signals,
    get_learning_health,
    get_patterns,
    get_polymarket_candidates,
    get_polymarket_markets,
    get_pipeline_signals,
    get_source_scores,
    get_source_learning_stats,
    get_strategy_learning_stats,
    get_memory_integrity,
    get_signal_readiness,
    get_system_health,
    get_trade_intents,
    get_risk_controls,
    get_quant_validations,
    run_system_action,
    set_execution_controls,
    get_signal_routes,
    get_summary,
    get_trade_candidates,
    get_trades,
)

app = Flask(__name__, static_folder="static", static_url_path="/static")


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


@app.get("/api/summary")
def api_summary():
    return jsonify(get_summary())


@app.get("/api/system-health")
def api_system_health():
    return jsonify(get_system_health())


@app.get("/api/learning-health")
def api_learning_health():
    return jsonify(get_learning_health())


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


@app.post("/api/risk-controls")
def api_risk_controls_update():
    payload = request.get_json(silent=True) or {}
    updates = payload.get("updates", {})
    return jsonify(set_execution_controls(updates))


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
    return jsonify(get_execution_orders())


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


@app.get("/api/polymarket-markets")
def api_polymarket_markets():
    return jsonify(get_polymarket_markets())


@app.get("/api/polymarket-candidates")
def api_polymarket_candidates():
    return jsonify(get_polymarket_candidates())


if __name__ == "__main__":
    # Local-only by default; change host to 0.0.0.0 if needed.
    app.run(host="127.0.0.1", port=8090, debug=False)
