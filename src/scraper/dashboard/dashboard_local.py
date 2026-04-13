import os
import polars as pl
import plotly.graph_objects as go
import webbrowser

_SQL_RESULTS = os.path.join(os.path.dirname(__file__), "..", "sql_results")


# ── chart factory ─────────────────────────────────────────────────────────────
_chart_counter = [0]

def make_history_chart_html(product_id: str, store: str, history_df: pl.DataFrame) -> str:
    _chart_counter[0] += 1
    div_id = f"chart_{_chart_counter[0]}"
    data = history_df.filter(
        (pl.col("product_id") == product_id) & (pl.col("store") == store)
    )
    fig = go.Figure()
    if len(data) > 0:
        dates = [str(d) for d in data["scrape_date"].to_list()]
        fig.add_trace(go.Scatter(
            x=dates, y=data["list_price"].to_list(),
            name="List Price", mode="lines+markers",
            line=dict(color="#1565c0", width=2),
            marker=dict(size=5),
        ))
        fig.add_trace(go.Scatter(
            x=dates, y=data["price"].to_list(),
            name="Sale Price", mode="lines+markers",
            line=dict(color="#e65100", width=2),
            marker=dict(size=5),
        ))
    fig.update_layout(
        margin=dict(l=4, r=4, t=4, b=4),
        height=130,
        paper_bgcolor="white",
        plot_bgcolor="#fafafa",
        xaxis=dict(showgrid=False, tickfont=dict(size=9)),
        yaxis=dict(showgrid=True, gridcolor="#eeeeee",
                   tickfont=dict(size=9), tickprefix="$", zeroline=False),
        legend=dict(orientation="h", yanchor="bottom", y=1.08,
                    xanchor="right", x=1, font=dict(size=9)),
    )
    fig_json = fig.to_json()
    return (
        f'<div id="{div_id}" style="flex:2;min-width:220px;height:130px"></div>'
        f'<script>Plotly.newPlot("{div_id}",{fig_json}.data,{fig_json}.layout,'
        f'{{"displayModeBar":false,"responsive":true}});</script>'
    )


# ── HTML builders ─────────────────────────────────────────────────────────────
_NO_IMG_SVG = (
    "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='72' height='72'%3E"
    "%3Crect width='72' height='72' fill='%23e0e0e0'/%3E"
    "%3Ctext x='50%25' y='55%25' dominant-baseline='middle' text-anchor='middle' "
    "fill='%23999' font-size='10'%3ENo img%3C/text%3E%3C/svg%3E"
)


def product_row_html(row: dict, history_df: pl.DataFrame, is_increase: bool,
                     col_before: str, col_after: str) -> str:
    color  = "#c62828" if is_increase else "#2e7d32"
    arrow  = "▲" if is_increase else "▼"
    img    = row.get("image")
    img_src = img if (img is not None and str(img).startswith("http")) else _NO_IMG_SVG
    link   = row.get("link")
    href   = link if link is not None else "#"
    before = row[col_before]
    after  = row[col_after]
    name   = str(row.get("name", "")).replace("<", "&lt;").replace(">", "&gt;")
    brand  = str(row.get("brand", "")).replace("<", "&lt;").replace(">", "&gt;")
    chart  = make_history_chart_html(row["product_id"], row["store"], history_df)
    pct_change = row["pct_change"]
    return f"""
    <div style="display:flex;align-items:center;padding:12px 16px;gap:8px;
                border-bottom:1px solid #e0e0e0;">
      <img src="{img_src}" style="width:72px;height:72px;object-fit:contain;
           border-radius:6px;flex-shrink:0;" onerror="this.src='{_NO_IMG_SVG}'"/>
      <div style="flex:1;padding:0 16px;min-width:0;overflow:hidden;">
        <a href="{href}" target="_blank"
           style="font-weight:600;font-size:13px;color:#1565c0;
                  text-decoration:none;line-height:1.4;display:block;">{name}</a>
        <div style="color:#757575;font-size:11px;margin-top:2px;">{brand}</div>
        <div style="color:{color};font-weight:700;font-size:13px;margin-top:6px;">
          {arrow} {pct_change:.1f}%&nbsp;&nbsp;(${before:.2f} → ${after:.2f})
        </div>
      </div>
      {chart}
    </div>"""


def store_section_html(store_name: str, df: pl.DataFrame, history_df: pl.DataFrame,
                       is_increase: bool, col_before: str, col_after: str) -> str:
    rows = "".join(
        product_row_html(r, history_df, is_increase, col_before, col_after)
        for r in df.to_dicts()
    )
    return f"""
    <div style="border:1px solid #e0e0e0;border-radius:8px;overflow:hidden;
                margin-bottom:24px;background:#fff;box-shadow:0 1px 4px rgba(0,0,0,.06);">
      <div style="padding:10px 16px;font-weight:700;font-size:14px;
                  background:#e8eaf6;letter-spacing:.03em;">{store_name.title()}</div>
      {rows}
    </div>"""


def tab_section_html(df: pl.DataFrame, history_df: pl.DataFrame, is_increase: bool,
                     col_before: str, col_after: str) -> str:
    if df.is_empty():
        return '<p style="padding:40px;color:#757575;">No data available.</p>'
    return "".join(
        store_section_html(st, df.filter(pl.col("store") == st), history_df, is_increase, col_before, col_after)
        for st in sorted(df["store"].unique().to_list())
    )


# ── build full HTML page ───────────────────────────────────────────────────────
def build_dashboard():
  # ── load data from sql_results CSVs ─────────────────────────────────────────
  SQL_RESULTS = _SQL_RESULTS
  result_list_increase  = pl.read_csv(os.path.join(SQL_RESULTS, "list_price_increases.csv")).rename({"pct_increase": "pct_change"})
  result_list_decrease  = pl.read_csv(os.path.join(SQL_RESULTS, "list_price_decreases.csv")).rename({"pct_decrease": "pct_change"})
  result_price_decrease = pl.read_csv(os.path.join(SQL_RESULTS, "discounts.csv")).rename({"pct_decrease": "pct_change"})
  result_best_deals     = pl.read_csv(os.path.join(SQL_RESULTS, "30d_avg_deals.csv")).rename({"pct_discount": "pct_change"})

  history_list_increase  = pl.read_csv(os.path.join(SQL_RESULTS, "list_price_increases_history.csv"))
  history_list_decrease  = pl.read_csv(os.path.join(SQL_RESULTS, "list_price_decreases_history.csv"))
  history_price_decrease = pl.read_csv(os.path.join(SQL_RESULTS, "discounts_history.csv"))
  history_best_deals     = pl.read_csv(os.path.join(SQL_RESULTS, "avg_deals_30d_history.csv"))

  _chart_counter[0] = 0

  sec_list_inc   = tab_section_html(result_list_increase,  history_list_increase,
                                    True,  "prev_list_price", "current_list_price")
  sec_list_dec   = tab_section_html(result_list_decrease,  history_list_decrease,
                                    False, "prev_list_price", "current_list_price")
  sec_price_dec  = tab_section_html(result_price_decrease, history_price_decrease,
                                    False, "prev_price",      "current_price")
  sec_best_deals = tab_section_html(result_best_deals,     history_best_deals,
                                    False, "avg_price_30d",   "current_price")

  HTML = f"""<!DOCTYPE html>
  <html lang="en">
  <head>
    <meta charset="UTF-8"/>
    <meta name="viewport" content="width=device-width,initial-scale=1"/>
    <title>Price Changes Dashboard</title>
    <script src="https://cdn.plot.ly/plotly-2.32.0.min.js"></script>
    <style>
      *{{box-sizing:border-box;margin:0;padding:0}}
      body{{font-family:'Segoe UI',Inter,Arial,sans-serif;background:#f5f5f5;min-height:100vh}}
      .header{{font-size:20px;font-weight:700;padding:18px 32px;background:#1565c0;color:#fff}}
      .tabs{{display:flex;border-bottom:2px solid #e0e0e0;background:#fff;padding:0 28px}}
      .tab{{padding:14px 22px;cursor:pointer;font-size:14px;font-weight:600;
            color:#757575;border-bottom:3px solid transparent;margin-bottom:-2px}}
      .tab.active{{color:#1565c0;border-bottom-color:#1565c0}}
      .tab:hover{{color:#1565c0}}
      .panel{{display:none;padding:28px;max-width:1280px;margin:0 auto}}
      .panel.active{{display:block}}
    </style>
  </head>
  <body>
    <div class="header">&#128202; Price Changes Dashboard</div>
    <div class="tabs">
      <div class="tab active" onclick="show('inc',this)">&#128200; List Price Increases</div>
      <div class="tab"        onclick="show('dec',this)">&#127991; List Price Decreases</div>
      <div class="tab"        onclick="show('pdec',this)">&#128176; Price Decreases</div>
      <div class="tab"        onclick="show('deals',this)">&#127381; Best Deals (vs 30d avg)</div>
    </div>
    <div id="inc"   class="panel active">{sec_list_inc}</div>
    <div id="dec"   class="panel">{sec_list_dec}</div>
    <div id="pdec"  class="panel">{sec_price_dec}</div>
    <div id="deals" class="panel">{sec_best_deals}</div>
    <script>
      function show(id,el){{
        document.querySelectorAll('.panel').forEach(p=>p.classList.remove('active'));
        document.querySelectorAll('.tab').forEach(t=>t.classList.remove('active'));
        document.getElementById(id).classList.add('active');
        el.classList.add('active');
      }}
    </script>
  </body>
  </html>"""

  out_path = os.path.join(os.path.dirname(__file__), "dashboard.html")
  with open(out_path, "w", encoding="utf-8") as f:
      f.write(HTML)

  print(f"Dashboard saved to: {out_path}")

  webbrowser.open(out_path)
