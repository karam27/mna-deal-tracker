import json

from mna_tracker import config
from mna_tracker.scrapers import sec_edgar, wikipedia

FIX = config.FIXTURES_DIR


def test_resolve_ciks_skips_unknown_tickers():
    payload = json.loads((FIX / "company_tickers.json").read_text())
    resolved = sec_edgar.resolve_ciks(payload, ["acme", "NOPE"])
    assert resolved == {"ACME": {"cik": 1000001, "title": "Acme Holdings Inc."}}


def test_parse_submissions_builds_filing_urls():
    payload = json.loads((FIX / "submissions_ACME.json").read_text())
    df = sec_edgar.parse_submissions(payload, "ACME")
    assert len(df) == len(payload["filings"]["recent"]["accessionNumber"])
    first = df.iloc[0]
    assert first["url"].startswith("https://www.sec.gov/Archives/edgar/data/1000001/")
    assert "-" not in first["url"].split("/")[-2]


def test_classify_keeps_only_mna_filings():
    payload = json.loads((FIX / "submissions_GLBX.json").read_text())
    mna = sec_edgar.classify_mna(sec_edgar.parse_submissions(payload, "GLBX"))
    allowed = set(config.MNA_FORMS) | {"8-K", "8-K/A"}
    assert set(mna["form"]) <= allowed
    eight_k = mna[mna["form"] == "8-K"]
    assert eight_k["items"].str.contains("2.01").all()
    assert mna["event_type"].notna().all()


def test_wikipedia_parser_handles_rowspan_footnotes_and_units():
    deals = wikipedia.load_offline(FIX)
    # rowspan: the 2nd deal inherits "2019" from the merged year cell
    stark = deals[deals["target"] == "Stark Biotech PLC"].iloc[0]
    assert stark["year_raw"] == "2019"
    # footnote markers are stripped
    assert "Vertex Labs Corp." in set(deals["target"])
    # nominal value is used, not the inflation-adjusted column
    assert stark["value_raw"] == "$ 140.0"
    # the second table is detected and its unit read from the header
    assert set(deals.loc[deals["target"] == "Pied Piper Inc.", "value_unit"]) == {"million"}
    # the unrelated table is ignored
    assert "a" not in set(deals["acquirer"])
