"""
db.py
SQLite schema (Sec 7.3: "Store: SQLite (MVP) ... Parquet for features").
Two tables:
  - suggestion_feedback: exactly Sec 5.1.5's schema, append-only (FR-33).
  - audit_log: SEC-04 tamper-evident append-only log, SHA-256 hash-chained
    over records so any row's hash depends on every prior row -- a rewritten
    history changes every subsequent hash, which is what "tamper-evident"
    means for a table without a real ledger/blockchain behind it.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent.parent / "data" / "gci.db"


def get_connection(db_path: Path = DB_PATH) -> sqlite3.Connection:
    db_path.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    init_schema(conn)
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS suggestion_feedback (
            suggestion_id TEXT PRIMARY KEY,
            ts_issued TEXT NOT NULL,
            ts_responded TEXT,
            transition_id TEXT NOT NULL,
            type TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            sources_json TEXT NOT NULL,
            predicted_effect_json TEXT NOT NULL,
            response TEXT,
            reject_reason TEXT,
            operator_id TEXT,
            realised_effect_json TEXT,
            model_version TEXT NOT NULL,
            t_sec REAL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            event_type TEXT NOT NULL,
            record_json TEXT NOT NULL,
            prev_hash TEXT NOT NULL,
            hash TEXT NOT NULL
        )
    """)
    # Migration guard: a database file created before t_sec existed won't get
    # it from CREATE TABLE IF NOT EXISTS (that only fires on brand-new
    # tables), so add it explicitly if it's missing. Without this, ts_issued
    # (real wall-clock time) gets wrongly diffed against a transition's
    # simulated start time in the Event Timeline, producing a meaningless
    # multi-day "seconds" figure.
    existing_cols = {row["name"] for row in conn.execute("PRAGMA table_info(suggestion_feedback)")}
    if "t_sec" not in existing_cols:
        conn.execute("ALTER TABLE suggestion_feedback ADD COLUMN t_sec REAL")
    conn.commit()


def append_audit_record(conn: sqlite3.Connection, ts: str, event_type: str, record: dict) -> str:
    """SEC-04: append-only, hash-chained."""
    cur = conn.execute("SELECT hash FROM audit_log ORDER BY id DESC LIMIT 1")
    row = cur.fetchone()
    prev_hash = row["hash"] if row else "GENESIS"
    record_json = json.dumps(record, sort_keys=True, default=str)
    digest_input = f"{prev_hash}|{ts}|{event_type}|{record_json}".encode()
    this_hash = hashlib.sha256(digest_input).hexdigest()
    conn.execute(
        "INSERT INTO audit_log (ts, event_type, record_json, prev_hash, hash) VALUES (?,?,?,?,?)",
        (ts, event_type, record_json, prev_hash, this_hash),
    )
    conn.commit()
    return this_hash


def verify_audit_chain(conn: sqlite3.Connection) -> tuple[bool, int | None]:
    """Recomputes every hash from scratch; returns (intact, first_broken_id)."""
    rows = conn.execute("SELECT * FROM audit_log ORDER BY id ASC").fetchall()
    prev_hash = "GENESIS"
    for row in rows:
        digest_input = f"{prev_hash}|{row['ts']}|{row['event_type']}|{row['record_json']}".encode()
        expected = hashlib.sha256(digest_input).hexdigest()
        if expected != row["hash"]:
            return False, row["id"]
        prev_hash = row["hash"]
    return True, None
