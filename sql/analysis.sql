-- Analysis queries used by the dashboard. Each query is named with "-- name: <id>".

-- name: kpis
SELECT
    (SELECT COUNT(*) FROM sec_filings)                                   AS total_filings,
    (SELECT COUNT(DISTINCT company_key) FROM sec_filings)                AS companies_with_activity,
    (SELECT COUNT(*) FROM deals)                                         AS total_deals,
    (SELECT ROUND(SUM(value_usd_bn), 1) FROM deals)                      AS total_deal_value_bn,
    (SELECT MAX(filing_date) FROM sec_filings)                           AS latest_filing;

-- name: filings_by_month
SELECT filing_month, event_type, COUNT(*) AS filings
FROM sec_filings
WHERE filing_date >= DATE((SELECT MAX(filing_date) FROM sec_filings), '-24 months')
GROUP BY filing_month, event_type
ORDER BY filing_month;

-- name: most_active_companies
SELECT c.display_name AS company, c.ticker,
       COUNT(*) AS mna_filings,
       SUM(CASE WHEN f.event_type LIKE 'Acquisition completed%' THEN 1 ELSE 0 END) AS completed_acquisitions,
       MAX(f.filing_date) AS last_filing
FROM sec_filings f
JOIN companies c USING (company_key)
GROUP BY c.company_key
ORDER BY mna_filings DESC
LIMIT 15;

-- name: largest_deals
SELECT acquirer, target, year, value_usd_bn
FROM deals
WHERE value_usd_bn IS NOT NULL
ORDER BY value_usd_bn DESC
LIMIT 15;

-- name: deals_by_decade
SELECT decade, COUNT(*) AS deals, ROUND(SUM(value_usd_bn), 1) AS total_value_bn
FROM deals
WHERE decade IS NOT NULL
GROUP BY decade
ORDER BY decade;

-- name: serial_acquirers
-- Companies that appear as acquirers in the historical deal list AND file M&A forms today.
SELECT d.acquirer, COUNT(DISTINCT d.deal_id) AS historical_deals,
       ROUND(SUM(d.value_usd_bn), 1) AS historical_value_bn,
       (SELECT COUNT(*) FROM sec_filings f WHERE f.company_key = d.acquirer_key) AS recent_sec_filings
FROM deals d
GROUP BY d.acquirer_key
ORDER BY historical_value_bn DESC
LIMIT 10;

-- name: recent_filings
SELECT f.filing_date, c.display_name AS company, f.form, f.event_type, f.url
FROM sec_filings f
JOIN companies c USING (company_key)
ORDER BY f.filing_date DESC
LIMIT 25;
