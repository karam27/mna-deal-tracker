import pandas as pd
import pytest

from mna_tracker import transform


@pytest.mark.parametrize("raw, unit, expected", [
    ("$ 182.4", "billion", 182.4),
    ("27,500", "million", 27.5),
    ("US$ 1.2 trillion", "unknown", 1200.0),
    ("850 million", "billion", 0.85),
    ("$ 140.0[2]", "billion", 140.0),
    ("—", "billion", None),
    ("", "billion", None),
])
def test_parse_value_bn(raw, unit, expected):
    result = transform.parse_value_bn(raw, unit)
    assert result == pytest.approx(expected) if expected is not None else result is None


@pytest.mark.parametrize("name, key", [
    ("Wayne Enterprises, Inc.", "wayne enterprises"),
    ("Acme Holdings Inc.", "acme"),
    ("Tyrell Corp.", "tyrell"),
    ("Tyrell Corporation", "tyrell"),
    ("Procter & Gamble Co.", "procter and gamble"),
])
def test_company_key_normalises_legal_suffixes(name, key):
    assert transform.company_key(name) == key


def test_parse_year():
    assert transform.parse_year("March 2022") == 2022
    assert transform.parse_year("n/a") is None


def _raw_deals(rows):
    return pd.DataFrame(rows, columns=["year_raw", "acquirer", "target", "value_raw", "value_unit", "source_table"])


def test_clean_deals_dedupes_and_reports():
    raw = _raw_deals([
        ("2018", "Oscorp Industries", "Tyrell Corp.", "68.0", "billion", 0),
        ("2018", "Oscorp Industries Inc", "Tyrell Corporation", "68.0", "billion", 0),
        ("2024", "Massive Dynamic", "Gringotts", "—", "billion", 0),
        ("2020", "", "Nobody", "1.0", "billion", 0),
        ("2019", "Big Co", "Small Co", "5000", "billion", 0),
    ])
    clean, report = transform.clean_deals(raw)
    assert len(clean) == 3
    assert report.issues == {"missing_company_name": 1, "missing_value": 1,
                             "implausible_value": 1, "duplicate_deal": 1}
    assert clean["deal_id"].is_unique


def test_clean_filings_drops_bad_dates_and_duplicates():
    raw = pd.DataFrame({
        "cik": [1, 1, 1], "company": ["Acme Inc.", "Acme Inc.", "Acme Inc."], "ticker": "ACME",
        "industry": "x", "form": "425", "event_type": "Merger communication", "items": "",
        "filing_date": ["2026-01-05", "2026-01-05", "not-a-date"], "report_date": ["", "", ""],
        "accession": ["a-1", "a-1", "a-2"], "description": "", "url": "u",
    })
    clean, report = transform.clean_filings(raw)
    assert len(clean) == 1
    assert report.issues == {"invalid_filing_date": 1, "duplicate_accession": 1}
    assert clean.loc[0, "filing_month"] == "2026-01"
