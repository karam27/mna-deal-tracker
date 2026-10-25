"""Reporting layer: SQL analysis -> CSV exports (for Power BI / Excel) -> HTML dashboard."""

from __future__ import annotations

import html
import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go

from mna_tracker import config

PALETTE = ["#1f4e79", "#c0504d", "#4f8f6f", "#d39b2a", "#7a5c99", "#3a8fb7", "#8c6d46", "#5f6b7a",
           "#b5577a", "#6b8e23"]
INK = "#1d2733"
MUTED = "#5f6b7a"
GRID = "#e6e9ee"


def load_queries(path: Path | None = None) -> dict[str, str]:
    text = (path or config.SQL_DIR / "analysis.sql").read_text()
    queries = {}
    for block in re.split(r"^-- name: ", text, flags=re.MULTILINE)[1:]:
        name, _, body = block.partition("\n")
        queries[name.strip()] = body.strip().rstrip(";")
    return queries


def run_queries(conn: sqlite3.Connection) -> dict[str, pd.DataFrame]:
    return {name: pd.read_sql_query(sql, conn) for name, sql in load_queries().items()}


def export_csv(conn: sqlite3.Connection, results: dict[str, pd.DataFrame], export_dir: Path) -> list[Path]:
    """Export model tables and analysis results as CSV, ready for Power BI or Excel."""
    export_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for table in ("companies", "sec_filings", "deals"):
        path = export_dir / f"{table}.csv"
        pd.read_sql_query(f"SELECT * FROM {table}", conn).to_csv(path, index=False)
        paths.append(path)
    for name, df in results.items():
        path = export_dir / f"analysis_{name}.csv"
        df.to_csv(path, index=False)
        paths.append(path)
    return paths


def _layout(fig: go.Figure, height: int = 380) -> go.Figure:
    fig.update_layout(
        height=height, margin=dict(l=10, r=10, t=10, b=10),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter, Segoe UI, Arial, sans-serif", size=12, color=INK),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, font=dict(size=11)),
        hoverlabel=dict(font_size=12),
    )
    fig.update_xaxes(gridcolor=GRID, zeroline=False, linecolor=GRID)
    fig.update_yaxes(gridcolor=GRID, zeroline=False, linecolor=GRID)
    return fig


def _fig_html(fig: go.Figure) -> str:
    return fig.to_html(full_html=False, include_plotlyjs=False, config={"displayModeBar": False, "responsive": True})


def build_charts(r: dict[str, pd.DataFrame]) -> dict[str, str]:
    charts: dict[str, str] = {}

    monthly = r["filings_by_month"]
    if not monthly.empty:
        pivot = monthly.pivot_table(index="filing_month", columns="event_type", values="filings",
                                    aggfunc="sum", fill_value=0)
        order = pivot.sum().sort_values(ascending=False).index
        fig = go.Figure()
        for i, col in enumerate(order):
            fig.add_bar(x=pivot.index, y=pivot[col], name=col, marker_color=PALETTE[i % len(PALETTE)])
        fig.update_layout(barmode="stack")
        fig.update_yaxes(title_text="Filings")
        charts["monthly"] = _fig_html(_layout(fig, 400))

    active = r["most_active_companies"]
    if not active.empty:
        a = active.sort_values("mna_filings")
        fig = go.Figure(go.Bar(x=a["mna_filings"], y=a["company"], orientation="h", marker_color=PALETTE[0],
                               text=a["mna_filings"], textposition="outside", cliponaxis=False))
        fig.update_xaxes(title_text="M&A-related filings")
        charts["active"] = _fig_html(_layout(fig, max(260, 34 * len(a) + 60)))

    largest = r["largest_deals"]
    if not largest.empty:
        d = largest.sort_values("value_usd_bn")
        labels = d["acquirer"] + " → " + d["target"] + " (" + d["year"].astype("Int64").astype(str) + ")"
        fig = go.Figure(go.Bar(x=d["value_usd_bn"], y=labels, orientation="h", marker_color=PALETTE[1],
                               text=d["value_usd_bn"].map(lambda v: f"${v:,.1f}bn"), textposition="outside",
                               cliponaxis=False))
        fig.update_xaxes(title_text="Deal value (USD bn)")
        charts["largest"] = _fig_html(_layout(fig, max(300, 34 * len(d) + 60)))

    decade = r["deals_by_decade"]
    if not decade.empty:
        fig = go.Figure(go.Bar(x=decade["decade"].astype(str) + "s", y=decade["total_value_bn"],
                               marker_color=PALETTE[2], customdata=decade["deals"],
                               hovertemplate="%{x}: $%{y:,.1f}bn across %{customdata} deals<extra></extra>"))
        fig.update_yaxes(title_text="Total value (USD bn)")
        charts["decade"] = _fig_html(_layout(fig, 320))

    return charts


def _table(df: pd.DataFrame, link_col: str | None = None) -> str:
    if df.empty:
        return "<p class='muted'>No rows.</p>"
    cols = [c for c in df.columns if c != link_col]
    head = "".join(f"<th>{html.escape(c.replace('_', ' ').title())}</th>" for c in cols)
    body = []
    for _, row in df.iterrows():
        cells = []
        for c in cols:
            value = "" if pd.isna(row[c]) else row[c]
            text = html.escape(f"{value:,.1f}" if isinstance(value, float) else str(value))
            if link_col and c == "form":
                text = f"<a href='{html.escape(str(row[link_col]))}' target='_blank' rel='noopener'>{text}</a>"
            cells.append(f"<td>{text}</td>")
        body.append("<tr>" + "".join(cells) + "</tr>")
    return f"<div class='table-wrap'><table><thead><tr>{head}</tr></thead><tbody>{''.join(body)}</tbody></table></div>"


def build_dashboard(conn: sqlite3.Connection, results: dict[str, pd.DataFrame], out_path: Path, mode: str) -> Path:
    k = results["kpis"].iloc[0]
    charts = build_charts(results)
    runs = pd.read_sql_query(
        "SELECT source, rows_in, rows_out, issues, status, finished_at FROM pipeline_runs "
        "WHERE run_id IN (SELECT MAX(run_id) FROM pipeline_runs GROUP BY source)", conn)
    runs["issues"] = runs["issues"].map(lambda s: ", ".join(f"{a}: {b}" for a, b in json.loads(s or "{}").items()) or "none")

    def kpi(label, value):
        shown = "—" if value is None or pd.isna(value) else (f"{value:,}" if isinstance(value, (int, float)) else value)
        return f"<div class='kpi'><div class='kpi-value'>{html.escape(str(shown))}</div><div class='kpi-label'>{label}</div></div>"

    banner = ""
    if mode == "offline":
        banner = ("<div class='banner'>Demo build: this dashboard was generated from the <b>fictional sample "
                  "fixtures</b> in <code>tests/fixtures</code>. Run <code>make run</code> for live SEC and "
                  "Wikipedia data.</div>")

    def card(title, sub, body, wide=False):
        return (f"<section class='card{' wide' if wide else ''}'><h2>{title}</h2>"
                f"<p class='muted'>{sub}</p>{body}</section>")

    generated = datetime.now(timezone.utc).strftime("%d %b %Y, %H:%M UTC")
    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>M&amp;A Deal Tracker</title>
<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
<style>
:root {{ --ink:{INK}; --muted:{MUTED}; --line:{GRID}; --bg:#f5f7fa; --card:#fff; --accent:#1f4e79; }}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:var(--bg); color:var(--ink); font:14px/1.5 Inter, "Segoe UI", Arial, sans-serif; }}
header {{ background:var(--accent); color:#fff; padding:28px 24px; }}
header h1 {{ margin:0; font-size:24px; }} header p {{ margin:4px 0 0; opacity:.85; }}
main {{ max-width:1200px; margin:0 auto; padding:20px 16px 40px; }}
.banner {{ background:#fff4d6; border:1px solid #f0d58a; padding:10px 14px; border-radius:8px; margin-bottom:16px; }}
.kpis {{ display:grid; grid-template-columns:repeat(auto-fit, minmax(170px,1fr)); gap:12px; margin-bottom:16px; }}
.kpi {{ background:var(--card); border:1px solid var(--line); border-radius:10px; padding:14px 16px; }}
.kpi-value {{ font-size:24px; font-weight:700; }} .kpi-label {{ color:var(--muted); font-size:12px; }}
.grid {{ display:grid; grid-template-columns:repeat(auto-fit, minmax(460px,1fr)); gap:16px; }}
.card {{ background:var(--card); border:1px solid var(--line); border-radius:10px; padding:16px; min-width:0; }}
.card.wide {{ grid-column:1/-1; }}
.card h2 {{ margin:0; font-size:16px; }} .muted {{ color:var(--muted); margin:2px 0 10px; font-size:12px; }}
.table-wrap {{ overflow-x:auto; }} table {{ border-collapse:collapse; width:100%; font-size:13px; }}
th, td {{ text-align:left; padding:7px 8px; border-bottom:1px solid var(--line); white-space:nowrap; }}
th {{ color:var(--muted); font-weight:600; font-size:12px; }} a {{ color:var(--accent); }}
footer {{ color:var(--muted); font-size:12px; margin-top:24px; }}
@media (max-width:540px) {{ .grid {{ grid-template-columns:1fr; }} }}
</style></head><body>
<header><h1>M&amp;A Deal Tracker</h1>
<p>Automated multi-source pipeline · SEC EDGAR + Wikipedia · generated {generated}</p></header>
<main>
{banner}
<div class="kpis">
{kpi("M&A-related SEC filings", int(k.total_filings))}
{kpi("Companies with activity", int(k.companies_with_activity))}
{kpi("Historical deals tracked", int(k.total_deals))}
{kpi("Total deal value (USD bn)", k.total_deal_value_bn)}
{kpi("Latest filing", k.latest_filing)}
</div>
<div class="grid">
{card("M&A filings per month", "Last 24 months, stacked by event type (SEC EDGAR)", charts.get("monthly", ""), wide=True)}
{card("Most active companies", "Count of M&A-related filings on the watchlist", charts.get("active", ""))}
{card("Largest deals", "Top 15 by nominal transaction value (Wikipedia)", charts.get("largest", ""))}
{card("Deal value by decade", "Sum of nominal values; hover for deal counts", charts.get("decade", ""))}
{card("Acquirers in the historical list", "Cross-source join on normalised company names", _table(results["serial_acquirers"]))}
{card("Latest M&A filings", "Click a form type to open the filing on sec.gov", _table(results["recent_filings"], link_col="url"), wide=True)}
{card("Data quality (latest run)", "Rows in/out and issues handled by the cleaning step", _table(runs), wide=True)}
</div>
<footer>Sources: SEC EDGAR submissions API (data.sec.gov) and Wikipedia "List of largest mergers and acquisitions".
Values are nominal USD as reported by the source. Built with Python, pandas, SQLite and Plotly.</footer>
</main></body></html>"""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(page, encoding="utf-8")
    return out_path
