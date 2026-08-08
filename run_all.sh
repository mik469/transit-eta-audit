#!/usr/bin/env bash
# Rebuilds the whole audit from the raw feeds: matched dataset, metrics, figures and
# the dashboard. Nothing downstream is hand-edited, so this is the only thing you need
# to run to reproduce every number in the report.
set -euo pipefail
cd "$(dirname "$0")"

# SEPTA's published schedule gives exact stop coordinates and real route names. Fetched
# once; skip if it's already unpacked.
if [ ! -f gtfs_static/google_bus/stops.txt ]; then
  echo "Fetching SEPTA GTFS static..."
  if curl -sSL --max-time 120 -o septa_gtfs.zip https://www3.septa.org/developer/gtfs_public.zip; then
    mkdir -p gtfs_static
    (
      cd gtfs_static
      unzip -oq ../septa_gtfs.zip
      for z in *.zip; do unzip -oq "$z" -d "${z%.zip}"; done
    )
  else
    echo "  download failed - the map falls back to a GPS-median estimate, which is worse"
  fi
fi

for stage in 01_pipeline 02_accuracy 03_modelling 04_benchmark 05_dashboard \
             06_report_figures 07_framework_figures; do
  echo
  python3 "src/$stage.py"
done

echo
echo "Done. Dataset in out/, figures in figs/, dashboard.html in the repo root."
