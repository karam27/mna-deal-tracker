"""Source 1: SEC EDGAR JSON API.

Pulls each watchlist company's filing history and keeps the filings that signal
M&A activity (merger registrations, merger proxies, tender offers, completed
acquisitions reported on 8-K Item 2.01).

Docs: https://www.sec.gov/search-filings/edgar-application-programming-interfaces
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pandas as pd

from mna_tracker import config
from mna_tracker.http import PoliteSession

log = logging.getLogger(__name__)

TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
ARCHIVE_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/{document}"

FILING_COLUMNS = [
    "cik", "company", "ticker", "industry", "form", "event_type", "items",
    "filing_date", "report_date", "accession", "description", "url",
]


def resolve_ciks(tickers_payload: dict, tickers: list[str]) -> dict[str, dict]:
    """Map ticker -> {cik, title} using SEC's company_tickers.json payload."""
    lookup = {row["ticker"].upper(): row for row in tickers_payload.values()}
    resolved = {}
    for ticker in tickers:
        row = lookup.get(ticker.upper())
        if row is None:
            log.warning("Ticker %s not found in SEC ticker list; skipping", ticker)
            continue
        resolved[ticker.upper()] = {"cik": int(row["cik_str"]), "title": row["title"]}
    return resolved


def parse_submissions(payload: dict, ticker: str | None = None) -> pd.DataFrame:
    """Flatten one company's submissions JSON into one row per filing."""
    recent = payload.get("filings", {}).get("recent", {})
    if not recent or not recent.get("accessionNumber"):
        return pd.DataFrame(columns=FILING_COLUMNS)

    df = pd.DataFrame({
        "accession": recent.get("accessionNumber", []),
        "filing_date": recent.get("filingDate", []),
        "report_date": recent.get("reportDate", []),
        "form": recent.get("form", []),
        "items": recent.get("items", [""] * len(recent["accessionNumber"])),
        "document": recent.get("primaryDocument", []),
        "description": recent.get("primaryDocDescription", []),
    })
    cik = int(payload["cik"])
    df["cik"] = cik
    df["company"] = payload.get("name", "")
    df["ticker"] = ticker or ((payload.get("tickers") or [""])[0])
    df["industry"] = payload.get("sicDescription", "")
    df["url"] = [
        ARCHIVE_URL.format(cik=cik, accession=acc.replace("-", ""), document=doc)
        for acc, doc in zip(df["accession"], df["document"])
    ]
    return df


def classify_mna(filings: pd.DataFrame) -> pd.DataFrame:
    """Keep only M&A-related filings and label each with an event type."""
    if filings.empty:
        return filings.assign(event_type=pd.Series(dtype=str))[FILING_COLUMNS]

    def event_type(row) -> str | None:
        if row["form"] in config.MNA_FORMS:
            return config.MNA_FORMS[row["form"]]
        if row["form"] in ("8-K", "8-K/A"):
            items = {i.strip() for i in str(row["items"] or "").split(",")}
            for item, label in config.MNA_8K_ITEMS.items():
                if item in items:
                    return label
        return None

    out = filings.copy()
    out["event_type"] = out.apply(event_type, axis=1)
    out = out[out["event_type"].notna()]
    return out[FILING_COLUMNS].reset_index(drop=True)


def fetch(session: PoliteSession, tickers: list[str], raw_dir: Path) -> pd.DataFrame:
    """Live extraction: resolve tickers, download submissions, save raw JSON, return M&A filings."""
    raw_dir.mkdir(parents=True, exist_ok=True)
    tickers_payload = session.get(TICKERS_URL).json()
    (raw_dir / "company_tickers.json").write_text(json.dumps(tickers_payload))

    frames = []
    for ticker, meta in resolve_ciks(tickers_payload, tickers).items():
        try:
            payload = session.get(SUBMISSIONS_URL.format(cik=meta["cik"])).json()
        except Exception as exc:  # one failing company must not stop the run
            log.error("SEC fetch failed for %s: %s", ticker, exc)
            continue
        (raw_dir / f"submissions_{ticker}.json").write_text(json.dumps(payload))
        mna = classify_mna(parse_submissions(payload, ticker))
        log.info("SEC %-5s %4d M&A filings", ticker, len(mna))
        frames.append(mna)

    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=FILING_COLUMNS)


def load_offline(fixtures_dir: Path) -> pd.DataFrame:
    """Offline extraction from saved JSON files (used by tests and the demo run)."""
    frames = []
    for path in sorted(fixtures_dir.glob("submissions_*.json")):
        ticker = path.stem.split("_", 1)[1]
        payload = json.loads(path.read_text())
        frames.append(classify_mna(parse_submissions(payload, ticker)))
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=FILING_COLUMNS)
