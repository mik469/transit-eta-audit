"""Stage 3: why do the predictions go wrong?

Stage 2 says how wrong they are. This stage asks whether the errors are systematic
enough to be anticipated from conditions known when the prediction was published, using
gradient boosting as a diagnostic instrument rather than a competitor to the feed.

Leakage is the thing to get right here. The most informative predictors of an error are
usually contaminated by the outcome, and a model built on them looks like it explains
the error when it is really just re-encoding it. Two controls:

  * features are restricted to quantities available at publication time
  * the train/test split is grouped by trip, so no trip appears on both sides

The first version of this had neither, scored R^2 above 0.6, and was meaningless. The
modest number this version reports is the honest one.

Writes out/modelling_metrics.json and two figures.
"""

import json

import duckdb
import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import xgboost as xgb
from sklearn.metrics import (mean_absolute_error, precision_recall_curve, r2_score,
                             roc_auc_score, roc_curve)

import config

FEATURES = ["lead", "hour", "dow", "direction_id", "stop_sequence", "arrival_delay",
            "route_freq"]

con = duckdb.connect()

print("Stage 3: failure-cause modelling")

# Training on all 11.8M rows is unnecessary and slow, so take one row in twenty. The
# filter hashes the row key rather than using DuckDB's reservoir sampling: reservoir
# results depend on the order rows come off a parallel scan, so they change between runs.
#
# The ORDER BY is load-bearing too, and it cost us an afternoon to work out. The hash
# filter fixes *which* rows come back but not what order they arrive in, and XGBoost's
# subsample picks rows by position, so re-running stage 1 could reshuffle the parquet
# and move MAE and R2 in the third decimal without anything else changing. Sorting on the
# row key pins the order regardless of how the file was written.
df = con.execute(f"""
    SELECT abs_error,
           (abs_error > {config.LARGE_FAILURE_S})::INT AS fail,
           lead,
           hour,
           dow,
           COALESCE(direction_id, 0)  AS direction_id,
           COALESCE(stop_sequence, 0) AS stop_sequence,
           COALESCE(arrival_delay, 0) AS arrival_delay,
           route_id,
           hash(trip_id) % 10 AS grp
    FROM read_parquet('{config.MATCHED_PAIRS}')
    WHERE hash(trip_id || '|' || stop_id || '|' || CAST(made_at AS VARCHAR)) % 20 = 0
    ORDER BY trip_id, stop_id, made_at
""").df()

is_train = df.grp < 8

# Route busyness is a summary of the data, so it has to be learned on the training
# trips alone. Computing it over everything would leak the test set into training.
busyness = df.loc[is_train, "route_id"].value_counts()
df["route_freq"] = df["route_id"].map(busyness).fillna(0)

train, test = df[is_train], df[~is_train]
x_train, x_test = train[FEATURES], test[FEATURES]
print(f"  features: {', '.join(FEATURES)}")
print(f"  {len(train):,} train / {len(test):,} test rows, disjoint trips")

# Conventional settings rather than tuned ones. The objective is diagnosis, and an
# extensive search over the test partition would be a form of leakage in itself.
common = dict(n_estimators=350, max_depth=6, learning_rate=0.08, subsample=0.8,
              colsample_bytree=0.8, n_jobs=4, random_state=42)

regressor = xgb.XGBRegressor(**common)
regressor.fit(x_train, train["abs_error"])
predicted = regressor.predict(x_test)
mae = mean_absolute_error(test["abs_error"], predicted)
r2 = r2_score(test["abs_error"], predicted)
print(f"  regression on |error|: MAE {mae:.1f}s, R2 {r2:.3f}")

classifier = xgb.XGBClassifier(eval_metric="auc", **common)
classifier.fit(x_train, train["fail"])
scores = classifier.predict_proba(x_test)[:, 1]
actual = test["fail"].values
auc = roc_auc_score(actual, scores)
base_rate = actual.mean() * 100
print(f"  large-failure classifier: AUC {auc:.3f} (base rate {base_rate:.1f}%)")


def thin(values, n=60):
    """Reduce a curve to n evenly spaced points so it can be embedded in the dashboard."""
    values = np.asarray(values, dtype=float)
    if len(values) <= n:
        return [round(float(v), 4) for v in values]
    idx = np.linspace(0, len(values) - 1, n).astype(int)
    return [round(float(values[i]), 4) for i in idx]


fpr, tpr, _ = roc_curve(actual, scores)
precision, recall, _ = precision_recall_curve(actual, scores)

# Exact TreeSHAP straight from the booster. The standalone shap package would not install
# against the numpy version here, and pred_contribs gives exact values for tree ensembles
# rather than sampled approximations, so this is the better route anyway.
sample = x_test.sample(4000, random_state=1)
contributions = regressor.get_booster().predict(xgb.DMatrix(sample), pred_contribs=True)
shap_values = contributions[:, :-1]          # last column is the base value
importance = np.abs(shap_values).mean(0)
order = np.argsort(importance)               # ascending, so the biggest driver plots last

# Beeswarm: one point per prediction, x is the seconds of error attributed to that
# feature, colour is the feature's own value.
feature_values = sample.values.astype(float)
jitter = np.random.default_rng(0)
fig, ax = plt.subplots(figsize=(7.4, 4.8))
for row, feature in enumerate(order):
    x = shap_values[:, feature]
    values = feature_values[:, feature]
    lo, hi = np.nanpercentile(values, 5), np.nanpercentile(values, 95)
    shade = np.clip((values - lo) / (hi - lo + 1e-9), 0, 1)
    ax.scatter(x, np.full(len(x), row) + jitter.uniform(-0.18, 0.18, len(x)),
               c=shade, cmap="coolwarm", s=6, alpha=0.5, edgecolors="none")
ax.axvline(0, color="k", lw=0.8)
ax.set_yticks(range(len(order)))
ax.set_yticklabels([FEATURES[i] for i in order])
ax.set_xlabel("SHAP value  (seconds of error attributed to the feature)")
ax.set_title("SHAP: what drives ETA prediction error")
scale = plt.cm.ScalarMappable(cmap="coolwarm")
scale.set_array([])
plt.colorbar(scale, ax=ax, label="feature value (low -> high)")
ax.spines[["top", "right"]].set_visible(False)
plt.tight_layout()
plt.savefig(config.FIGS / "03_shap_summary.png", dpi=140)
plt.close()

plt.figure(figsize=(6.6, 4))
plt.barh([FEATURES[i] for i in order], [importance[i] for i in order], color=config.BLUE)
plt.xlabel("mean |SHAP|  (seconds of error attributed)")
plt.title("Operational drivers of prediction error, ranked")
plt.tight_layout()
plt.savefig(config.FIGS / "03_feature_importance.png", dpi=140)
plt.close()

with open(config.MODELLING_METRICS, "w") as fh:
    json.dump({
        "reg_mae_s": round(float(mae), 1),
        "reg_r2": round(float(r2), 3),
        "clf_auc": round(float(auc), 3),
        "large_fail_base_rate_pct": round(float(base_rate), 1),
        "shap_importance_s": {FEATURES[i]: round(float(importance[i]), 2)
                              for i in np.argsort(-importance)},
        "roc": {"fpr": thin(fpr), "tpr": thin(tpr)},
        "pr": {"recall": thin(recall), "precision": thin(precision)},
    }, fh, indent=2)

print(f"  wrote {config.MODELLING_METRICS.name} and two figures")
