"""Pipeline entry point: extract -> transform -> load -> report.

Usage:
    python -m mna_tracker.pipeline              # live run (SEC + Wikipedia)
    python -m mna_tracker.pipeline --offline    # demo/test run from tests/fixtures
    python -m mna_tracker.pipeline --sources sec
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

from mna_tracker import config, load, report, transform
from mna_tracker.http import PoliteSession
from mna_tracker.scrapers import sec_edgar, wikipedia

log = logging.getLogger("mna_tracker")


def setup_logging(log_dir: Path, verbose: bool = False) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s", "%Y-%m-%d %H:%M:%S")
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(logging.DEBUG if verbose else logging.INFO)
    for handler in (logging.StreamHandler(sys.stdout), logging.FileHandler(log_dir / "pipeline.log")):
        handler.setFormatter(fmt)
        root.addHandler(handler)


def run(offline: bool = False, sources: tuple[str, ...] = ("sec", "wiki"),
        db_path: Path = config.DB_PATH, raw_dir: Path = config.RAW_DIR,
        export_dir: Path = config.EXPORT_DIR, dashboard_path: Path = config.DOCS_DIR / "index.html",
        fixtures_dir: Path = config.FIXTURES_DIR) -> dict:
    mode = "offline" if offline else "live"
    started = datetime.now(timezone.utc).isoformat(timespec="seconds")
    log.info("Pipeline started (mode=%s, sources=%s)", mode, ",".join(sources))
    conn = load.connect(db_path)
    summary: dict = {"mode": mode, "loaded": {}, "failed": []}

    steps = {
        "sec": (
            lambda: sec_edgar.load_offline(fixtures_dir) if offline else sec_edgar.fetch(
                PoliteSession(config.SEC_USER_AGENT, config.SEC_MIN_INTERVAL_SECONDS),
                config.WATCHLIST, raw_dir),
            transform.clean_filings, load.load_filings, "sec_filings"),
        "wiki": (
            lambda: wikipedia.load_offline(fixtures_dir) if offline else wikipedia.fetch(
                PoliteSession(config.SEC_USER_AGENT, config.WIKI_MIN_INTERVAL_SECONDS), raw_dir),
            transform.clean_deals, load.load_deals, "wikipedia_deals"),
    }

    for name in sources:
        extract, clean, loader, label = steps[name]
        try:
            raw = extract()
            clean_df, quality = clean(raw)
            loaded = loader(conn, clean_df)
            load.log_run(conn, started, mode, quality)
            summary["loaded"][name] = loaded
            log.info("Loaded %d rows from %s", loaded, name)
        except Exception:  # isolate source failures; keep the rest of the run alive
            log.exception("Source %s failed", name)
            load.log_run(conn, started, mode, transform.QualityReport(label), status="failed")
            summary["failed"].append(name)

    results = report.run_queries(conn)
    exports = report.export_csv(conn, results, export_dir)
    dashboard = report.build_dashboard(conn, results, dashboard_path, mode)
    conn.close()
    summary.update(exports=len(exports), dashboard=str(dashboard))
    log.info("Exported %d CSV files; dashboard written to %s", len(exports), dashboard)
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="M&A Deal Tracker pipeline")
    parser.add_argument("--offline", action="store_true", help="use saved fixtures instead of the network")
    parser.add_argument("--sources", default="sec,wiki", help="comma-separated: sec,wiki")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)

    setup_logging(config.LOG_DIR, args.verbose)
    sources = tuple(s.strip() for s in args.sources.split(",") if s.strip())
    unknown = set(sources) - {"sec", "wiki"}
    if unknown:
        parser.error(f"unknown sources: {', '.join(sorted(unknown))}")
    summary = run(offline=args.offline, sources=sources)
    return 1 if summary["failed"] and not summary["loaded"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
