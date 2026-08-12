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

TRIP_UPDATES = [str(FEED_DIR / "septa_tu_1.parquet"), str(FEED_DIR / "septa_tu_2.parquet")]
BUS_POSITIONS = str(FEED_DIR / "septa_bus_vp.parquet")
RAIL_POSITIONS = str(FEED_DIR / "septa_vp.parquet")

MATCHED_PAIRS = str(OUT / "matched_pairs.parquet")
ACCURACY_METRICS = OUT / "accuracy_metrics.json"
MODELLING_METRICS = OUT / "modelling_metrics.json"
BENCHMARK = OUT / "benchmark.json"
DASHBOARD = ROOT / "dashboard.html"

AGENCY = "SEPTA"
MODE = "bus"
DAY = "2026-01-04"

TZ_OFFSET_HOURS = 5

MAX_LEAD_S = 3600

MAX_PLAUSIBLE_ERROR_S = 1800

LEAD_BANDS_SQL = """
    CASE WHEN lead <= 120  THEN '0-2'
         WHEN lead <= 300  THEN '2-5'
         WHEN lead <= 600  THEN '5-10'
         WHEN lead <= 1200 THEN '10-20'
         ELSE '20-60' END
"""
BAND_ORDER = ["0-2", "2-5", "5-10", "10-20", "20-60"]

LARGE_FAILURE_S = 120

FIG_DPI = 300

BLUE = "#2b6cb0"
ORANGE = "#c05621"
TEAL = "#0d9488"
