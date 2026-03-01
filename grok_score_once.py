#!/usr/bin/env python3
"""One-shot Grok market scorer — run manually to populate brain_grok_scores."""

import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

DB_PATH = Path(__file__).parent / "data" / "trades.db"
XAI_KEY_PATH = Path.home() / ".secrets" / "xai-api-key.json"


def main():
    with open(XAI_KEY_PATH) as f:
        xai_key = json.load(f)["api_key"]

    conn = sqlite3.connect(str(DB_PATH))
    sample = int(sys.argv[1]) if len(sys.argv) > 1 else 20

    rows = conn.execute(
        """
        SELECT condition_id, slug, question, outcome_prices_json, volume_24h
        FROM polymarket_markets
        WHERE active = 1 AND closed = 0
          AND json_extract(outcome_prices_json, '$[0]') BETWEEN '0.10' AND '0.90'
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
    for i, (cid, slug, question, prices_json, vol24) in enumerate(rows, 1):
        try:
            prices = json.loads(prices_json or "[]")
            price = float(prices[0]) if prices else 0.0
        except (json.JSONDecodeError, IndexError, ValueError):
            price = 0.0
        market_lines.append(
            f'{i}. [{cid}] "{question}" — currently trading at {price:.2f} '
            f"({price * 100:.0f}% YES)"
        )
        market_map[cid] = {"slug": slug, "question": question, "price": price}

    print(f"Scoring {len(rows)} markets via Grok grok-4-1-fast-reasoning...")
    print("Markets:")
    for line in market_lines:
        print(f"  {line}")
    print()

    prompt_body = (
        "Score these Polymarket prediction markets. For each, search X for "
        "the latest discussion and return a JSON array with:\n"
        "- condition_id: (provided)\n"
        '- grok_score: 0-100 (0=strongly NO, 50=neutral, 100=strongly YES)\n'
        '- direction: "yes" | "no" | "neutral"\n'
        "- x_post_count: approximate posts found\n"
        "- rationale: 1 sentence why\n\n"
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
                    "Search X/Twitter for real-time sentiment on each "
                    "prediction market below. Score each one based on what "
                    "people are saying."
                ),
            },
            {"role": "user", "content": prompt_body},
        ],
        "tools": [{"type": "x_search"}],
    }

    print("Calling Grok API (this may take 30-60s)...")
    resp = requests.post(
        "https://api.x.ai/v1/responses",
        headers=headers,
        json=payload,
        timeout=120,
    )
    resp.raise_for_status()

    # Extract text content from /v1/responses output array
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
        print(f"Failed to parse JSON from Grok response ({len(content)} chars):")
        print(content[:2000])
        return

    if not isinstance(items, list):
        items = [items]

    scored_at = datetime.now(timezone.utc).isoformat()
    scored = 0

    print(f"\n{'Score':>5}  {'Dir':>7}  {'Posts':>5}  {'Price':>5}  Question")
    print("-" * 90)

    for item in items:
        cid = str(item.get("condition_id", ""))
        if cid not in market_map:
            continue
        info = market_map[cid]
        score = int(item.get("grok_score", 50))
        direction = str(item.get("direction", "neutral"))
        post_count = int(item.get("x_post_count", 0))
        rationale = str(item.get("rationale", ""))[:500]

        conn.execute(
            """
            INSERT OR REPLACE INTO brain_grok_scores
            (scored_at, condition_id, market_slug, question, current_price,
             grok_score, grok_direction, x_post_count, rationale)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                scored_at, cid, info["slug"], info["question"],
                info["price"], score, direction, post_count, rationale,
            ),
        )
        scored += 1

        label = "BOOST" if score >= 70 else ("BLOCK" if score < 30 else "  -- ")
        q = info["question"][:50]
        print(f"{score:>5}  {direction:>7}  {post_count:>5}  {info['price']:>5.2f}  {q}  [{label}] {rationale[:60]}")

    conn.commit()
    conn.close()
    print(f"\nScored {scored} markets. View at http://localhost:8090/polymarket")


if __name__ == "__main__":
    main()
