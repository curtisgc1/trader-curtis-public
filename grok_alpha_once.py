#!/usr/bin/env python3
"""One-shot Grok alpha scanner — find breaking news affecting Polymarket."""

import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

DB_PATH = Path(__file__).parent / "data" / "trades.db"
XAI_KEY_PATH = Path.home() / ".secrets" / "xai-api-key.json"


def main():
    dry_run = "--dry-run" in sys.argv or "-n" in sys.argv

    with open(XAI_KEY_PATH) as f:
        xai_key = json.load(f)["api_key"]

    conn = sqlite3.connect(str(DB_PATH))
    sample = 50

    rows = conn.execute(
        """
        SELECT condition_id, slug, question, outcome_prices_json,
               clob_token_ids_json
        FROM polymarket_markets
        WHERE active = 1 AND closed = 0
          AND json_extract(outcome_prices_json, '$[0]') BETWEEN '0.05' AND '0.95'
        ORDER BY volume_24h DESC
        LIMIT ?
        """,
        (sample,),
    ).fetchall()

    if not rows:
        print("No active markets found")
        return

    market_lines = []
    market_map = {}
    for i, (cid, slug, question, prices_json, tokens_json) in enumerate(rows, 1):
        try:
            prices = json.loads(prices_json or "[]")
            price = float(prices[0]) if prices else 0.0
        except (json.JSONDecodeError, IndexError, ValueError):
            price = 0.0
        try:
            tokens = json.loads(tokens_json or "[]")
        except json.JSONDecodeError:
            tokens = []
        market_lines.append(f'{i}. [{cid}] "{question}" — YES={price:.0%}')
        market_map[cid] = {
            "slug": slug, "question": question, "price": price,
            "yes_token": tokens[0] if len(tokens) > 0 else "",
            "no_token": tokens[1] if len(tokens) > 1 else "",
        }

    print(f"Scanning {len(rows)} markets for breaking news via Grok...")
    if dry_run:
        print("(DRY RUN — no orders will be placed)\n")

    prompt = (
        "Search X/Twitter for the LATEST NEWS and discussion about each "
        "prediction market below. For EVERY market where you find relevant "
        "recent posts (last 6-12 hours), give your confidence estimate.\n\n"
        "Return a JSON array. For each market with relevant X activity:\n"
        "- condition_id: (provided)\n"
        "- grok_confidence: 0-100 (your probability estimate for YES based "
        "on what you found on X right now)\n"
        '- direction: "yes" or "no" (which side has the edge)\n'
        "- news_summary: 1-2 sentences about what X is saying\n"
        '- urgency: "high" if breaking news, "medium" if developing\n\n'
        "Be opinionated — if X sentiment or news clearly disagrees with the "
        "current market price, flag it. Include at least your top 5-10 "
        "markets where X discussion suggests the price is wrong.\n\n"
        "Only return an empty array [] if you genuinely cannot find any "
        "X discussion about ANY of these markets.\n\n"
        "Markets:\n" + "\n".join(market_lines)
    )

    headers = {
        "Authorization": f"Bearer {xai_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "grok-4-1-fast-reasoning",
        "input": [
            {
                "role": "system",
                "content": (
                    "You are an aggressive prediction market analyst. "
                    "Search X/Twitter for every market below and give your "
                    "honest probability estimate based on what people are "
                    "saying and any news you find. If the current market "
                    "price looks wrong based on X sentiment, say so. "
                    "Return results for any market where you have a view."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "tools": [{"type": "x_search"}],
    }

    print("Calling Grok API (may take 30-90s)...")
    resp = requests.post(
        "https://api.x.ai/v1/responses",
        headers=headers,
        json=payload,
        timeout=180,
    )
    resp.raise_for_status()

    content = ""
    for block in resp.json().get("output", []):
        if isinstance(block.get("content"), list):
            for item in block["content"]:
                if item.get("type") == "output_text":
                    content += item.get("text", "")
        elif isinstance(block.get("content"), str):
            content += block["content"]

    try:
        if "```json" in content:
            json_str = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            json_str = content.split("```")[1].split("```")[0]
        else:
            json_str = content
        items = json.loads(json_str)
    except (json.JSONDecodeError, IndexError):
        print(f"Failed to parse JSON ({len(content)} chars):")
        print(content[:3000])
        return

    if not isinstance(items, list):
        items = [items]

    if not items:
        print("\nNo actionable breaking news found. Empty scan.")
        return

    min_edge = 20
    detected_at = datetime.now(timezone.utc).isoformat()

    print(f"\n{'Edge':>5}  {'Dir':>4}  {'Grok':>4}  {'Mkt':>4}  {'Urgency':>7}  Question")
    print("-" * 100)

    for item in items:
        cid = str(item.get("condition_id", ""))
        if cid not in market_map:
            continue
        info = market_map[cid]
        confidence = int(item.get("grok_confidence", 50))
        direction = str(item.get("direction", "neutral"))
        news = str(item.get("news_summary", ""))[:500]
        urgency = str(item.get("urgency", "medium"))

        market_pct = info["price"] * 100
        if direction == "yes":
            edge = confidence - market_pct
            token_id = info["yes_token"]
        else:
            edge = market_pct - confidence
            token_id = info["no_token"]

        action = "BET" if edge >= min_edge else "skip"
        q = info["question"][:45]
        print(
            f"{edge:>+5.0f}  {direction:>4}  {confidence:>4}  "
            f"{market_pct:>4.0f}  {urgency:>7}  {q}  [{action}]"
        )
        print(f"       {news[:90]}")

        conn.execute(
            """
            INSERT INTO brain_grok_alpha
            (detected_at, condition_id, token_id, market_slug, question,
             market_price, grok_confidence, direction, edge_pct,
             news_summary, bet_size_usd, status, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
            """,
            (
                detected_at, cid, token_id, info["slug"],
                info["question"], info["price"], confidence,
                direction, edge, news,
                "detected" if dry_run else "skipped",
                f"one-shot edge={edge:.1f}%",
            ),
        )

    conn.commit()
    conn.close()
    print(f"\nDone. View at http://localhost:8090/polymarket")


if __name__ == "__main__":
    main()
