"""Load clean data into SQLite with idempotent upserts and run logging."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from mna_tracker import config
from mna_tracker.transform import QualityReport


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript((config.SQL_DIR / "schema.sql").read_text())
    return conn


def _upsert(conn: sqlite3.Connection, table: str, df: pd.DataFrame, key: str) -> int:
    if df.empty:
        return 0
    cols = list(df.columns)
    placeholders = ", ".join("?" for _ in cols)
    updates = ", ".join(f"{c} = excluded.{c}" for c in cols if c != key)
    sql = (f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({placeholders}) "
           f"ON CONFLICT({key}) DO UPDATE SET {updates}")
    rows = [
        tuple(None if pd.isna(v) else (v.item() if hasattr(v, "item") else v) for v in row)
        for row in df.itertuples(index=False, name=None)
    ]
    conn.executemany(sql, rows)
    return len(rows)


def load_filings(conn: sqlite3.Connection, filings: pd.DataFrame) -> int:
    if filings.empty:
        return 0
    companies = (
        filings.sort_values("filing_date", ascending=False)
        .drop_duplicates("company_key")[["company_key", "company", "cik", "ticker", "industry"]]
        .rename(columns={"company": "display_name"})
    )
    _upsert(conn, "companies", companies, "company_key")
    table = filings[["accession", "cik", "company_key", "form", "event_type", "items",
                     "filing_date", "filing_month", "report_date", "description", "url"]].copy()
    table["filing_date"] = table["filing_date"].dt.strftime("%Y-%m-%d")
    table["report_date"] = table["report_date"].dt.strftime("%Y-%m-%d")
    count = _upsert(conn, "sec_filings", table, "accession")
    conn.commit()
    return count


def load_deals(conn: sqlite3.Connection, deals: pd.DataFrame) -> int:
    count = _upsert(conn, "deals", deals, "deal_id")
    conn.commit()
    return count


def log_run(conn: sqlite3.Connection, started_at: str, mode: str,
            report: QualityReport, status: str = "success") -> None:
    conn.execute(
        "INSERT INTO pipeline_runs (started_at, finished_at, mode, source, rows_in, rows_out, issues, status) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (started_at, datetime.now(timezone.utc).isoformat(timespec="seconds"), mode,
         report.source, report.rows_in, report.rows_out, json.dumps(report.issues), status),
    )
    conn.commit()
