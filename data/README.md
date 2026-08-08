# Raw data

The four feed files are about 180 MB in total, which is past what belongs in a git
repository, so they are not committed. Everything in `out/` and `figs/` is rebuilt from
them, so you need them before `run_all.sh` will do anything useful.

Drop them in this directory:

| File | Contents | Approx. size |
| --- | --- | --- |
| `septa_tu_1.parquet` | `trip_updates`, the agency's predicted arrivals | 114 MB |
| `septa_tu_2.parquet` | `trip_updates`, continued | 14 MB |
| `septa_bus_vp.parquet` | `vehicle_positions`, bus GPS, the ground truth | 30 MB |
| `septa_vp.parquet` | `vehicle_positions`, regional rail GPS | 15 MB |

`src/config.py` looks here first and falls back to the parent directory, which is where
they sat during development.

## Where they come from

[gtfsrt.io](https://gtfsrt.io) archives public GTFS-Realtime feeds and republishes them
as date-partitioned Parquet. We took SEPTA's `trip_updates` and `vehicle_positions` for
**4 January 2026** from the `parquet.gtfsrt.io` bucket.

The date was fixed before any analysis was run, and no alternative date was inspected and
discarded, since picking a day after seeing its results would turn an audit into a
demonstration.

## Static schedule

`run_all.sh` fetches this automatically on first run:

```
https://www3.septa.org/developer/gtfs_public.zip
```

It unpacks to `gtfs_static/`, and supplies the published stop coordinates and route
names. It matters more than it sounds: an early version of the dashboard estimated stop
positions from the median of vehicle GPS fixes, and for a handful of reused stop ids that
put stops up to twelve kilometres from where they actually are. 99.5% of the 9,856
analysed stops resolve against the official file.

## A caveat on coverage

The archive slice is not a complete day. Matched predictions span roughly 05:14 to 23:59
UTC, which is 16 of 24 local clock hours with a gap across the mid-afternoon. This is why
the hour-by-lead heatmap in the dashboard has blank columns, and why the report treats
the afternoon-peak findings as partial.
