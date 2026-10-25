"""Source 2: HTML scraping of Wikipedia's list of largest M&A deals.

Wikipedia tables are messy: merged cells (rowspan), footnote markers, units hidden
in headers, and column names that change over time. This parser handles all of
that by expanding the table into a grid and matching columns by keyword.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

import pandas as pd
from bs4 import BeautifulSoup, Tag

from mna_tracker.http import PoliteSession

log = logging.getLogger(__name__)

URL = "https://en.wikipedia.org/wiki/List_of_largest_mergers_and_acquisitions"

COLUMN_ALIASES = {
    "acquirer": ("purchaser", "acquirer", "acquiror", "buyer"),
    "target": ("purchased", "target", "acquired", "seller"),
    "value": ("transaction value", "value", "price"),
    "year": ("year", "date", "announced"),
}

DEAL_COLUMNS = ["year_raw", "acquirer", "target", "value_raw", "value_unit", "source_table"]


def _cell_text(cell: Tag) -> str:
    for sup in cell.find_all("sup"):  # footnote markers like [12]
        sup.decompose()
    return " ".join(cell.get_text(" ", strip=True).split())


def table_to_grid(table: Tag) -> list[list[str]]:
    """Expand an HTML table into a rectangular grid, honouring rowspan and colspan."""
    grid: list[list[str]] = []
    pending: dict[int, tuple[int, str]] = {}  # column -> (rows remaining, text)
    for tr in table.find_all("tr"):
        row: list[str] = []
        cells = tr.find_all(["th", "td"], recursive=False)
        col = 0
        cell_iter = iter(cells)
        while True:
            if col in pending:
                remaining, text = pending[col]
                row.append(text)
                if remaining <= 1:
                    del pending[col]
                else:
                    pending[col] = (remaining - 1, text)
                col += 1
                continue
            cell = next(cell_iter, None)
            if cell is None:
                break
            text = _cell_text(cell)
            colspan = int(cell.get("colspan", 1) or 1)
            rowspan = int(cell.get("rowspan", 1) or 1)
            for _ in range(colspan):
                row.append(text)
                if rowspan > 1:
                    pending[col] = (rowspan - 1, text)
                col += 1
        if row:
            grid.append(row)
    return grid


def _match_columns(header: list[str]) -> dict[str, int]:
    mapping: dict[str, int] = {}
    lowered = [h.lower() for h in header]
    for field, aliases in COLUMN_ALIASES.items():
        for idx, name in enumerate(lowered):
            if field == "value" and ("adjust" in name or "inflation" in name):
                continue  # prefer the nominal value column
            if any(alias in name for alias in aliases) and idx not in mapping.values():
                mapping[field] = idx
                break
    return mapping


def _unit_from_header(header_text: str) -> str:
    text = header_text.lower()
    if "bil" in text or "bn" in text:
        return "billion"
    if "mil" in text or "mn" in text:
        return "million"
    return "unknown"


def parse_tables(html: str) -> pd.DataFrame:
    """Parse every wikitable that looks like an M&A deal list."""
    soup = BeautifulSoup(html, "lxml")
    records = []
    for t_index, table in enumerate(soup.select("table.wikitable")):
        grid = table_to_grid(table)
        if len(grid) < 2:
            continue
        header = grid[0]
        cols = _match_columns(header)
        if not {"acquirer", "target"} <= cols.keys():
            continue
        unit = _unit_from_header(header[cols["value"]]) if "value" in cols else "unknown"
        for row in grid[1:]:
            if len(row) < len(header) or row == header:
                continue
            records.append({
                "year_raw": row[cols["year"]] if "year" in cols else "",
                "acquirer": row[cols["acquirer"]],
                "target": row[cols["target"]],
                "value_raw": row[cols["value"]] if "value" in cols else "",
                "value_unit": unit,
                "source_table": t_index,
            })
    df = pd.DataFrame(records, columns=DEAL_COLUMNS)
    log.info("Wikipedia: parsed %d raw deal rows", len(df))
    return df


def fetch(session: PoliteSession, raw_dir: Path) -> pd.DataFrame:
    raw_dir.mkdir(parents=True, exist_ok=True)
    html = session.get(URL).text
    (raw_dir / "wikipedia_largest_mna.html").write_text(html, encoding="utf-8")
    return parse_tables(html)


def load_offline(fixtures_dir: Path) -> pd.DataFrame:
    return parse_tables((fixtures_dir / "wikipedia_largest_mna.html").read_text(encoding="utf-8"))
