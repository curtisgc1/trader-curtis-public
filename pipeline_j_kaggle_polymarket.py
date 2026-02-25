#!/usr/bin/env python3
"""
Pipeline J: Ingest Kaggle Polymarket historical/resolved datasets for training.

This pipeline does NOT create live trade signals.
It stores resolved historical rows into polymarket_kaggle_markets so
GRPO dataset builders can use them as supervision data.
"""

import argparse
import csv
import hashlib
import json
import sqlite3
import subprocess
import sys
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

BASE = Path(__file__).parent
DB_PATH = BASE / "data" / "trades.db"
DATASETS_DIR = BASE / "datasets" / "kaggle"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connect() -> sqlite3.Connection:
    return sqlite3.connect(str(DB_PATH))


def ensure_tables(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS polymarket_kaggle_markets (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          created_at TEXT NOT NULL,
          source_file TEXT NOT NULL,
          source_row_hash TEXT NOT NULL UNIQUE,
          question TEXT NOT NULL,
          market_slug TEXT NOT NULL DEFAULT '',
          category TEXT NOT NULL DEFAULT '',
          outcome_raw TEXT NOT NULL DEFAULT '',
          resolved_direction TEXT NOT NULL DEFAULT 'neutral',
          close_time TEXT NOT NULL DEFAULT '',
          meta_json TEXT NOT NULL DEFAULT '{}'
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_kaggle_markets_close_time
        ON polymarket_kaggle_markets(close_time)
        """
    )
    conn.commit()


def _hash_row(source_file: str, payload: Dict[str, Any]) -> str:
    b = json.dumps({"source_file": source_file, "payload": payload}, sort_keys=True, ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(b).hexdigest()


def _normalize_outcome(raw: str) -> Tuple[str, str]:
    s = (raw or "").strip().lower()
    if s in {"yes", "up", "true", "1", "long"}:
        return s, "long"
    if s in {"no", "down", "false", "0", "short"}:
        return s, "short"
    return s, "neutral"


def _pick(d: Dict[str, Any], *keys: str) -> str:
    for k in keys:
        v = d.get(k)
        if v is not None and str(v).strip() != "":
            return str(v).strip()
    return ""


def _rows_from_jsonl(path: Path) -> Iterable[Dict[str, Any]]:
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except Exception:
            continue
        if isinstance(row, dict):
            yield row


def _rows_from_csv(path: Path) -> Iterable[Dict[str, Any]]:
    with path.open("r", encoding="utf-8", errors="ignore", newline="") as f:
        rdr = csv.DictReader(f)
        for row in rdr:
            yield dict(row)


def _iter_rows(path: Path) -> Iterable[Dict[str, Any]]:
    if path.suffix.lower() == ".jsonl":
        return _rows_from_jsonl(path)
    return _rows_from_csv(path)


def ingest_file(conn: sqlite3.Connection, path: Path, max_rows_per_file: int = 0) -> Tuple[int, int]:
    cur = conn.cursor()
    inserted = 0
    scanned = 0
    src = str(path)
    for row in _iter_rows(path):
        if max_rows_per_file > 0 and scanned >= max_rows_per_file:
            break
        scanned += 1
        # Keep this strict so unrelated Kaggle datasets cannot pollute labels.
        question = _pick(row, "question", "market", "name")
        if not question:
            continue
        outcome_raw = _pick(row, "outcome", "resolved_outcome", "winner", "result", "resolution")
        if not outcome_raw:
            continue
        outcome_norm, resolved = _normalize_outcome(outcome_raw)
        if resolved == "neutral":
            continue
        close_time = _pick(row, "resolved_at", "end_date", "close_time", "market_close_time")
        slug = _pick(row, "slug", "market_slug")
        category = _pick(row, "category", "topic", "tag")
        payload = {
            "question": question,
            "outcome": outcome_norm,
            "resolved_direction": resolved,
            "close_time": close_time,
            "slug": slug,
            "category": category,
        }
        row_hash = _hash_row(src, payload)
        cur.execute(
            """
            INSERT OR IGNORE INTO polymarket_kaggle_markets
            (created_at, source_file, source_row_hash, question, market_slug, category, outcome_raw, resolved_direction, close_time, meta_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                now_iso(),
                src,
                row_hash,
                question[:1200],
                slug[:240],
                category[:120],
                outcome_norm[:64],
                resolved,
                close_time[:120],
                json.dumps(row, ensure_ascii=True)[:4000],
            ),
        )
        inserted += int(cur.rowcount or 0)
    conn.commit()
    return scanned, inserted


def _download_kaggle(slug: str, out_dir: Path) -> str:
    if not slug:
        return "skipped:no_slug"
    out_dir.mkdir(parents=True, exist_ok=True)
    kaggle_bin = shutil.which("kaggle")
    if not kaggle_bin:
        py_scripts = Path(sys.executable).resolve().parent / "kaggle"
        user_scripts = Path.home() / "Library" / "Python" / f"{sys.version_info.major}.{sys.version_info.minor}" / "bin" / "kaggle"
        if py_scripts.exists():
            kaggle_bin = str(py_scripts)
        elif user_scripts.exists():
            kaggle_bin = str(user_scripts)
    if not kaggle_bin:
        return "skipped:no_kaggle_cli"
    cmd = [kaggle_bin]
    cmd.extend(
        [
        "datasets",
        "download",
        "-d",
        slug,
        "-p",
        str(out_dir),
        "--unzip",
        "-q",
        ]
    )
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        msg = (proc.stderr or proc.stdout or "").strip().replace("\n", " ")
        return f"error:{msg[:200]}"
    return "ok"


def main() -> int:
    ap = argparse.ArgumentParser(description="Ingest Kaggle Polymarket resolved datasets into local DB")
    ap.add_argument("--file", default="", help="single csv/jsonl file path")
    ap.add_argument("--dir", default=str(DATASETS_DIR), help="directory to scan for csv/jsonl")
    ap.add_argument("--kaggle-dataset", default="", help="optional kaggle dataset slug (downloads before ingest)")
    ap.add_argument("--max-files", type=int, default=0, help="optional max files to ingest per run (0=all)")
    ap.add_argument("--max-rows-per-file", type=int, default=0, help="optional max rows to scan per file (0=all)")
    args = ap.parse_args()

    d = Path(args.dir).expanduser()
    if args.kaggle_dataset:
        status = _download_kaggle(args.kaggle_dataset, d)
        print(f"kaggle_download={status}")
        if status.startswith("error:"):
            return 2
        if status == "skipped:no_kaggle_cli":
            return 3

    files: List[Path] = []
    if args.file:
        p = Path(args.file).expanduser()
        if p.exists() and p.suffix.lower() in {".csv", ".jsonl"}:
            files.append(p)
    else:
        if d.exists():
            csv_files = sorted(d.glob("*.csv"), key=lambda p: p.stat().st_mtime, reverse=True)
            jsonl_files = sorted(d.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
            files.extend(csv_files)
            files.extend(jsonl_files)
    if args.max_files and args.max_files > 0:
        files = files[: int(args.max_files)]

    conn = _connect()
    conn.execute("PRAGMA busy_timeout=15000")
    try:
        ensure_tables(conn)
        total_scanned = 0
        total_inserted = 0
        for f in files:
            scanned, inserted = ingest_file(conn, f, max_rows_per_file=max(0, int(args.max_rows_per_file or 0)))
            total_scanned += scanned
            total_inserted += inserted
        print(
            f"Pipeline J (Kaggle): files={len(files)} rows_scanned={total_scanned} rows_inserted={total_inserted}"
        )
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
