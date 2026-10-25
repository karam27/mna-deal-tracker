-- M&A Deal Tracker: SQLite schema

CREATE TABLE IF NOT EXISTS companies (
    company_key   TEXT PRIMARY KEY,         -- normalised name used for matching across sources
    display_name  TEXT NOT NULL,
    cik           INTEGER,                  -- SEC Central Index Key (NULL if not SEC-listed)
    ticker        TEXT,
    industry      TEXT
);

CREATE TABLE IF NOT EXISTS sec_filings (
    accession     TEXT PRIMARY KEY,         -- unique SEC filing ID
    cik           INTEGER NOT NULL,
    company_key   TEXT NOT NULL REFERENCES companies(company_key),
    form          TEXT NOT NULL,
    event_type    TEXT NOT NULL,
    items         TEXT,
    filing_date   DATE NOT NULL,
    filing_month  TEXT NOT NULL,
    report_date   DATE,
    description   TEXT,
    url           TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS deals (
    deal_id       TEXT PRIMARY KEY,         -- acquirer|target|year
    year          INTEGER,
    decade        INTEGER,
    acquirer      TEXT NOT NULL,
    target        TEXT NOT NULL,
    acquirer_key  TEXT NOT NULL,
    target_key    TEXT NOT NULL,
    value_usd_bn  REAL
);

CREATE TABLE IF NOT EXISTS pipeline_runs (
    run_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at    TEXT NOT NULL,
    finished_at   TEXT,
    mode          TEXT NOT NULL,            -- live | offline
    source        TEXT NOT NULL,
    rows_in       INTEGER,
    rows_out      INTEGER,
    issues        TEXT,                     -- JSON data-quality report
    status        TEXT NOT NULL             -- success | failed
);

CREATE INDEX IF NOT EXISTS idx_filings_date    ON sec_filings(filing_date);
CREATE INDEX IF NOT EXISTS idx_filings_company ON sec_filings(company_key);
CREATE INDEX IF NOT EXISTS idx_deals_year      ON deals(year);
