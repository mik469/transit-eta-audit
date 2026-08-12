"""Stage 6: print-quality figures for the written report.

Two of the views that are interactive in dashboard.html don't survive being put in a Word
document, so they get static equivalents here:

  figs/06_pipeline_funnel.png  attrition from raw feed rows to matched pairs
  figs/06_geo_map.png          stop-level geography of error, at official GTFS coordinates
  figs/07_dashboard_map.png    the dashboard's own map panel, exported via kaleido

The last one is exported rather than screenshotted because Plotly draws map markers with
WebGL and headless Chrome won't rasterise them, so a browser capture of that panel comes
out as an empty basemap. Took a while to work that out.
"""

import duckdb
import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

import config

con = duckdb.connect()

print("Stage 6: report figures")

# Funnel: what the pipeline discards, and where.
raw = con.execute(f"SELECT count(*) FROM read_parquet({config.TRIP_UPDATES})").fetchone()[0]
keyed = con.execute(f"""
    SELECT count(*) FROM read_parquet({config.TRIP_UPDATES})
    WHERE arrival_time IS NOT NULL AND trip_id IS NOT NULL AND stop_id IS NOT NULL
""").fetchone()[0]
in_window = con.execute(f"""
    SELECT count(*) FROM read_parquet({config.TRIP_UPDATES})
    WHERE arrival_time IS NOT NULL AND trip_id IS NOT NULL AND stop_id IS NOT NULL
      AND CAST(arrival_time AS BIGINT) - CAST(feed_timestamp AS BIGINT)
          BETWEEN 1 AND {config.MAX_LEAD_S}
""").fetchone()[0]
matched = con.execute(f"SELECT count(*) FROM read_parquet('{config.MATCHED_PAIRS}')").fetchone()[0]

stages = ["Raw trip_updates rows", "Keyed (trip, stop, arrival)", "Lead time 0-60 min",
          "Matched to GPS truth"]
counts = [raw, keyed, in_window, matched]

fig, ax = plt.subplots(figsize=(7.6, 4.0))
bars = ax.barh(range(4), counts, height=0.62,
               color=["#94a3b8", "#64748b", config.BLUE, config.TEAL])
for i, (bar, value) in enumerate(zip(bars, counts)):
    ax.text(value + raw * 0.012, i, f"{value / 1e6:.2f}M  ({100 * value / raw:.1f}%)",
            va="center", fontsize=9.5, fontweight="bold")
ax.set_yticks(range(4))
ax.set_yticklabels(stages, fontsize=9.5)
ax.invert_yaxis()
ax.set_xlim(0, raw * 1.28)
ax.set_title("Attrition from raw prediction feed to non-circular matched pairs")
ax.spines[["top", "right"]].set_visible(False)
ax.get_xaxis().set_visible(False)
plt.tight_layout()
plt.savefig(config.FIGS / "06_pipeline_funnel.png", dpi=config.FIG_DPI)
plt.close()
print(f"  funnel: {raw:,} -> {keyed:,} -> {in_window:,} -> {matched:,} "
      f"({100 * matched / in_window:.1f}% of in-window)")

bus_stops = config.GTFS_STATIC / "google_bus" / "stops.txt"
rail_stops = config.GTFS_STATIC / "google_rail" / "stops.txt"
if not bus_stops.exists():
    print("  skipping the maps: GTFS static is missing, run run_all.sh to fetch it")
    raise SystemExit

# Stop coordinates come from the published stops.txt, not from the GPS feed. An earlier
# version took the median of vehicle positions per stop, which put a handful of reused
# stop ids about twelve kilometres from where they actually are.
coords = f"""
    SELECT sid, any_value(lat) AS lat, any_value(lon) AS lon
    FROM (
        SELECT CAST(stop_id AS VARCHAR) AS sid, stop_lat AS lat, stop_lon AS lon
        FROM read_csv_auto('{bus_stops}')
        UNION ALL
        SELECT CAST(stop_id AS VARCHAR), stop_lat, stop_lon
        FROM read_csv_auto('{rail_stops}')
    )
    GROUP BY sid
"""
rows = con.execute(f"""
    WITH c AS ({coords}),
         e AS (
             SELECT CAST(stop_id AS VARCHAR) AS sid, median(abs_error) AS er, count(*) AS n
             FROM read_parquet('{config.MATCHED_PAIRS}')
             GROUP BY sid
             HAVING count(*) >= 200
         )
    SELECT c.lat, c.lon, e.er, e.n FROM e JOIN c USING (sid)
""").fetchall()

lat = np.array([r[0] for r in rows])
lon = np.array([r[1] for r in rows])
error = np.array([r[2] for r in rows])
traffic = np.array([r[3] for r in rows])

fig, ax = plt.subplots(figsize=(6.8, 6.4))
worst_last = np.argsort(error)          # draw the bad stops on top so they stay visible
scatter = ax.scatter(lon[worst_last], lat[worst_last],
                     c=np.clip(error[worst_last], 0, 180),
                     s=np.clip(3 + traffic[worst_last] / 900, 3, 26),
                     cmap="YlOrRd", alpha=0.85, linewidths=0)
bar = plt.colorbar(scatter, ax=ax, fraction=0.038, pad=0.02)
bar.set_label("median |error| (s, capped at 180)")
ax.set_xlabel("longitude")
ax.set_ylabel("latitude")
ax.set_title(f"Where predictions fail: {len(rows):,} SEPTA stops\n"
             "(official GTFS coordinates; dot size = traffic)")
ax.set_aspect(1 / np.cos(np.radians(float(lat.mean()))))
ax.spines[["top", "right"]].set_visible(False)
plt.tight_layout()
plt.savefig(config.FIGS / "06_geo_map.png", dpi=config.FIG_DPI)
plt.close()
print(f"  map: {len(rows):,} stops, median of stop medians {np.median(error):.0f}s, "
      f"worst {error.max():.0f}s")

# The same data as the dashboard's map panel, exported at print resolution.
try:
    import plotly.graph_objects as go

    fig = go.Figure(go.Scattermapbox(
        lat=list(lat), lon=list(lon), mode="markers",
        marker=dict(size=[round(min(6 + v / 400, 20), 2) for v in traffic],
                    color=list(error), colorscale="YlOrRd", cmin=0, cmax=180,
                    showscale=True, opacity=0.85,
                    colorbar=dict(orientation="h", x=0.5, xanchor="center", y=0.0,
                                  yanchor="bottom", len=0.5, thickness=10,
                                  title=dict(text="median |error| (s)", side="top")))))
    fig.update_layout(height=470, margin=dict(l=0, r=0, t=0, b=0),
                      mapbox=dict(style="open-street-map", zoom=9.4,
                                  center=dict(lat=float(lat.mean()), lon=float(lon.mean()))))
    fig.write_image(str(config.FIGS / "07_dashboard_map.png"), width=1400, height=470, scale=2)
    print(f"  dashboard map panel exported ({len(rows):,} markers)")
except Exception as exc:
    print(f"  dashboard map panel skipped, kaleido unavailable: {str(exc)[:70]}")
