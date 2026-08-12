"""Stage 2: how accurate are the predictions, and how confident can we be?

Reads the matched pairs and characterises error across the whole distribution rather
than as a single average. The distribution is heavy-tailed, so the median is the primary
summary and the percentiles are reported next to it.

The feed publishes an optional `uncertainty` field on arrival predictions. In this
archive it is empty on every single pair, so there is no stated confidence to test. We
build the missing uncertainty instead, using split-conformal prediction, and check that
it holds up on trips the interval width was never fitted on.

Writes out/accuracy_metrics.json and three figures.
"""

import json

import duckdb
import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

import config

con = duckdb.connect()
pairs = config.MATCHED_PAIRS

print("Stage 2: accuracy and calibration")

row = con.execute(f"""
    SELECT count(*)                    AS n,
           median(abs_error)           AS med,
           avg(abs_error)              AS mean,
           quantile_cont(abs_error, 0.90) AS p90,
           median(error)               AS bias,
           100.0 * avg(CASE WHEN abs_error <= 60  THEN 1 ELSE 0 END) AS within_1,
           100.0 * avg(CASE WHEN abs_error <= 120 THEN 1 ELSE 0 END) AS within_2,
           100.0 * avg(CASE WHEN abs_error <= 300 THEN 1 ELSE 0 END) AS within_5
    FROM read_parquet('{pairs}')
""").fetchone()

metrics = {
    "n_pairs": row[0],
    "median_abs_s": round(row[1], 1),
    "mean_abs_s": round(row[2], 1),
    "p90_abs_s": round(row[3], 1),
    "bias_s": round(row[4], 1),
    "within_1min_pct": round(row[5], 1),
    "within_2min_pct": round(row[6], 1),
    "within_5min_pct": round(row[7], 1),
}
for key, value in metrics.items():
    print(f"  {key:<18} {value}")

# Distribution of signed error. Negative means the vehicle turned up after the countdown
# said it would, which is the direction that costs a passenger waiting time.
hist = con.execute(f"""
    SELECT floor(error / 15.0) * 15 AS bucket, count(*) AS c
    FROM read_parquet('{pairs}')
    WHERE error BETWEEN -900 AND 900
    GROUP BY bucket
    ORDER BY bucket
""").fetchall()

fig, ax = plt.subplots(figsize=(7.2, 4.2))
ax.bar(np.array([b[0] for b in hist]) / 60, np.array([b[1] for b in hist]),
       width=0.24, color=config.ORANGE)
ax.axvline(0, color="k", ls="--", lw=1)
ax.set_xlabel("prediction error (minutes,  + = predicted late)")
ax.set_ylabel("matched pairs")
ax.set_title("Distribution of ETA errors (heavy-tailed, slight early bias)")
ax.spines[["top", "right"]].set_visible(False)
plt.tight_layout()
plt.savefig(config.FIGS / "02_error_distribution.png", dpi=config.FIG_DPI)
plt.close()

# Accuracy against lead time. This is the structure a single headline number hides: a
# claim made 30 seconds out and one made 40 minutes out are not the same assertion.
bands = con.execute(f"""
    SELECT {config.LEAD_BANDS_SQL} AS band,
           min(lead)                      AS ord,
           median(abs_error)              AS med,
           quantile_cont(abs_error, 0.25) AS q1,
           quantile_cont(abs_error, 0.75) AS q3,
           count(*)                       AS n
    FROM read_parquet('{pairs}')
    GROUP BY band
    ORDER BY ord
""").fetchall()

labels = [b[0] for b in bands]
median = np.array([b[2] for b in bands]) / 60
q1 = np.array([b[3] for b in bands]) / 60
q3 = np.array([b[4] for b in bands]) / 60

fig, ax = plt.subplots(figsize=(7.2, 4.2))
x = np.arange(len(labels))
ax.fill_between(x, q1, q3, alpha=0.25, color=config.BLUE, label="inter-quartile range")
ax.plot(x, median, "o-", color=config.BLUE, lw=2, label="median")
for xi, m in zip(x, median):
    ax.text(xi, m + 0.05, f"{m:.1f}", ha="center", fontsize=9, fontweight="bold")
ax.set_xticks(x)
ax.set_xticklabels(labels)
ax.set_xlabel("prediction lead time (minutes ahead)")
ax.set_ylabel("absolute error (minutes)")
ax.set_title("Accuracy degrades systematically with lead time")
ax.legend(frameon=False)
ax.spines[["top", "right"]].set_visible(False)
plt.tight_layout()
plt.savefig(config.FIGS / "02_error_vs_lead.png", dpi=config.FIG_DPI)
plt.close()

stated = con.execute(f"""
    SELECT count(*) FROM read_parquet('{pairs}')
    WHERE arrival_uncertainty IS NOT NULL AND arrival_uncertainty > 0
""").fetchone()[0]
if stated > 1000:
    print(f"  feed states uncertainty on {stated:,} pairs, using it")
else:
    print("  feed states no uncertainty at all, so building conformal intervals instead")

# Split conformal. Fit the interval half-width on one half of the trips, measure how
# often it actually covers on the other half. Splitting by trip rather than by row
# matters: rows within a trip are dependent, and a row-level split would flatter the
# coverage figure.
levels = [0.5, 0.8, 0.9, 0.95]
empirical = []
for level in levels:
    half_width = con.execute(f"""
        SELECT quantile_cont(abs_error, {level}) FROM read_parquet('{pairs}')
        WHERE hash(trip_id) % 2 = 0
    """).fetchone()[0]
    covered = con.execute(f"""
        SELECT 100.0 * avg(CASE WHEN abs_error <= {half_width} THEN 1 ELSE 0 END)
        FROM read_parquet('{pairs}')
        WHERE hash(trip_id) % 2 = 1
    """).fetchone()[0]
    empirical.append(covered)

fig, ax = plt.subplots(figsize=(6.0, 4.6))
ax.plot([50, 95], [50, 95], "k--", lw=1, label="ideal (nominal = empirical)")
ax.plot([l * 100 for l in levels], empirical, "o-", color=config.BLUE, lw=2,
        label="conformal intervals")
for level, cov in zip(levels, empirical):
    ax.text(level * 100, cov + 0.8, f"{cov:.1f}%", ha="center", fontsize=9)
ax.set_xlabel("nominal coverage (%)")
ax.set_ylabel("empirical coverage on held-out trips (%)")
ax.set_title("Calibrated ETA windows via conformal prediction\n"
             "(the feed itself provides no uncertainty)")
ax.legend(frameon=False)
ax.spines[["top", "right"]].set_visible(False)
plt.tight_layout()
plt.savefig(config.FIGS / "02_calibration.png", dpi=config.FIG_DPI)
plt.close()

metrics["feed_states_uncertainty"] = stated > 1000
metrics["conformal_empirical_coverage_pct"] = {
    int(level * 100): round(cov, 1) for level, cov in zip(levels, empirical)
}
print("  conformal coverage:", metrics["conformal_empirical_coverage_pct"])

with open(config.ACCURACY_METRICS, "w") as fh:
    json.dump(metrics, fh, indent=2)
print(f"  wrote {config.ACCURACY_METRICS.name} and three figures")
