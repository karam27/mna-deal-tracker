import sqlite3

from mna_tracker import pipeline


def _run(tmp_path):
    return pipeline.run(
        offline=True,
        db_path=tmp_path / "test.db",
        raw_dir=tmp_path / "raw",
        export_dir=tmp_path / "exports",
        dashboard_path=tmp_path / "index.html",
    )


def test_offline_pipeline_end_to_end(tmp_path):
    summary = _run(tmp_path)
    assert summary["failed"] == []
    assert summary["loaded"]["sec"] > 0 and summary["loaded"]["wiki"] > 0
    html = (tmp_path / "index.html").read_text()
    assert "M&amp;A Deal Tracker" in html and "Demo build" in html
    assert (tmp_path / "exports" / "deals.csv").exists()


def test_pipeline_is_idempotent(tmp_path):
    _run(tmp_path)
    _run(tmp_path)  # second run must update rows, not duplicate them
    conn = sqlite3.connect(tmp_path / "test.db")
    filings = conn.execute("SELECT COUNT(*), COUNT(DISTINCT accession) FROM sec_filings").fetchone()
    deals = conn.execute("SELECT COUNT(*), COUNT(DISTINCT deal_id) FROM deals").fetchone()
    runs = conn.execute("SELECT COUNT(*) FROM pipeline_runs").fetchone()[0]
    assert filings[0] == filings[1] and deals[0] == deals[1]
    assert runs == 4  # 2 sources x 2 runs are logged


def test_cross_source_company_matching(tmp_path):
    _run(tmp_path)
    conn = sqlite3.connect(tmp_path / "test.db")
    matched = conn.execute(
        "SELECT COUNT(DISTINCT d.acquirer_key) FROM deals d JOIN companies c ON c.company_key = d.acquirer_key"
    ).fetchone()[0]
    assert matched >= 3  # Acme, Globex, Initech, Umbrella appear in both sources
