"""Sanity checks on the matched dataset and the metrics it produces.

These are not unit tests of individual functions; the stages are scripts, not a library.
They are the checks we actually cared about while building it: that the non-circular
construction holds, that the filters did what they were meant to, and that the headline
numbers haven't silently moved.

Run after ./run_all.sh:

    python3 -m pytest tests/ -v

Skips cleanly if the pipeline hasn't been run yet.
"""

import json
import sys
from pathlib import Path

import duckdb
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import config

pytestmark = pytest.mark.skipif(
    not Path(config.MATCHED_PAIRS).exists(),
    reason="run ./run_all.sh first",
)


@pytest.fixture(scope="module")
def con():
    return duckdb.connect()


def test_matched_pairs_exist(con):
    n = con.execute(f"SELECT count(*) FROM read_parquet('{config.MATCHED_PAIRS}')").fetchone()[0]
    assert n > 1_000_000, f"only {n:,} pairs, the join probably lost most of the feed"


def test_lead_window_respected(con):
    """No prediction should have survived outside the 0-60 minute window."""
    bad = con.execute(f"""
        SELECT count(*) FROM read_parquet('{config.MATCHED_PAIRS}')
        WHERE lead <= 0 OR lead > {config.MAX_LEAD_S}
    """).fetchone()[0]
    assert bad == 0


def test_error_plausibility_filter(con):
    bad = con.execute(f"""
        SELECT count(*) FROM read_parquet('{config.MATCHED_PAIRS}')
        WHERE abs_error > {config.MAX_PLAUSIBLE_ERROR_S}
    """).fetchone()[0]
    assert bad == 0


def test_error_is_prediction_minus_actual(con):
    """The whole audit rests on this arithmetic, so check it rather than assume it."""
    bad = con.execute(f"""
        SELECT count(*) FROM read_parquet('{config.MATCHED_PAIRS}')
        WHERE error <> pred_arrival - actual_arrival
           OR abs_error <> abs(pred_arrival - actual_arrival)
    """).fetchone()[0]
    assert bad == 0


def test_no_null_keys(con):
    bad = con.execute(f"""
        SELECT count(*) FROM read_parquet('{config.MATCHED_PAIRS}')
        WHERE trip_id IS NULL OR stop_id IS NULL
           OR pred_arrival IS NULL OR actual_arrival IS NULL
    """).fetchone()[0]
    assert bad == 0


def test_feed_states_no_uncertainty(con):
    """A load-bearing finding: if a future archive does populate this, the calibration
    chapter needs rewriting rather than quietly carrying on."""
    stated = con.execute(f"""
        SELECT count(*) FROM read_parquet('{config.MATCHED_PAIRS}')
        WHERE arrival_uncertainty IS NOT NULL AND arrival_uncertainty > 0
    """).fetchone()[0]
    assert stated == 0


def test_accuracy_degrades_with_lead(con):
    """Median error should rise monotonically across the lead bands. This is the study's
    central claim, so it gets a test."""
    rows = con.execute(f"""
        SELECT {config.LEAD_BANDS_SQL} AS band, min(lead) AS ord, median(abs_error) AS med
        FROM read_parquet('{config.MATCHED_PAIRS}')
        GROUP BY band ORDER BY ord
    """).fetchall()
    medians = [r[2] for r in rows]
    assert len(medians) == len(config.BAND_ORDER)
    assert medians == sorted(medians), f"not monotonic: {medians}"


@pytest.mark.skipif(not config.ACCURACY_METRICS.exists(), reason="run stage 2 first")
def test_headline_metrics_have_not_moved():
    """Guards the numbers quoted in the written report. If a change to the pipeline moves
    these, the report needs updating too, which is the point of the test failing."""
    with open(config.ACCURACY_METRICS) as fh:
        m = json.load(fh)
    assert m["n_pairs"] == 11_779_888
    assert m["median_abs_s"] == pytest.approx(64.0, abs=0.5)
    assert m["within_2min_pct"] == pytest.approx(70.9, abs=0.2)
    assert m["bias_s"] == pytest.approx(-30.0, abs=0.5)


@pytest.mark.skipif(not config.ACCURACY_METRICS.exists(), reason="run stage 2 first")
def test_conformal_coverage_is_calibrated():
    """Empirical coverage should land within a point of nominal at every level."""
    with open(config.ACCURACY_METRICS) as fh:
        coverage = json.load(fh)["conformal_empirical_coverage_pct"]
    for nominal, empirical in coverage.items():
        assert abs(empirical - int(nominal)) < 1.0, f"{nominal}% -> {empirical}%"


@pytest.mark.skipif(not config.MODELLING_METRICS.exists(), reason="run stage 3 first")
def test_no_leakage_in_error_model():
    """A high R2 on this feature set would mean the outcome had got into the features.
    The grouped split should keep it low; if this test starts passing with a big number,
    something has leaked."""
    with open(config.MODELLING_METRICS) as fh:
        m = json.load(fh)
    assert m["reg_r2"] < 0.35, f"R2 {m['reg_r2']} is suspiciously high, check for leakage"
    assert 0.5 < m["clf_auc"] < 0.9


@pytest.mark.skipif(not config.MODELLING_METRICS.exists(), reason="run stage 3 first")
def test_lead_time_is_the_dominant_driver():
    with open(config.MODELLING_METRICS) as fh:
        shap = json.load(fh)["shap_importance_s"]
    assert max(shap, key=shap.get) == "lead"
