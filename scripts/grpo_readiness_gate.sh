#!/usr/bin/env bash
set -euo pipefail

ROOT="/Users/Shared/curtis/trader-curtis"
DB="$ROOT/data/trades.db"

if [ ! -f "$DB" ]; then
  echo "grpo_readiness=bad reason=db_missing path=$DB"
  exit 1
fi

sql() { sqlite3 "$DB" "$1" 2>/dev/null || true; }
one() { local out; out="$(sql "$1")"; echo "${out:-}"; }
get_control() {
  local key="$1"
  local fallback="$2"
  local v
  v="$(one "SELECT value FROM execution_controls WHERE key='${key}' LIMIT 1;")"
  if [ -z "$v" ]; then
    echo "$fallback"
  else
    echo "$v"
  fi
}
set_control() {
  local key="$1"
  local value="$2"
  local esc
  esc="$(printf "%s" "$value" | sed "s/'/''/g")"
  sql "
    CREATE TABLE IF NOT EXISTS execution_controls (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      key TEXT NOT NULL UNIQUE,
      value TEXT NOT NULL,
      updated_at TEXT NOT NULL
    );
    INSERT INTO execution_controls (key, value, updated_at)
    VALUES ('${key}', '${esc}', datetime('now'))
    ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=datetime('now');
  " >/dev/null
}

realized_count="$(one "SELECT COUNT(*) FROM route_outcomes WHERE COALESCE(outcome_type,'realized')='realized';")"
operational_count="$(one "SELECT COUNT(*) FROM route_outcomes WHERE COALESCE(outcome_type,'realized')='operational';")"
kaggle_rows="$(one "SELECT COUNT(*) FROM polymarket_kaggle_markets;")"
mlx_status="$(one "SELECT COALESCE(value,'') FROM execution_controls WHERE key='runtime:grpo_mlx_last_status' LIMIT 1;")"
kaggle_status="$(one "SELECT COALESCE(value,'') FROM execution_controls WHERE key='runtime:kaggle_last_status' LIMIT 1;")"
kaggle_last_success_utc="$(one "SELECT COALESCE(value,'') FROM execution_controls WHERE key='runtime:kaggle_last_success_utc' LIMIT 1;")"

min_realized="$(get_control grpo_min_realized_for_live_updates 100)"
min_kaggle_rows="$(get_control grpo_min_kaggle_rows 1000)"
kaggle_max_success_age_hours="$(get_control grpo_kaggle_max_success_age_hours 48)"
auto_unlock="$(get_control grpo_auto_unlock_live_updates 0)"

state="good"
reasons=""
kaggle_success_fresh=0
if [ -n "${kaggle_last_success_utc:-}" ]; then
  kaggle_success_fresh="$(
    python3 - "${kaggle_last_success_utc}" "${kaggle_max_success_age_hours}" <<'PY'
from datetime import datetime, timezone
import sys

ts = (sys.argv[1] or "").strip()
max_h = float(sys.argv[2]) if len(sys.argv) > 2 else 48.0
try:
    if ts.endswith("Z"):
        ts = ts[:-1] + "+00:00"
    dt = datetime.fromisoformat(ts)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    age_h = (datetime.now(timezone.utc) - dt.astimezone(timezone.utc)).total_seconds() / 3600.0
    print("1" if age_h <= max_h else "0")
except Exception:
    print("0")
PY
  )"
fi

if [ "${realized_count:-0}" -lt "${min_realized:-100}" ]; then
  state="warn"
  reasons="${reasons}realized_lt_min;"
fi
if [ "${kaggle_rows:-0}" -lt "${min_kaggle_rows:-1000}" ]; then
  state="warn"
  reasons="${reasons}kaggle_rows_lt_min;"
fi
if ! printf "%s" "${mlx_status:-}" | grep -Eiq '^ok$'; then
  state="warn"
  reasons="${reasons}mlx_status_not_ok;"
fi
if ! printf "%s" "${kaggle_status:-}" | grep -Eiq '^ok' && [ "${kaggle_success_fresh:-0}" != "1" ]; then
  state="warn"
  reasons="${reasons}kaggle_not_recent_success;"
fi

apply_live="$(get_control grpo_apply_weight_updates 0)"
if [ "$state" = "good" ] && [ "$auto_unlock" = "1" ] && [ "$apply_live" != "1" ]; then
  set_control grpo_apply_weight_updates 1
  apply_live=1
fi

set_control runtime:grpo_readiness_state "$state"
set_control runtime:grpo_readiness_checked_utc "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
set_control runtime:grpo_readiness_reasons "$reasons"

cat <<EOF
state=${state}
reasons=${reasons}
realized_count=${realized_count}
operational_count=${operational_count}
min_realized=${min_realized}
kaggle_rows=${kaggle_rows}
min_kaggle_rows=${min_kaggle_rows}
mlx_last_status=${mlx_status}
kaggle_last_status=${kaggle_status}
kaggle_last_success_utc=${kaggle_last_success_utc}
kaggle_success_fresh=${kaggle_success_fresh}
kaggle_max_success_age_hours=${kaggle_max_success_age_hours}
auto_unlock_live_updates=${auto_unlock}
grpo_apply_weight_updates=${apply_live}
EOF

if [ "$state" = "good" ]; then
  exit 0
fi
exit 1
