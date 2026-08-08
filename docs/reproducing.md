# Reproducing the results

## What "reproducible" means here

Running `./run_all.sh` twice on the same machine produces byte-identical metric files.
That is a stronger claim than it sounds, and it took work to make true.

The first version of stage 3 sampled its training rows with DuckDB's reservoir sampling
and left XGBoost's subsampling unseeded. Reservoir results depend on the order rows come
off a parallel scan, so consecutive runs of the same script produced different metrics:
MAE moving by a second or so, R² in the third decimal. Small, but it would have made the
reproducibility claim in the report false. Two changes fixed it:

* the training sample is now a hash filter on the row key, which is order-independent
* both models take `random_state=42`, as does the SHAP subsample

You can check it:

```bash
./run_all.sh && shasum -a 256 out/*.json > /tmp/first
./run_all.sh && shasum -a 256 out/*.json | diff - /tmp/first && echo identical
```

## What isn't captured

Dependencies are pinned to exact versions in `requirements.txt`, but there's no container
image, so a different Python minor version or a different BLAS could still move a
floating-point digit. Publishing an image is the obvious next step and hasn't been done.

## Stage dependencies

Stages run in order and each one reads the previous stage's output, so the script fails
fast if something upstream is missing rather than quietly producing figures from a stale
dataset.

```
01_pipeline ──> out/matched_pairs.parquet
                      │
        ┌─────────────┼─────────────┐
        ▼             ▼             ▼
  02_accuracy   03_modelling   06_report_figures
        │             │
        └──────┬──────┘
               ▼
        04_benchmark ──> 05_dashboard
```

`07_framework_figures` depends on nothing and can run any time.

## Runtime

About 30 seconds end to end on an M-series MacBook, most of it in stage 1 joining
17 million prediction rows against the position feed. Peak memory sits around 6 GB.
