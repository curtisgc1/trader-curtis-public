#!/usr/bin/env python3
"""
Pipeline G: Weather market probability engine (paper advisory).

- Reads active Polymarket markets
- Detects temperature-style markets
- Uses Open-Meteo multi-model forecasts as an ensemble proxy
- Computes per-outcome probabilities using market-style rounded daily max temp
- Stores rows for dashboard + downstream routing
"""

import json
import math
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

DB_PATH = Path(__file__).parent / "data" / "trades.db"
STATION_MAP_PATH = Path(__file__).parent / "docs" / "weather_station_resolver.json"

# Free model set available through Open-Meteo forecast endpoint.
WEATHER_MODELS = [
    "ecmwf_ifs025",
    "gfs_global",
    "icon_global",
    "gem_global",
    "jma_msm",
]

MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connect() -> sqlite3.Connection:
    return sqlite3.connect(str(DB_PATH))


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,))
    return cur.fetchone() is not None


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    cur = conn.cursor()
    cur.execute(f"PRAGMA table_info({table})")
    return any((row[1] == column) for row in cur.fetchall())


def ensure_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS weather_market_probs (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          created_at TEXT NOT NULL,
          market_id TEXT NOT NULL,
          question TEXT NOT NULL,
          city TEXT NOT NULL DEFAULT '',
          target_date TEXT NOT NULL DEFAULT '',
          station_hint TEXT NOT NULL DEFAULT 'city-centroid-proxy',
          source_hint TEXT NOT NULL DEFAULT '',
          rounding_hint TEXT NOT NULL DEFAULT 'nearest-int',
          model_count INTEGER NOT NULL DEFAULT 0,
          outcome_probs_json TEXT NOT NULL DEFAULT '{}',
          best_outcome TEXT NOT NULL DEFAULT '',
          best_prob REAL NOT NULL DEFAULT 0,
          uncertainty REAL NOT NULL DEFAULT 0,
          spread_c REAL NOT NULL DEFAULT 0,
          market_url TEXT NOT NULL DEFAULT '',
          status TEXT NOT NULL DEFAULT 'new',
          notes TEXT NOT NULL DEFAULT ''
        )
        """
    )
    if _table_exists(conn, "weather_market_probs") and not _column_exists(conn, "weather_market_probs", "source_hint"):
        conn.execute("ALTER TABLE weather_market_probs ADD COLUMN source_hint TEXT NOT NULL DEFAULT ''")
    if _table_exists(conn, "weather_market_probs") and not _column_exists(conn, "weather_market_probs", "rounding_hint"):
        conn.execute("ALTER TABLE weather_market_probs ADD COLUMN rounding_hint TEXT NOT NULL DEFAULT 'nearest-int'")
    conn.commit()


def load_controls(conn: sqlite3.Connection) -> Dict[str, str]:
    out: Dict[str, str] = {}
    if not _table_exists(conn, "execution_controls"):
        return out
    cur = conn.cursor()
    cur.execute("SELECT key, value FROM execution_controls")
    for k, v in cur.fetchall():
        out[str(k)] = str(v)
    return out


def load_station_map() -> List[Dict[str, Any]]:
    if not STATION_MAP_PATH.exists():
        return []
    try:
        raw = json.loads(STATION_MAP_PATH.read_text())
        rows = raw.get("stations") if isinstance(raw, dict) else None
        return rows if isinstance(rows, list) else []
    except Exception:
        return []


def resolve_station_strict(question: str, city_hint: str, stations: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    q = str(question or "").lower()
    city = str(city_hint or "").lower()
    best = None
    best_score = -1
    for s in stations:
        aliases = [str(x).lower() for x in (s.get("aliases") or []) if str(x).strip()]
        score = 0
        if city and city == str(s.get("city", "")).lower():
            score += 5
        for a in aliases:
            if a and a in q:
                score += 3
        iata = str(s.get("iata") or "").lower()
        if iata and re.search(rf"(^|[^a-z0-9]){re.escape(iata)}([^a-z0-9]|$)", q):
            score += 4
        if score > best_score:
            best = s
            best_score = score
    if best and best_score >= 3:
        return best
    return None


def parse_city(question: str) -> str:
    q = str(question or "")
    patterns = [
        r"(?:in|for)\s+([A-Z][A-Za-z .'-]{1,40}?)(?:\s+on\s+[A-Za-z]+\s+\d{1,2}|\?|$)",
        r"temperature\s+(?:in|for)\s+([A-Z][A-Za-z .'-]{1,40}?)(?:\?|$)",
    ]
    for p in patterns:
        m = re.search(p, q)
        if m:
            city = re.sub(r"\s+", " ", m.group(1)).strip(" ,.-")
            if city:
                return city
    return ""


def parse_target_date(question: str) -> Optional[datetime]:
    q = str(question or "")
    m = re.search(r"\b(" + "|".join(MONTHS.keys()) + r")\s+(\d{1,2})(?:,\s*(\d{4}))?\b", q, flags=re.IGNORECASE)
    if not m:
        return None
    mon = MONTHS.get(m.group(1).lower())
    day = int(m.group(2))
    year = int(m.group(3) or datetime.now(timezone.utc).year)
    try:
        return datetime(year, mon, day, tzinfo=timezone.utc)
    except Exception:
        return None


def parse_resolution_hints(question: str) -> Dict[str, str]:
    q = str(question or "").lower()
    source_hint = "unspecified"
    if "weather.com" in q:
        source_hint = "weather.com"
    elif "accuweather" in q:
        source_hint = "accuweather"
    elif "noaa" in q or "nws" in q:
        source_hint = "noaa"
    elif "airport" in q:
        source_hint = "airport-observed"

    rounding_hint = "nearest-int"
    if "round down" in q or "rounded down" in q or "floor" in q:
        rounding_hint = "floor-int"
    elif "round up" in q or "rounded up" in q or "ceil" in q:
        rounding_hint = "ceil-int"
    elif "nearest" in q or "rounded" in q:
        rounding_hint = "nearest-int"

    station_text = ""
    m = re.search(r"(?:station|airport)\\s*[:\\-]\\s*([a-z0-9 .\\-']{2,40})", q)
    if m:
        station_text = m.group(1).strip()

    return {
        "source_hint": source_hint,
        "rounding_hint": rounding_hint,
        "station_text": station_text,
    }


def geocode_city(city: str) -> Optional[Tuple[float, float, str]]:
    if not city:
        return None
    try:
        r = requests.get(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={"name": city, "count": 1, "language": "en", "format": "json"},
            timeout=20,
        )
        if r.status_code >= 400:
            return None
        data = r.json()
        rows = data.get("results") if isinstance(data, dict) else None
        if not rows:
            return None
        row = rows[0]
        lat = float(row.get("latitude"))
        lon = float(row.get("longitude"))
        resolved_name = str(row.get("name") or city)
        return lat, lon, resolved_name
    except Exception:
        return None


def _round_market_temp(v: float) -> int:
    # market-style nearest integer with symmetric half-away-from-zero behavior.
    if v >= 0:
        return int(math.floor(v + 0.5))
    return int(math.ceil(v - 0.5))


def _round_market_temp_with_mode(v: float, mode: str) -> int:
    m = str(mode or "nearest-int")
    if m == "floor-int":
        return int(math.floor(v))
    if m == "ceil-int":
        return int(math.ceil(v))
    return _round_market_temp(v)


def parse_outcome_ints(outcomes: List[str]) -> Dict[str, Dict[str, Any]]:
    parsed: Dict[str, Dict[str, Any]] = {}
    for raw in outcomes:
        s = str(raw or "").strip()
        lo = s.lower()
        nums = [int(x) for x in re.findall(r"-?\d+", lo)]
        rule: Dict[str, Any] = {"kind": "unknown", "value": None, "low": None, "high": None}
        if "between" in lo and len(nums) >= 2:
            rule = {"kind": "between", "low": min(nums[0], nums[1]), "high": max(nums[0], nums[1])}
        elif ("or lower" in lo) or ("or below" in lo) or ("<=" in lo):
            if nums:
                rule = {"kind": "lte", "value": nums[0]}
        elif ("or higher" in lo) or ("or above" in lo) or (">=" in lo):
            if nums:
                rule = {"kind": "gte", "value": nums[0]}
        elif nums:
            rule = {"kind": "eq", "value": nums[0]}
        parsed[s] = rule
    return parsed


def eval_outcome_prob(rule: Dict[str, Any], rounded_vals: List[int]) -> float:
    if not rounded_vals:
        return 0.0
    kind = str(rule.get("kind") or "")
    if kind == "eq":
        v = int(rule.get("value"))
        hit = sum(1 for x in rounded_vals if x == v)
    elif kind == "lte":
        v = int(rule.get("value"))
        hit = sum(1 for x in rounded_vals if x <= v)
    elif kind == "gte":
        v = int(rule.get("value"))
        hit = sum(1 for x in rounded_vals if x >= v)
    elif kind == "between":
        lo = int(rule.get("low"))
        hi = int(rule.get("high"))
        hit = sum(1 for x in rounded_vals if lo <= x <= hi)
    else:
        hit = 0
    return round(hit / len(rounded_vals), 4)


def get_model_daily_maxes(lat: float, lon: float, target_date: datetime) -> Dict[str, float]:
    ymd = target_date.strftime("%Y-%m-%d")
    try:
        r = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": lat,
                "longitude": lon,
                "hourly": "temperature_2m",
                "forecast_days": 10,
                "models": ",".join(WEATHER_MODELS),
                "timezone": "UTC",
            },
            timeout=25,
        )
        if r.status_code >= 400:
            return {}
        data = r.json()
    except Exception:
        return {}

    hourly = data.get("hourly") if isinstance(data, dict) else None
    if not isinstance(hourly, dict):
        return {}

    times = hourly.get("time") or []
    if not isinstance(times, list) or not times:
        return {}

    out: Dict[str, float] = {}
    for model in WEATHER_MODELS:
        key = f"temperature_2m_{model}"
        arr = hourly.get(key)
        if not isinstance(arr, list) or len(arr) != len(times):
            continue
        vals: List[float] = []
        for i, ts in enumerate(times):
            if not str(ts).startswith(ymd):
                continue
            v = arr[i]
            if v is None:
                continue
            try:
                vals.append(float(v))
            except Exception:
                pass
        if vals:
            out[model] = max(vals)
    return out


def fetch_weather_markets(conn: sqlite3.Connection, limit: int = 120) -> List[Tuple[Any, ...]]:
    if not _table_exists(conn, "polymarket_markets"):
        return []
    cur = conn.cursor()
    cur.execute(
        """
        SELECT market_id, question, outcomes_json, market_url
        FROM polymarket_markets
        WHERE active=1 AND closed=0
          AND (
            lower(question) LIKE '%temperature%'
            OR lower(question) LIKE '%degrees%'
            OR lower(question) LIKE '%high temp%'
            OR lower(question) LIKE '%max temp%'
          )
        ORDER BY liquidity DESC, volume_24h DESC
        LIMIT ?
        """,
        (int(limit),),
    )
    return cur.fetchall()


def build_weather_probs(conn: sqlite3.Connection) -> int:
    ensure_table(conn)
    controls = load_controls(conn)
    strict_station_required = str(controls.get("weather_strict_station_required", "1")) != "0"
    high_beta_only = str(controls.get("high_beta_only", "1")) != "0"
    min_beta = float(controls.get("high_beta_min_beta", "1.5") or 1.5)
    # Weather markets are event-vol driven; treat as high-beta only if configured min <= 1.0.
    if high_beta_only and min_beta > 1.0:
        # explicit skip when user wants high-beta-only equity/crypto and weather isn't allowed.
        cur = conn.cursor()
        cur.execute("DELETE FROM weather_market_probs")
        conn.commit()
        return 0

    stations = load_station_map()
    cur = conn.cursor()
    cur.execute("DELETE FROM weather_market_probs")
    rows = fetch_weather_markets(conn)
    if not rows:
        conn.commit()
        return 0

    created = 0
    for market_id, question, outcomes_json, market_url in rows:
        q = str(question or "")
        hints = parse_resolution_hints(q)
        city = parse_city(q)
        target_dt = parse_target_date(q)
        if not city or target_dt is None:
            continue

        geo = geocode_city(city)
        if not geo:
            continue
        lat, lon, resolved_city = geo
        station_name = "city-centroid-proxy"
        station_iata = ""
        if strict_station_required:
            rs = resolve_station_strict(q, resolved_city, stations)
            if not rs:
                continue
            lat = float(rs.get("latitude"))
            lon = float(rs.get("longitude"))
            station_name = str(rs.get("station_name") or "strict-station")
            station_iata = str(rs.get("iata") or "")

        model_maxes = get_model_daily_maxes(lat, lon, target_dt)
        if not model_maxes:
            continue

        rounded_vals = [_round_market_temp_with_mode(v, hints.get("rounding_hint", "nearest-int")) for v in model_maxes.values()]
        spread = (max(model_maxes.values()) - min(model_maxes.values())) if len(model_maxes) > 1 else 0.0
        # normalized uncertainty proxy from model spread.
        uncertainty = min(1.0, max(0.0, spread / 10.0))

        try:
            outs_raw = json.loads(outcomes_json or "[]")
            outcomes = [str(x) for x in outs_raw] if isinstance(outs_raw, list) else []
        except Exception:
            outcomes = []

        probs: Dict[str, float] = {}
        if outcomes:
            parsed = parse_outcome_ints(outcomes)
            for out_name, rule in parsed.items():
                probs[out_name] = eval_outcome_prob(rule, rounded_vals)
        else:
            # fallback to exact rounded temp histogram if no explicit outcomes.
            hist: Dict[str, int] = {}
            for v in rounded_vals:
                key = f"{v}C"
                hist[key] = hist.get(key, 0) + 1
            probs = {k: round(v / len(rounded_vals), 4) for k, v in hist.items()}

        if not probs:
            continue

        best_outcome, best_prob = sorted(probs.items(), key=lambda x: x[1], reverse=True)[0]
        notes = (
            f"city={resolved_city}; station={station_name}; iata={station_iata}; strict={int(strict_station_required)}; "
            f"models={len(model_maxes)}; source={hints.get('source_hint','unspecified')}; rounding={hints.get('rounding_hint','nearest-int')}"
        )
        cur.execute(
            """
            INSERT INTO weather_market_probs
            (created_at, market_id, question, city, target_date, station_hint, source_hint, rounding_hint, model_count,
             outcome_probs_json, best_outcome, best_prob, uncertainty, spread_c, market_url, status, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'new', ?)
            """,
            (
                now_iso(),
                str(market_id or ""),
                q,
                resolved_city,
                target_dt.strftime("%Y-%m-%d"),
                station_name,
                str(hints.get("source_hint", "unspecified")),
                str(hints.get("rounding_hint", "nearest-int")),
                int(len(model_maxes)),
                json.dumps(probs),
                str(best_outcome),
                float(best_prob),
                float(round(uncertainty, 4)),
                float(round(spread, 4)),
                str(market_url or ""),
                notes,
            ),
        )
        created += 1

    conn.commit()
    return created


def main() -> int:
    conn = _connect()
    try:
        n = build_weather_probs(conn)
        print(f"PIPELINE_G_WEATHER: markets_scored={n}")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
