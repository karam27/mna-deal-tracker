"""Central configuration: paths, watchlist and source settings."""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
EXPORT_DIR = DATA_DIR / "exports"
LOG_DIR = DATA_DIR / "logs"
DB_PATH = DATA_DIR / "mna.db"
DOCS_DIR = ROOT / "docs"
SQL_DIR = ROOT / "sql"
FIXTURES_DIR = ROOT / "tests" / "fixtures"

# SEC asks every automated client to identify itself with a name and contact email.
# Set it in your shell or as a GitHub Actions secret:
#   export SEC_USER_AGENT="Your Name your.email@example.com"
SEC_USER_AGENT = os.getenv("SEC_USER_AGENT", "MnA-Deal-Tracker research contact@example.com")

# SEC fair-access policy allows up to 10 requests/second; we stay well below it.
SEC_MIN_INTERVAL_SECONDS = 0.25
WIKI_MIN_INTERVAL_SECONDS = 1.0

# Companies to monitor for M&A-related SEC filings (edit freely).
WATCHLIST = [
    "MSFT", "GOOGL", "AMZN", "AAPL", "META",
    "PFE", "MRK", "ABBV", "JNJ", "BMY",
    "AVGO", "CSCO", "ORCL", "CRM", "ADBE",
    "XOM", "CVX", "COP", "JPM", "COF",
]

# SEC form types that signal an M&A event, mapped to a readable event type.
MNA_FORMS = {
    "S-4": "Merger registration",
    "S-4/A": "Merger registration (amended)",
    "425": "Merger communication",
    "DEFM14A": "Definitive merger proxy",
    "PREM14A": "Preliminary merger proxy",
    "DEFM14C": "Merger information statement",
    "SC TO-T": "Tender offer (bidder)",
    "SC TO-T/A": "Tender offer (bidder, amended)",
    "SC 14D9": "Tender offer (target response)",
    "SC 14D9/A": "Tender offer (target response, amended)",
}

# 8-K items that signal M&A. Item 2.01 = completion of an acquisition or disposition.
MNA_8K_ITEMS = {
    "2.01": "Acquisition completed (8-K 2.01)",
}
