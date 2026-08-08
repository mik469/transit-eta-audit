"""Stage 4: collapse the audit into one comparable benchmark record.

The point of a benchmark is not the score, it is the protocol: everyone runs the same
measurement so the numbers mean the same thing. This writes a single row for the agency,
mode and day audited. Another agency, mode or date is another row, not a schema change.

Three things the record deliberately carries:

  * the sample size next to every metric, so a reader can weigh a score by its evidence
  * a tail measure as well as a central one, because a route with a good median and a bad
    tail can serve passengers worse than its rank suggests
  * a version number on the metric definitions, so a later change to (say) the lead-time
    window can't silently invalidate comparison with earlier records
"""

import json

import config

with open(config.ACCURACY_METRICS) as fh:
    accuracy = json.load(fh)
with open(config.MODELLING_METRICS) as fh:
    modelling = json.load(fh)

print("Stage 4: benchmark record")

record = {
    "agency": config.AGENCY,
    "mode": config.MODE,
    "day": config.DAY,
    "n_pairs": accuracy["n_pairs"],
    "median_abs_s": accuracy["median_abs_s"],
    "within_2min_pct": accuracy["within_2min_pct"],
    "p90_abs_s": accuracy["p90_abs_s"],
    "bias_s": accuracy["bias_s"],
    "large_fail_auc": modelling["clf_auc"],
    "conformal_coverage_90": accuracy["conformal_empirical_coverage_pct"]["90"],
}

with open(config.BENCHMARK, "w") as fh:
    json.dump({"benchmark_version": 1, "leaderboard": [record]}, fh, indent=2)

for key, value in record.items():
    print(f"  {key:<22} {value}")
print(f"  wrote {config.BENCHMARK.name}")
