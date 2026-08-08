"""Stage 1: build the non-circular matched dataset.

Predictions come from the GTFS-Realtime trip_updates feed. Ground truth is reconstructed
independently from the vehicle_positions GPS feed, so the prediction and the outcome
never share a source. That separation is the whole point of the study: comparing an
agency's prediction against its own later reported arrival just compares two outputs of
one estimator.

Writes out/matched_pairs.parquet, which every later stage reads.

Only bus is auditable from this archive slice. Rail trip_updates carry a delay value but
no absolute arrival time and no stop_id, so predicted arrivals would have to be rebuilt
from the static schedule. The realtime rail trip_ids also reference a schedule version
that isn't in the current static feed (zero overlap), so that reconstruction isn't
possible here. The matching rules below are written per mode, so rail slots back in if a
future archive carries the fields.
"""

import duckdb
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

import config

MODES = [("bus", config.BUS_POSITIONS, "matched_pairs.parquet")]

con = duckdb.connect()

print("Stage 1: pipeline and ground-truth reconstruction")

# One row per published arrival estimate. Lead time is derived here rather than later so
# it can't drift away from the timestamps it came from.
con.execute(f"""
    CREATE TABLE pred AS
    SELECT CAST(trip_id AS VARCHAR)   AS trip_id,
           CAST(route_id AS VARCHAR)  AS route_id,
           direction_id,
           CAST(stop_id AS VARCHAR)   AS stop_id,
           stop_sequence,
           CAST(feed_timestamp AS BIGINT) AS made_at,
           CAST(arrival_time AS BIGINT)   AS pred_arrival,
           arrival_uncertainty,
           arrival_delay,
           CAST(arrival_time AS BIGINT) - CAST(feed_timestamp AS BIGINT) AS lead
    FROM read_parquet({config.TRIP_UPDATES})
    WHERE arrival_time IS NOT NULL
      AND trip_id IS NOT NULL
      AND stop_id IS NOT NULL
""")
con.execute(f"DELETE FROM pred WHERE NOT (lead > 0 AND lead <= {config.MAX_LEAD_S})")

n_pred = con.execute("SELECT count(*) FROM pred").fetchone()[0]
print(f"  predictions made 0-60 min ahead: {n_pred:,}")

volumes = {}

for mode, positions, filename in MODES:
    if mode == "bus":
        # Bus positions carry stop_id, so the earliest report at a stop is the arrival.
        con.execute(f"""
            CREATE OR REPLACE TABLE truth AS
            SELECT CAST(trip_id AS VARCHAR) AS trip_id,
                   CAST(stop_id AS VARCHAR) AS stop_id,
                   0 AS seq,
                   MIN(CAST(timestamp AS BIGINT)) AS actual_arrival
            FROM read_parquet('{positions}')
            WHERE trip_id IS NOT NULL
              AND stop_id IS NOT NULL
              AND CAST(stop_id AS VARCHAR) <> 'None'
            GROUP BY 1, 2
        """)
        join_on = "p.trip_id = t.trip_id AND p.stop_id = t.stop_id"
    else:
        # Rail predictions have no stop_id, so match on sequence and take the stop from
        # the GPS feed instead.
        con.execute(f"""
            CREATE OR REPLACE TABLE truth AS
            SELECT CAST(trip_id AS VARCHAR) AS trip_id,
                   any_value(CAST(stop_id AS VARCHAR)) AS stop_id,
                   current_stop_sequence AS seq,
                   MIN(CAST(timestamp AS BIGINT)) AS actual_arrival
            FROM read_parquet('{positions}')
            WHERE trip_id IS NOT NULL
              AND current_stop_sequence IS NOT NULL
            GROUP BY trip_id, current_stop_sequence
        """)
        join_on = "p.trip_id = t.trip_id AND p.stop_sequence = t.seq"

    con.execute(f"""
        COPY (
            SELECT p.trip_id,
                   p.route_id,
                   p.direction_id,
                   t.stop_id,
                   p.stop_sequence,
                   p.made_at,
                   p.pred_arrival,
                   t.actual_arrival,
                   p.pred_arrival - t.actual_arrival      AS error,
                   abs(p.pred_arrival - t.actual_arrival) AS abs_error,
                   p.lead,
                   p.arrival_uncertainty,
                   p.arrival_delay,
                   hour(to_timestamp(p.made_at) - INTERVAL {config.TZ_OFFSET_HOURS} HOUR)      AS hour,
                   dayofweek(to_timestamp(p.made_at) - INTERVAL {config.TZ_OFFSET_HOURS} HOUR) AS dow,
                   '{mode}' AS mode
            FROM pred p
            JOIN truth t ON {join_on}
            WHERE abs(p.pred_arrival - t.actual_arrival) <= {config.MAX_PLAUSIBLE_ERROR_S}
        ) TO '{config.OUT / filename}' (FORMAT parquet)
    """)

    n, median_err, trips = con.execute(f"""
        SELECT count(*), median(abs_error), count(DISTINCT trip_id)
        FROM read_parquet('{config.OUT / filename}')
    """).fetchone()
    volumes[mode] = n or 0
    print(f"  {mode}: {n or 0:,} matched pairs, median |error| {median_err or 0:.0f}s, "
          f"{trips or 0:,} trips -> {filename}")

fig, ax = plt.subplots(figsize=(6, 4))
bars = ax.bar(list(volumes), list(volumes.values()), color=[config.BLUE, config.TEAL],
              edgecolor="white")
for bar, value in zip(bars, volumes.values()):
    label = f"{value / 1e6:.2f}M" if value >= 1e6 else f"{value / 1e3:.0f}k"
    ax.text(bar.get_x() + bar.get_width() / 2, value, label, ha="center", va="bottom",
            fontweight="bold")
ax.set_ylabel("matched pairs")
ax.set_title("Non-circular matched dataset, by mode")
ax.spines[["top", "right"]].set_visible(False)
plt.tight_layout()
plt.savefig(config.FIGS / "01_pipeline_volumes.png", dpi=140)
plt.close()

print("  done (bus only; see the module docstring for why rail is not auditable here)")
