"""Paths and constants shared by every stage of the audit.

Everything resolves from the repository root rather than the working directory, so the
stages behave the same whether you run them from the repo root, from src/, or through
run_all.sh.

The raw feed files are too large for version control (about 180 MB), so they are not in
the repository. See data/README.md for how to fetch them. FEED_DIR looks in data/ first
and falls back to the parent directory, which is where they sat during development.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "out"
FIGS = ROOT / "figs"
GTFS_STATIC = ROOT / "gtfs_static"

OUT.mkdir(exist_ok=True)
FIGS.mkdir(exist_ok=True)


def _feed_dir():
    if (ROOT / "data" / "septa_tu_1.parquet").exists():
        return ROOT / "data"
    return ROOT.parent


FEED_DIR = _feed_dir()

# Raw GTFS-Realtime archive files (gtfsrt.io, SEPTA, 2026-01-04).
TRIP_UPDATES = [str(FEED_DIR / "septa_tu_1.parquet"), str(FEED_DIR / "septa_tu_2.parquet")]
BUS_POSITIONS = str(FEED_DIR / "septa_bus_vp.parquet")
RAIL_POSITIONS = str(FEED_DIR / "septa_vp.parquet")

# Stage outputs.
MATCHED_PAIRS = str(OUT / "matched_pairs.parquet")
ACCURACY_METRICS = OUT / "accuracy_metrics.json"
MODELLING_METRICS = OUT / "modelling_metrics.json"
BENCHMARK = OUT / "benchmark.json"
DASHBOARD = ROOT / "dashboard.html"

# The audited agency, mode and archive date. Adding another agency means adding a
# benchmark row, not changing the schema.
AGENCY = "SEPTA"
MODE = "bus"
DAY = "2026-01-04"

# US Eastern offset used to derive local hour-of-day from the feed's UTC timestamps.
# The archive slice is a single winter day, so a fixed offset is safe here; a run
# spanning a daylight-saving boundary would need a proper timezone conversion.
TZ_OFFSET_HOURS = 5

# Only predictions made between 0 and 60 minutes ahead count. Beyond an hour a
# trip_updates entry is closer to a restatement of the timetable than a live prediction.
MAX_LEAD_S = 3600

# Matched pairs more than 30 minutes apart are treated as identifier collisions rather
# than genuine predictions and dropped.
MAX_PLAUSIBLE_ERROR_S = 1800

# Lead-time bands, defined once. An earlier version repeated this expression in three
# places and a change to one of them produced figures that disagreed with the text.
LEAD_BANDS_SQL = """
    CASE WHEN lead <= 120  THEN '0-2'
         WHEN lead <= 300  THEN '2-5'
         WHEN lead <= 600  THEN '5-10'
         WHEN lead <= 1200 THEN '10-20'
         ELSE '20-60' END
"""
BAND_ORDER = ["0-2", "2-5", "5-10", "10-20", "20-60"]

# A "large failure" is an absolute error over two minutes, matching the within-2-minutes
# statistic reported elsewhere.
LARGE_FAILURE_S = 120

# Plot colours, kept consistent across the static figures and the dashboard.
BLUE = "#2b6cb0"
ORANGE = "#c05621"
TEAL = "#0d9488"
