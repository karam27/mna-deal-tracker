"""Cleaning, standardisation and validation.

Every cleaning step records what it changed, so each run produces a data-quality
report instead of silently dropping rows.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

import pandas as pd

log = logging.getLogger(__name__)

_FOOTNOTE = re.compile(r"\[[^\]]*\]")
_NUMBER = re.compile(r"\d[\d,]*\.?\d*")
_YEAR = re.compile(r"\b(19\d{2}|20\d{2})\b")
_LEGAL_SUFFIXES = re.compile(
    r"[,\s]+(inc|incorporated|corp|corporation|co|company|plc|ltd|limited|llc|lp|ag|sa|nv|se|group|holdings)\.?$",
    re.IGNORECASE,
)


@dataclass
class QualityReport:
    source: str
    rows_in: int = 0
    rows_out: int = 0
    issues: dict[str, int] = field(default_factory=dict)

    def add(self, issue: str, count: int) -> None:
        if count:
            self.issues[issue] = self.issues.get(issue, 0) + int(count)

    def summary(self) -> str:
        details = ", ".join(f"{k}={v}" for k, v in self.issues.items()) or "no issues"
        return f"[{self.source}] {self.rows_in} in -> {self.rows_out} out ({details})"


def clean_text(value) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    text = _FOOTNOTE.sub("", str(value)).replace("\xa0", " ")
    return " ".join(text.split()).strip(" ,;")


def company_key(name: str) -> str:
    """Normalised key for matching the same company written different ways."""
    key = clean_text(name).lower().replace("&", "and")
    previous = None
    while previous != key:  # strip stacked suffixes, e.g. "Holdings Inc."
        previous = key
        key = _LEGAL_SUFFIXES.sub("", key).strip()
    return re.sub(r"[^a-z0-9]+", " ", key).strip()


def parse_value_bn(raw: str, unit: str = "unknown") -> float | None:
    """Convert a deal-value string to USD billions. Returns None if no number is present."""
    text = clean_text(raw).lower()
    match = _NUMBER.search(text)
    if not match:
        return None
    number = float(match.group().replace(",", ""))
    if "trillion" in text:
        return number * 1000
    if "billion" in text or re.search(r"\d\s*bn\b", text):
        return number
    if "million" in text or re.search(r"\d\s*(mn|m)\b", text):
        return number / 1000
    if unit == "million":
        return number / 1000
    return number  # default/unknown unit: tables are labelled in billions


def parse_year(raw: str) -> int | None:
    match = _YEAR.search(clean_text(raw))
    return int(match.group()) if match else None


def clean_deals(raw: pd.DataFrame) -> tuple[pd.DataFrame, QualityReport]:
    report = QualityReport("wikipedia_deals", rows_in=len(raw))
    df = raw.copy()
    df["acquirer"] = df["acquirer"].map(clean_text)
    df["target"] = df["target"].map(clean_text)
    df["year"] = df["year_raw"].map(parse_year)
    df["value_usd_bn"] = [parse_value_bn(v, u) for v, u in zip(df["value_raw"], df["value_unit"])]

    missing_names = (df["acquirer"] == "") | (df["target"] == "")
    report.add("missing_company_name", missing_names.sum())
    df = df[~missing_names]

    report.add("missing_value", df["value_usd_bn"].isna().sum())
    report.add("missing_year", df["year"].isna().sum())
    implausible = df["value_usd_bn"].notna() & ((df["value_usd_bn"] <= 0) | (df["value_usd_bn"] > 1000))
    report.add("implausible_value", implausible.sum())
    df.loc[implausible, "value_usd_bn"] = None

    df["acquirer_key"] = df["acquirer"].map(company_key)
    df["target_key"] = df["target"].map(company_key)
    df["deal_id"] = (
        df["acquirer_key"] + "|" + df["target_key"] + "|" + df["year"].astype("Int64").astype(str)
    ).str.replace(" ", "-")

    before = len(df)
    df = df.sort_values("value_usd_bn", ascending=False, na_position="last")
    df = df.drop_duplicates("deal_id", keep="first")
    report.add("duplicate_deal", before - len(df))

    df["decade"] = (df["year"] // 10 * 10).astype("Int64")
    out = df[["deal_id", "year", "decade", "acquirer", "target", "value_usd_bn",
              "acquirer_key", "target_key"]].reset_index(drop=True)
    out["year"] = out["year"].astype("Int64")
    report.rows_out = len(out)
    log.info(report.summary())
    return out, report


def clean_filings(raw: pd.DataFrame) -> tuple[pd.DataFrame, QualityReport]:
    report = QualityReport("sec_filings", rows_in=len(raw))
    df = raw.copy()
    df["company"] = df["company"].map(clean_text)
    df["filing_date"] = pd.to_datetime(df["filing_date"], errors="coerce")
    df["report_date"] = pd.to_datetime(df["report_date"].replace("", None), errors="coerce")

    bad_dates = df["filing_date"].isna()
    report.add("invalid_filing_date", bad_dates.sum())
    df = df[~bad_dates]

    before = len(df)
    df = df.drop_duplicates("accession", keep="first")
    report.add("duplicate_accession", before - len(df))

    df["company_key"] = df["company"].map(company_key)
    df["filing_month"] = df["filing_date"].dt.to_period("M").astype(str)
    df = df.sort_values("filing_date", ascending=False).reset_index(drop=True)
    report.rows_out = len(df)
    log.info(report.summary())
    return df, report
