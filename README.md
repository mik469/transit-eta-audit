# Real-Time Transit ETA Accuracy Audit

An open, reproducible audit of how accurate a transit agency's own real-time arrival
predictions actually are, measured against an **independent** ground truth rather than
against the agency's own later output.

Proof-of-concept dataset: **SEPTA bus, 4 January 2026, 11,779,888 matched
prediction-vs-actual pairs.**

MSc group project, School of Computing, Engineering and Physical Sciences, University of
the West of Scotland.

---

## Why bother

Your phone says the bus arrives in four minutes. Almost nobody checks whether that is
true, because the obvious test is circular: comparing an agency's predicted arrival with
the same agency's later reported arrival just compares two outputs of one estimator, so
any systematic error cancels out and stays invisible.

## The trick that makes it work

GTFS-Realtime is not one feed. It is several, produced by different parts of the
pipeline:

| Feed | What it is | Role here |
| --- | --- | --- |
| `trip_updates` | the agency's predicted arrival time per stop | the thing being audited |
| `vehicle_positions` | an independent stream of GPS fixes | reduced to the real arrival at each stop |

Take the prediction from one feed and reconstruct the truth from the other, and the
comparison is genuinely non-circular. That single design choice is the backbone of the
whole project.

It is not perfect independence, and we say so in the report: both feeds ultimately come
from one agency's telemetry, so a systematic fault in vehicle location would propagate
into both.

## Headline findings

- Median absolute error **64 s**; 70.9% of predictions land within two minutes.
- Predictions run **~30 s early** at the median, so the bus arrives *later* than promised.
- Accuracy collapses with how far ahead the claim was made: **28 s** at 0 to 2 minutes
  out, **114 s** at 20 to 60 minutes.
- The feed publishes **no uncertainty at all**. The optional `uncertainty` field is empty
  on all 11.78M pairs, so we build calibrated windows with conformal prediction instead.
  Empirical coverage 49.7 / 79.4 / 89.8 / 94.9% against nominal 50 / 80 / 90 / 95%.
- Individual errors are mostly **not** explicable from prior conditions (R² 0.11 under
  strict leakage control), but large failures are anticipable (**AUC 0.71**). Lead time
  dominates the SHAP ranking.

Route-level variation is much larger than anything else: 32 s median error on the best
route, 169 s on the worst.

## Running it

```bash
git clone <this repo>
cd transit-eta-audit
python3 -m pip install -r requirements.txt
# fetch the raw feeds first (see data/README.md)
./run_all.sh
open dashboard.html
```

`run_all.sh` fetches SEPTA's static schedule if it isn't already there, then runs the
seven stages in order. Everything downstream regenerates from the raw feeds: the matched
dataset, every metric file, every figure and the dashboard. Nothing is hand-edited.

Tested on Python 3.11 on macOS. About 30 seconds end to end and roughly 6 GB of peak
memory, most of it in stage 1 joining 17 million prediction rows against the position feed.

## Layout

```
src/
  config.py              shared paths, lead-time bands, thresholds
  01_pipeline.py         ingest feeds, reconstruct arrivals, match -> matched_pairs.parquet
  02_accuracy.py         distributional accuracy + conformal calibration
  03_modelling.py        gradient boosting + SHAP, leakage-controlled
  04_benchmark.py        one versioned benchmark record
  05_dashboard.py        builds dashboard.html
  06_report_figures.py   print-quality figures for the written report
  07_framework_figures.py  conceptual diagrams for the methodology chapters
tests/                   sanity checks on the matched dataset and the metrics
data/                    raw feeds go here (not in version control, see data/README.md)
out/                     matched dataset and metric JSON (generated)
figs/                    figures (generated)
```

## A note on the numbers

Every figure and metric in the written report comes from a single execution of
`run_all.sh`, and a second execution reproduces them byte for byte. Getting there took two
goes. The first version sampled training rows with reservoir sampling and left the models
unseeded, so consecutive runs disagreed. Fixing that left a subtler fault: a hash filter
pins *which* rows are sampled but not the order they come back in, and the boosting
subsample draws by position, so simply regenerating the matched dataset could shift R² in
the third decimal with nothing else changed. Sorting the training query on the row key
pins it. `docs/reproducing.md` has the detail and the command to verify it yourself.

## Known limitations

- **One agency, one mode, one day.** The design extends to more; it hasn't been run on
  more. The benchmark has exactly one row, so its cross-agency normalisation is untested.
- **Bus only.** Rail `trip_updates` carry a delay value but no absolute arrival time and
  no `stop_id`, and the realtime rail trip ids reference a schedule version that isn't in
  the current static feed (zero overlap), so rail ground truth can't be reconstructed
  here. The matching rules are written per mode so rail slots back in if a future archive
  carries the fields.
- **The archive slice covers 16 of 24 clock hours**, with a gap across the mid-afternoon.
  The afternoon peak is under-represented and the hour-of-day findings are partial. The
  blank columns in the dashboard's hour-by-lead heatmap are exactly this.
- **Ground truth is a reconstruction.** The position feed reports at intervals, so the
  first report at a stop is an upper bound on the true arrival, biasing reconstructed
  arrivals slightly late. That means the measured early-running bias is an upper bound.
  `current_status` isn't populated in this feed, so "stopped at" can't be isolated.
- **No container image.** Dependencies are pinned to exact versions, but a different
  Python build or BLAS could still move a floating-point digit. Publishing an image is the
  most valuable outstanding improvement.
- **The dashboard has never been put in front of a real analyst.** Its design follows
  established principles but that is a rationale, not evidence.

## Data

The raw feeds are about 180 MB and are not in the repository. `data/README.md` explains
where they come from and how to fetch them. The GTFS-Realtime archive data is SEPTA's,
redistributed by [gtfsrt.io](https://gtfsrt.io) under its own terms; the static schedule
comes from SEPTA's developer portal.
