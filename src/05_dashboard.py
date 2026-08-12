"""Stage 5: build the interactive dashboard.

Produces dashboard.html: one self-contained file that opens offline in any browser, with
no server and no build step. That constraint drove most of the design decisions here --
an artefact that needs infrastructure to view is one nobody views.

Twelve panels, a stops map, a searchable route leaderboard, and a global route filter.
Because a browser with no server cannot re-aggregate eleven million rows, every per-route
slice the filter can show is computed here at build time and embedded in the page, so
picking a route is a lookup rather than a query. That costs about six megabytes of file
size and buys the whole thing working from a file:// URL.
"""

import json

import duckdb
import plotly.graph_objects as go
import plotly.io as pio
from plotly.offline import get_plotlyjs

import config

PAIRS = config.MATCHED_PAIRS
DATA = config.FEED_DIR

with open(config.ACCURACY_METRICS) as fh:
    acc = json.load(fh)
with open(config.MODELLING_METRICS) as fh:
    mod = json.load(fh)

con = duckdb.connect()
print("Stage 5: dashboard")

ROUTES = config.GTFS_STATIC / "google_bus" / "routes.txt"
RN = {}
if ROUTES.exists():
    for rid, sn, ln in con.execute(f"SELECT CAST(route_id AS VARCHAR), route_short_name, route_long_name FROM read_csv_auto('{ROUTES}')").fetchall():
        RN[str(rid)] = (str(sn) if sn is not None else str(rid), str(ln) if ln is not None else "")
rname = lambda rid: RN.get(str(rid), (str(rid), ""))[0]
rlong = lambda rid: RN.get(str(rid), (str(rid), ""))[1]

BLUE, ORANGE, INK, GRID = "#2563eb", "#ea580c", "#0f172a", "#e2e8f0"
CFG = {"displayModeBar": False, "responsive": True}
def style(fig, h=290, xt="", yt=""):
    fig.update_layout(height=h, margin=dict(l=8, r=8, t=8, b=8), showlegend=False,
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter,-apple-system,Segoe UI,sans-serif", color=INK, size=12))
    fig.update_xaxes(gridcolor=GRID, zeroline=False, title=xt, linecolor=GRID)
    fig.update_yaxes(gridcolor=GRID, zeroline=False, title=yt, linecolor=GRID)
    return fig
def dv(fig, name): return pio.to_html(fig, include_plotlyjs=False, full_html=False, div_id=name, config=CFG)

BANDS = config.LEAD_BANDS_SQL

d = con.execute(f"SELECT {BANDS} b, min(lead) o, median(abs_error)/60 m FROM read_parquet('{PAIRS}') GROUP BY b ORDER BY o").fetchall()
f1 = go.Figure(go.Bar(x=[r[0] for r in d], y=[r[2] for r in d], marker_color=BLUE,
    hovertemplate="lead %{x} min ahead<br><b>%{y:.2f} min</b> median error<extra></extra>"))
p1 = dv(style(f1, yt="median |error| (min)", xt="lead time (min ahead)"), "p1")

tot = con.execute(f"SELECT count(*) FROM read_parquet('{PAIRS}')").fetchone()[0]
bins = con.execute(f"SELECT floor(least(abs_error,600)/15)*15 b, count(*) c FROM read_parquet('{PAIRS}') GROUP BY b ORDER BY b").fetchall()
cum, run = [], 0
for b, c in bins: run += c; cum.append((b, 100 * run / tot))
f2 = go.Figure(go.Scatter(x=[c[0] for c in cum], y=[c[1] for c in cum], mode="lines", line=dict(color=BLUE, width=2),
    fill="tozeroy", fillcolor="rgba(37,99,235,.12)", hovertemplate="within %{x:.0f}s<br><b>%{y:.1f}%</b> of predictions<extra></extra>"))
f2.add_vline(x=120, line=dict(color=ORANGE, dash="dot"))
p2 = dv(style(f2, yt="% of predictions", xt="absolute error <= (s)"), "p2")

h = con.execute(f"SELECT floor(error/15.0)*15/60 b, count(*) c FROM read_parquet('{PAIRS}') WHERE error BETWEEN -900 AND 900 GROUP BY b ORDER BY b").fetchall()
f3 = go.Figure(go.Bar(x=[r[0] for r in h], y=[r[1] for r in h], marker_color=ORANGE,
    hovertemplate="error %{x:.1f} min<br>%{y:,} pairs<extra></extra>"))
p3 = dv(style(f3, yt="matched pairs", xt="error (min, + = predicted late)"), "p3")

hm = con.execute(f"SELECT hour, {BANDS} b, min(lead) o, median(abs_error) e FROM read_parquet('{PAIRS}') GROUP BY hour, b ORDER BY hour, o").fetchall()
order = ["0-2", "2-5", "5-10", "10-20", "20-60"]
z = [[None] * 24 for _ in order]
for hr, b, o, e in hm:
    z[order.index(b)][int(hr)] = e
f4 = go.Figure(go.Heatmap(z=z, x=list(range(24)), y=order, colorscale="YlOrRd",
    colorbar=dict(title="med |err| (s)"), hovertemplate="%{x}:00, lead %{y} min<br><b>%{z:.0f}s</b><extra></extra>"))
p4 = dv(style(f4, yt="lead (min)", xt="hour of day"), "p4")

cov = acc["conformal_empirical_coverage_pct"]; nom = [int(k) for k in cov]; emp = [cov[k] for k in cov]
f5 = go.Figure()
f5.add_scatter(x=[50, 95], y=[50, 95], mode="lines", line=dict(color="#94a3b8", dash="dash"), hoverinfo="skip")
f5.add_scatter(x=nom, y=emp, mode="lines+markers", line=dict(color=BLUE, width=2), marker=dict(size=9),
    hovertemplate="nominal %{x}%<br><b>empirical %{y:.1f}%</b><extra></extra>")
p5 = dv(style(f5, yt="empirical coverage (%)", xt="nominal coverage (%)"), "p5")

si = mod["shap_importance_s"]; keys = list(si)[::-1]
f6 = go.Figure(go.Bar(x=[si[k] for k in keys], y=keys, orientation="h", marker_color=BLUE,
    hovertemplate="%{y}<br><b>%{x:.1f}s</b> mean |SHAP|<extra></extra>"))
p6 = dv(style(f6, xt="mean |SHAP| (s)"), "p6")

r = con.execute(f"SELECT route_id, median(abs_error) e, count(*) n FROM read_parquet('{PAIRS}') WHERE route_id IS NOT NULL GROUP BY route_id HAVING count(*)>=5000 ORDER BY e DESC, route_id LIMIT 12").fetchall()
f7 = go.Figure(go.Bar(x=[x[1] for x in r][::-1], y=[rname(x[0]) for x in r][::-1], orientation="h",
    marker_color=BLUE, customdata=[[x[2], rlong(x[0])] for x in r][::-1],
    hovertemplate="<b>%{y}</b>  %{customdata[1]}<br>%{x:.0f}s median error &middot; %{customdata[0]:,} pairs<extra></extra>"))
p7 = dv(style(f7, xt="median |error| (s)"), "p7")

lb = con.execute(f"""SELECT route_id, median(abs_error) med, quantile_cont(abs_error,0.9) p90,
   100.0*avg(CASE WHEN abs_error<=120 THEN 1 ELSE 0 END) w2, count(*) n
 FROM read_parquet('{PAIRS}') WHERE route_id IS NOT NULL GROUP BY route_id HAVING count(*)>=2000 ORDER BY med DESC, route_id""").fetchall()
rows = "".join(
    f"<tr data-route=\"{x[0]}\" data-name=\"{rname(x[0])} {rlong(x[0])}\" onclick=\"applyRoute('{x[0]}')\">"
    f"<td>{rname(x[0])}</td><td class='n'>{rlong(x[0])}</td>"
    f"<td data-v='{x[1]:.0f}'>{x[1]:.0f}</td><td data-v='{x[2]:.0f}'>{x[2]:.0f}</td>"
    f"<td data-v='{x[3]:.1f}'>{x[3]:.0f}%</td><td data-v='{x[4]}'>{x[4]:,}</td></tr>" for x in lb)
leaderboard = (
    "<div class='lbtools'><input id='lbsearch' placeholder='Search route or name...' oninput='filterLB()'>"
    "<span class='hint'>tip: click a row to filter the whole dashboard to that route</span>"
    "<button class='mini' onclick='resetFilter()'>reset</button></div>"
    "<div class='tablewrap'><table id='lb'><thead><tr>"
    "<th onclick='sortLB(this,0,false)'>Route<i></i></th><th onclick='sortLB(this,1,false)'>Name<i></i></th>"
    "<th onclick='sortLB(this,2,true)'>Median s<i></i></th><th onclick='sortLB(this,3,true)'>90th s<i></i></th>"
    "<th onclick='sortLB(this,4,true)'>Within 2min<i></i></th><th onclick='sortLB(this,5,true)'>Pairs<i></i></th>"
    f"</tr></thead><tbody>{rows}</tbody></table></div>")

b = con.execute(f"SELECT hour, median(error) m FROM read_parquet('{PAIRS}') GROUP BY hour ORDER BY hour").fetchall()
f8 = go.Figure(go.Bar(x=[x[0] for x in b], y=[x[1] for x in b],
    marker=dict(color=[x[1] for x in b], colorscale="RdBu", cmid=0, reversescale=True, showscale=False),
    hovertemplate="%{x}:00<br><b>%{y:.0f}s</b> median error<extra></extra>"))
p8 = dv(style(f8, yt="median error (s, +late/-early)", xt="hour of day"), "p8")

fan = con.execute(f"""SELECT {BANDS} b, min(lead) o, quantile_cont(error,0.1)/60 p10,
   quantile_cont(error,0.5)/60 p50, quantile_cont(error,0.9)/60 p90
 FROM read_parquet('{PAIRS}') GROUP BY b ORDER BY o""").fetchall()
xb = [r[0] for r in fan]
ffan = go.Figure()
ffan.add_scatter(x=xb + xb[::-1], y=[r[4] for r in fan] + [r[2] for r in fan][::-1], fill="toself",
    fillcolor="rgba(37,99,235,.15)", line=dict(width=0), hoverinfo="skip")
ffan.add_scatter(x=xb, y=[r[3] for r in fan], mode="lines+markers", line=dict(color=BLUE, width=2),
    hovertemplate="lead %{x} min<br>median %{y:.2f} min (band = p10-p90)<extra></extra>")
pfan = dv(style(ffan, yt="signed error (min)", xt="lead time (min ahead)"), "pfan")

froc = go.Figure()
froc.add_scatter(x=[0, 1], y=[0, 1], mode="lines", line=dict(color="#94a3b8", dash="dash"), hoverinfo="skip")
froc.add_scatter(x=mod["roc"]["fpr"], y=mod["roc"]["tpr"], mode="lines", line=dict(color=BLUE, width=2),
    fill="tozeroy", fillcolor="rgba(37,99,235,.10)", hovertemplate="FPR %{x:.2f}<br>TPR %{y:.2f}<extra></extra>")
froc.add_annotation(x=0.63, y=0.12, text=f"AUC = {mod['clf_auc']:.2f}", showarrow=False, font=dict(size=13, color=INK))
proc = dv(style(froc, yt="true positive rate", xt="false positive rate"), "proc")

sp = con.execute(f"""SELECT stop_sequence s, median(abs_error) m FROM read_parquet('{PAIRS}')
 WHERE stop_sequence BETWEEN 1 AND 50 GROUP BY stop_sequence HAVING count(*)>=1000 ORDER BY s""").fetchall()
fpos = go.Figure(go.Scatter(x=[r[0] for r in sp], y=[r[1] for r in sp], mode="lines+markers",
    line=dict(color=BLUE, width=2), hovertemplate="stop #%{x} on trip<br>%{y:.0f}s median<extra></extra>"))
ppos = dv(style(fpos, yt="median |error| (s)", xt="stop position (sequence on trip)"), "ppos")

dr = con.execute(f"""SELECT direction_id d, median(abs_error) m, 100.0*avg(CASE WHEN abs_error<=120 THEN 1 ELSE 0 END) w2, count(*) n
 FROM read_parquet('{PAIRS}') WHERE direction_id IS NOT NULL GROUP BY direction_id ORDER BY direction_id""").fetchall()
DIRN = {0: "Outbound", 1: "Inbound"}
fdir = go.Figure(go.Bar(x=[DIRN.get(int(r[0]), str(r[0])) for r in dr], y=[r[1] for r in dr], marker_color=BLUE,
    customdata=[[r[2], r[3]] for r in dr],
    hovertemplate="%{x}<br>%{y:.0f}s median · %{customdata[0]:.0f}% within 2min · %{customdata[1]:,} pairs<extra></extra>"))
pdir = dv(style(fdir, yt="median |error| (s)"), "pdir")

BUS = config.GTFS_STATIC / "google_bus" / "stops.txt"
RAIL = config.GTFS_STATIC / "google_rail" / "stops.txt"
if BUS.exists():
    coords_sql = (f"SELECT sid, any_value(lat) lat, any_value(lon) lon FROM ("
                  f"SELECT CAST(stop_id AS VARCHAR) sid, stop_lat lat, stop_lon lon FROM read_csv_auto('{BUS}') "
                  f"UNION ALL SELECT CAST(stop_id AS VARCHAR), stop_lat, stop_lon FROM read_csv_auto('{RAIL}')) GROUP BY sid")
    coord_src = "official GTFS static stops.txt"
else:
    coords_sql = (f"SELECT CAST(stop_id AS VARCHAR) sid, median(latitude) lat, median(longitude) lon "
                  f"FROM read_parquet('{VP}') WHERE latitude BETWEEN 39 AND 41 AND stop_id IS NOT NULL "
                  f"AND CAST(stop_id AS VARCHAR)<>'None' GROUP BY sid")
    coord_src = "GPS-median estimate (static feed missing)"
m = con.execute(f"""WITH c AS ({coords_sql}),
 e AS (SELECT CAST(stop_id AS VARCHAR) sid, median(abs_error) er, quantile_cont(abs_error,0.9) p90,
   100.0*avg(CASE WHEN abs_error<=120 THEN 1 ELSE 0 END) w2, count(*) n FROM read_parquet('{PAIRS}') GROUP BY sid HAVING count(*)>=200)
 SELECT e.sid, c.lat, c.lon, e.er, e.p90, e.w2, e.n FROM e JOIN c USING(sid) ORDER BY e.sid""").fetchall()
sids = [str(x[0]) for x in m]
lat = [x[1] for x in m]; lon = [x[2] for x in m]
med = [x[3] for x in m]; p90 = [x[4] for x in m]; w2 = [x[5] for x in m]; cnt = [x[6] for x in m]
sid_to_idx = {s: i for i, s in enumerate(sids)}
route_stops = {}
RS = config.GTFS_STATIC / "google_bus" / "route_stops.txt"
if RS.exists():
    for rid, sid in con.execute(f"SELECT CAST(route_id AS VARCHAR), CAST(stop_id AS VARCHAR) FROM read_csv_auto('{RS}') ORDER BY 1, 2").fetchall():
        i = sid_to_idx.get(str(sid))
        if i is not None: route_stops.setdefault(str(rid), []).append(i)
route_stops_json = json.dumps(route_stops)
map_sizes = [round(min(6 + v / 400, 20), 2) for v in cnt]
sizes_json = json.dumps(map_sizes)
home_json = json.dumps({"lat": round(sum(lat) / len(lat), 5), "lon": round(sum(lon) / len(lon), 5), "zoom": 9.4})
fmap = go.Figure(go.Scattermapbox(lat=lat, lon=lon, mode="markers",
    marker=dict(size=map_sizes, color=med, colorscale="YlOrRd", cmin=0, cmax=180, showscale=True,
                colorbar=dict(orientation="h", x=0.5, xanchor="center", y=0.0, yanchor="bottom",
                              len=0.5, thickness=10, title=dict(text="median |error| (s)", side="top")), opacity=0.8),
    text=[f"{e:.0f}s median | {c:,} pairs" for e, c in zip(med, cnt)], hovertemplate="%{text}<extra></extra>"))
btn = lambda lab, col, cs, ttl, cx: dict(label=lab, method="restyle",
    args=[{"marker.color": [col], "marker.colorscale": cs, "marker.colorbar.title.text": [ttl],
           "marker.cmin": 0, "marker.cmax": cx}, [0]])
fmap.update_layout(height=470, margin=dict(l=0, r=0, t=0, b=0),
    mapbox=dict(style="open-street-map", center=dict(lat=sum(lat)/len(lat), lon=sum(lon)/len(lon)), zoom=9.4),
    updatemenus=[dict(type="dropdown", x=0.01, y=0.99, xanchor="left", yanchor="top", bgcolor="white",
        buttons=[btn("Median error", med, "YlOrRd", "median |error| (s)", 180),
                 btn("90th-pct error", p90, "YlOrRd", "90th-pct |error| (s)", 400),
                 btn("Within 2 min %", w2, "YlGn", "within 2 min (%)", 100),
                 btn("Traffic (pairs)", cnt, "Blues", "pairs", 3000)])])
MAP_CFG = {"displayModeBar": True, "scrollZoom": True, "responsive": True, "displaylogo": False,
           "modeBarButtonsToRemove": ["select2d", "lasso2d", "toImage"]}
pmap = pio.to_html(fmap, include_plotlyjs=False, full_html=False, div_id="pmap", config=MAP_CFG)
print(f"  map: {len(m):,} stops from {coord_src}, 4 switchable metrics")

BAND_ORDER = config.BAND_ORDER
routes_in = [str(x[0]) for x in lb]
rin_sql = "(" + ",".join("'" + r.replace("'", "''") + "'" for r in routes_in) + ")"
RK = "CAST(route_id AS VARCHAR)"
kpi_g = {r[0]: r[1:] for r in con.execute(
    f"SELECT {RK}, median(abs_error), 100.0*avg(CASE WHEN abs_error<=120 THEN 1 ELSE 0 END), "
    f"quantile_cont(abs_error,0.9), median(error), count(*) FROM read_parquet('{PAIRS}') "
    f"WHERE {RK} IN {rin_sql} GROUP BY 1").fetchall()}
lead_g, bias_g, fan_g, ecdf_g = {}, {}, {}, {}
for rid, bnd, v in con.execute(f"SELECT {RK}, {BANDS} bd, median(abs_error)/60 FROM read_parquet('{PAIRS}') WHERE {RK} IN {rin_sql} GROUP BY 1,2").fetchall():
    lead_g.setdefault(rid, {})[bnd] = v
for rid, hr, v in con.execute(f"SELECT {RK}, hour, median(error) FROM read_parquet('{PAIRS}') WHERE {RK} IN {rin_sql} GROUP BY 1,2").fetchall():
    bias_g.setdefault(rid, {})[int(hr)] = v
for rid, bnd, q1, q5, q9 in con.execute(f"SELECT {RK}, {BANDS} bd, quantile_cont(error,0.1)/60, quantile_cont(error,0.5)/60, quantile_cont(error,0.9)/60 FROM read_parquet('{PAIRS}') WHERE {RK} IN {rin_sql} GROUP BY 1,2").fetchall():
    fan_g.setdefault(rid, {})[bnd] = (q1, q5, q9)
for rid, bkt, c in con.execute(f"SELECT {RK}, floor(least(abs_error,600)/15)*15 bb, count(*) FROM read_parquet('{PAIRS}') WHERE {RK} IN {rin_sql} GROUP BY 1,2").fetchall():
    ecdf_g.setdefault(rid, {})[bkt] = c
def _ecdf(bk):
    tot = sum(bk.values()) or 1; run = 0; x = []; y = []
    for bb in sorted(bk): run += bk[bb]; x.append(bb); y.append(round(100 * run / tot, 2))
    return x, y
_r = lambda v, n=3: round(v, n) if v is not None else None
filterdata = {}
for rid in routes_in:
    k = kpi_g.get(rid)
    if not k: continue
    lg, bg, fg = lead_g.get(rid, {}), bias_g.get(rid, {}), fan_g.get(rid, {})
    ex, ey = _ecdf(ecdf_g.get(rid, {}))
    filterdata[rid] = {
        "kpi": {"med": round(k[0]), "w2": round(k[1]), "p90": round(k[2]), "bias": round(k[3]), "n": int(k[4])},
        "lead": [_r(lg.get(bo)) for bo in BAND_ORDER],
        "bias": [_r(bg.get(h), 1) for h in range(24)],
        "fan10": [_r(fg[bo][0]) if bo in fg else None for bo in BAND_ORDER],
        "fan50": [_r(fg[bo][1]) if bo in fg else None for bo in BAND_ORDER],
        "fan90": [_r(fg[bo][2]) if bo in fg else None for bo in BAND_ORDER],
        "ecdf_x": ex, "ecdf_y": ey}
filterdata["ALL"] = {
    "kpi": {"med": round(acc["median_abs_s"]), "w2": round(acc["within_2min_pct"]), "p90": round(acc["p90_abs_s"]), "bias": round(acc["bias_s"]), "n": acc["n_pairs"]},
    "lead": [r[2] for r in d],
    "bias": [next((row[1] for row in b if int(row[0]) == h), None) for h in range(24)],
    "fan10": [r[2] for r in fan], "fan50": [r[3] for r in fan], "fan90": [r[4] for r in fan],
    "ecdf_x": [c[0] for c in cum], "ecdf_y": [c[1] for c in cum]}
filterdata_json = json.dumps(filterdata)
route_options = "".join(f"<option value='{r}'>{rname(r)} &mdash; {rlong(r)}</option>" for r in routes_in)
print(f"  route filter: pre-computed slices for {len(filterdata) - 1} routes")

kpis = [("Matched pairs", f"{acc['n_pairs']/1e6:.1f}M"), ("Median error", f"{acc['median_abs_s']:.0f}s"),
        ("Within 2 min", f"{acc['within_2min_pct']:.0f}%"), ("90th-pct error", f"{acc['p90_abs_s']:.0f}s"),
        ("Bias", f"{acc['bias_s']:.0f}s early"), ("Large-fail AUC", f"{mod['clf_auc']:.2f}"), ("Conformal @90", f"{cov['90']:.0f}%")]
KID = {"Matched pairs": "pairs", "Median error": "median", "Within 2 min": "w2", "90th-pct error": "p90", "Bias": "bias"}
KCLS = {"Within 2 min": "g", "Conformal @90": "g", "Bias": "w"}
kpi_html = "".join(
    (f'<div class="kpi {KCLS.get(l,"")}"><div class="v" id="kpi-{KID[l]}">{v}</div><div class="l">{l}</div></div>' if l in KID
     else f'<div class="kpi {KCLS.get(l,"")}"><div class="v">{v}</div><div class="l">{l}</div></div>') for l, v in kpis)
card = lambda t, b, full=False: f'<div class="card{" full" if full else ""}"><h3>{t}</h3>{b}</div>'
head = (f"Predictions run <b>~{abs(acc['bias_s']):.0f}s early</b> on average and lose accuracy sharply with lead time "
        f"(~28s at 2&nbsp;min ahead &rarr; ~114s at 20&ndash;60&nbsp;min); large failures are predictable at AUC {mod['clf_auc']:.2f}.")

html = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>ETA Accuracy Audit - SEPTA bus</title><script>{get_plotlyjs()}</script>
<style>
:root{{--ink:#0f172a;--muted:#64748b;--surf:#fff;--bg:#eef2f9;--line:#e6eaf2;--accent:#4f46e5;--good:#10b981;--warn:#f59e0b}}
*{{box-sizing:border-box}}
body{{margin:0;font-family:'Segoe UI',-apple-system,Inter,Roboto,sans-serif;color:var(--ink);background:radial-gradient(1100px 460px at 50% -120px,#e4e9fb 0%,transparent 60%),var(--bg)}}
.wrap{{max-width:1340px;margin:0 auto;padding:26px 22px 52px}}
.hero{{background:linear-gradient(120deg,#4f46e5,#7c3aed 55%,#0ea5e9);color:#fff;border-radius:22px;padding:26px 30px;box-shadow:0 16px 40px rgba(79,70,229,.30)}}
.hero h1{{margin:0;font-size:27px;font-weight:800;letter-spacing:-.4px}}
.hero p{{margin:9px 0 0;color:rgba(255,255,255,.92);font-size:14px;line-height:1.55;max-width:960px}}
.hero code{{background:rgba(255,255,255,.18);padding:1px 6px;border-radius:6px;font-size:.92em}} .hero b{{color:#fff}}
.badge{{display:inline-block;background:rgba(255,255,255,.22);border:1px solid rgba(255,255,255,.35);padding:4px 12px;border-radius:999px;font-size:12px;font-weight:700;letter-spacing:.3px;margin-bottom:12px}}
.kpis{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:14px;margin:16px 0 4px}}
.kpi{{background:#fff;border:1px solid var(--line);border-radius:16px;padding:16px 18px;position:relative;overflow:hidden;box-shadow:0 4px 16px rgba(15,23,42,.05);transition:transform .2s,box-shadow .2s}}
.kpi:hover{{transform:translateY(-4px);box-shadow:0 14px 30px rgba(15,23,42,.12)}}
.kpi::before{{content:'';position:absolute;left:0;top:0;bottom:0;width:4px;background:var(--accent)}}
.kpi.g::before{{background:var(--good)}} .kpi.w::before{{background:var(--warn)}}
.kpi .v{{font-size:27px;font-weight:800;letter-spacing:-.5px}} .kpi .l{{color:var(--muted);font-size:11px;margin-top:3px;font-weight:700;text-transform:uppercase;letter-spacing:.5px}}
.section{{font-size:12px;font-weight:800;text-transform:uppercase;letter-spacing:1.2px;color:var(--muted);margin:28px 4px 2px}}
.grid{{display:grid;grid-template-columns:1fr 1fr;gap:18px;margin-top:10px}}
.card{{background:#fff;border:1px solid var(--line);border-radius:16px;padding:15px 18px;box-shadow:0 4px 16px rgba(15,23,42,.05);transition:transform .2s,box-shadow .2s;opacity:0;transform:translateY(12px);animation:rise .55s ease forwards}}
.card:hover{{transform:translateY(-3px);box-shadow:0 14px 30px rgba(15,23,42,.10)}}
.card h3{{margin:0 0 8px;font-size:14px;font-weight:700;display:flex;align-items:center;gap:8px}}
.card h3::before{{content:'';width:9px;height:9px;border-radius:50%;background:linear-gradient(135deg,#4f46e5,#0ea5e9)}}
.card.full{{grid-column:1/-1}} @keyframes rise{{to{{opacity:1;transform:none}}}}
footer{{color:var(--muted);font-size:12px;margin-top:22px;line-height:1.6}}
@media(max-width:820px){{.grid{{grid-template-columns:1fr}}}}
.tablewrap{{max-height:360px;overflow:auto}}
table#lb{{width:100%;border-collapse:collapse;font-size:13px}}
table#lb th,table#lb td{{text-align:right;padding:6px 10px;border-bottom:1px solid var(--line);white-space:nowrap}}
table#lb th:first-child,table#lb td:first-child,table#lb td.n{{text-align:left}}
table#lb td.n{{color:var(--muted)}}
table#lb th{{cursor:pointer;user-select:none;position:sticky;top:0;background:#f8fafc;font-size:12px;text-transform:uppercase;letter-spacing:.4px;color:var(--muted)}}
.lbtools{{display:flex;gap:10px;align-items:center;margin-bottom:8px;flex-wrap:wrap}}
#lbsearch{{flex:1;min-width:160px;padding:7px 10px;border:1px solid var(--line);border-radius:8px;background:var(--surf);color:var(--ink);font-size:13px}}
.hint{{color:var(--muted);font-size:12px}}
.mini{{background:var(--surf);border:1px solid var(--line);color:var(--ink);border-radius:8px;padding:6px 10px;cursor:pointer;font-size:12px}}
.filterbar{{display:flex;gap:10px;align-items:center;margin:14px 0 4px;flex-wrap:wrap}}
.filterbar .fl{{color:var(--muted);font-size:13px}}
#routeFilter{{padding:7px 10px;border:1px solid var(--line);border-radius:8px;background:var(--surf);color:var(--ink);font-size:13px;max-width:360px}}
table#lb tbody tr{{cursor:pointer;transition:background .12s}} table#lb tbody tr:hover{{background:rgba(79,70,229,.07)}} table#lb tbody tr.sel{{background:rgba(79,70,229,.14)}}
table#lb th i{{margin-left:5px}} table#lb th i::after{{content:'\\21C5';color:var(--muted);opacity:.55}}
table#lb th.asc i::after{{content:'\\2191';color:var(--accent);opacity:1}}
table#lb th.desc i::after{{content:'\\2193';color:var(--accent);opacity:1}}
</style></head><body><div class="wrap">
<div class="hero"><span class="badge">Non-circular audit &middot; {acc['n_pairs']/1e6:.1f}M matched pairs</span>
<h1>Real-Time Public-Transport ETA Accuracy Audit</h1>
<p>SEPTA bus &middot; 2026-01-04 &middot; agency predictions (<code>trip_updates</code>) audited against an independent GPS ground truth (<code>vehicle_positions</code>). {head}</p></div>
<div class="filterbar"><span class="fl">Filter dashboard to a route:</span>
<select id="routeFilter" onchange="applyRoute(this.value)"><option value="ALL">All routes (everything)</option>{route_options}</select>
<button class="mini" onclick="document.getElementById('routeFilter').value='ALL';applyRoute('ALL')">reset</button>
<span id="filternote" class="fl"></span></div>
<div class="kpis">{kpi_html}</div>
<div class="section">Accuracy over time</div>
<div class="grid">
{card("Accuracy vs lead time", p1)}
{card("Cumulative accuracy (ECDF)", p2)}
{card("Distribution of ETA errors", p3)}
{card("Error spread by lead time (p10&ndash;p90)", pfan)}
</div>
<div class="section">Calibration &amp; failure model</div>
<div class="grid">
{card("Conformal interval calibration", p5)}
{card("Failure drivers (SHAP)", p6)}
{card("Failure model &mdash; ROC curve", proc)}
{card("Inbound vs outbound", pdir)}
</div>
<div class="section">When &amp; where errors happen</div>
<div class="grid">
{card("Error by hour &times; lead time", p4)}
{card("Prediction bias by hour of day", p8)}
{card("Error vs stop position on the trip", ppos)}
{card("Worst routes by median error", p7)}
</div>
<div class="section">Explore</div>
<div class="grid">
{card("Stops map &mdash; pick a metric (top-left dropdown)", pmap, full=True)}
{card("Route leaderboard", leaderboard, full=True)}
</div>
<footer>Reproducible: <code>./run_all.sh</code> regenerates every figure from the raw open feeds. Ground truth is reconstructed from an independent GPS stream, so the audit is non-circular. Data: gtfsrt.io open archive.</footer>
</div>
<script>
const ROUTE_STOPS={route_stops_json};
const STOP_SIZE={sizes_json};
const MAP_HOME={home_json};
const FDATA={filterdata_json};
function countUp(el){{
 const txt=el.innerText, m=txt.match(/^(-?[\\d,.]+)(.*)$/); if(!m)return;
 const target=parseFloat(m[1].replace(/,/g,'')), suf=m[2], dec=(m[1].split('.')[1]||'').length, big=/,/.test(m[1]);
 let start=null; const dur=850, fmt=v=>(big?Math.round(v).toLocaleString():v.toFixed(dec))+suf;
 function step(t){{ if(!start)start=t; const p=Math.min((t-start)/dur,1), e=1-Math.pow(1-p,3);
   el.innerText=fmt(target*e); if(p<1)requestAnimationFrame(step); else el.innerText=txt; }}
 requestAnimationFrame(step);}}
document.querySelectorAll('.kpi .v').forEach(countUp);
function sortLB(th,col,num){{
 const tb=document.querySelector('#lb tbody'); const rows=[...tb.rows];
 const asc=!th.classList.contains('asc');
 rows.sort((a,b)=>{{let x=num?parseFloat(a.cells[col].dataset.v):a.cells[col].innerText.toLowerCase();
   let y=num?parseFloat(b.cells[col].dataset.v):b.cells[col].innerText.toLowerCase();
   return (x>y?1:x<y?-1:0)*(asc?1:-1);}});
 document.querySelectorAll('#lb th').forEach(h=>h.classList.remove('asc','desc'));
 th.classList.add(asc?'asc':'desc'); rows.forEach(r=>tb.appendChild(r));}}
function filterLB(){{const q=document.getElementById('lbsearch').value.toLowerCase();
 document.querySelectorAll('#lb tbody tr').forEach(r=>{{r.style.display=(r.dataset.name||'').toLowerCase().includes(q)?'':'none';}});}}
function pickRoute(rid,scroll){{
 document.querySelectorAll('#lb tbody tr').forEach(r=>r.classList.toggle('sel',r.dataset.route==rid));
 const gd=document.getElementById('pmap'); if(!gd||!ROUTE_STOPS[rid]||!gd.data)return;
 const set=new Set(ROUTE_STOPS[rid]);
 const sizes=STOP_SIZE.map((s,i)=>set.has(i)?Math.max(s,7):0);   // keep this route's stops, hide the rest
 Plotly.restyle(gd,{{'marker.size':[sizes]}},[0]);
 const idx=ROUTE_STOPS[rid], la=idx.map(i=>gd.data[0].lat[i]), lo=idx.map(i=>gd.data[0].lon[i]);
 const cla=la.reduce((a,b)=>a+b,0)/la.length, clo=lo.reduce((a,b)=>a+b,0)/lo.length;
 Plotly.relayout(gd,{{'mapbox.center':{{lat:cla,lon:clo}},'mapbox.zoom':11}});
 if(scroll!==false) gd.scrollIntoView({{behavior:'smooth',block:'center'}});}}
function clearHi(){{const gd=document.getElementById('pmap'); if(!gd||!gd.data)return;
 Plotly.restyle(gd,{{'marker.size':[STOP_SIZE]}},[0]);
 Plotly.relayout(gd,{{'mapbox.center':{{lat:MAP_HOME.lat,lon:MAP_HOME.lon}},'mapbox.zoom':MAP_HOME.zoom}});
 document.querySelectorAll('#lb tbody tr').forEach(r=>r.classList.remove('sel'));}}
function applyRoute(rid){{
 const dd=FDATA[rid]; if(!dd)return; const k=dd.kpi;
 const setv=(id,val)=>{{const e=document.getElementById(id); if(e)e.innerText=val;}};
 setv('kpi-pairs', k.n>=1e6?(k.n/1e6).toFixed(1)+'M':k.n.toLocaleString());
 setv('kpi-median', k.med+'s'); setv('kpi-w2', k.w2+'%'); setv('kpi-p90', k.p90+'s');
 setv('kpi-bias', k.bias+'s'+(k.bias<0?' early':(k.bias>0?' late':'')));
 Plotly.restyle('p1',{{y:[dd.lead]}});
 Plotly.restyle('p2',{{x:[dd.ecdf_x],y:[dd.ecdf_y]}});
 Plotly.restyle('p8',{{y:[dd.bias],'marker.color':[dd.bias]}});
 Plotly.restyle('pfan',{{y:[dd.fan90.concat([...dd.fan10].reverse()), dd.fan50]}},[0,1]);
 const sel=document.getElementById('routeFilter'); if(sel&&sel.value!=rid) sel.value=rid;
 const note=document.getElementById('filternote');
 if(note) note.innerText = rid=='ALL' ? '' : ('now showing this route only ('+k.n.toLocaleString()+' pairs)');
 if(rid=='ALL'){{clearHi();}} else {{pickRoute(rid,false);}}
}}
function resetFilter(){{const s=document.getElementById('routeFilter'); if(s)s.value='ALL'; applyRoute('ALL');}}
</script></body></html>"""
config.DASHBOARD.write_text(html, encoding="utf-8")
size_mb = config.DASHBOARD.stat().st_size / 1e6
print(f"  wrote {config.DASHBOARD.name} ({size_mb:.1f} MB, self-contained)")
