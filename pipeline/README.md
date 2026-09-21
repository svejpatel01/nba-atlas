# hub pipeline

Offline data pipeline for the NBA data hub (nba.svej.org). Fetches stats.nba.com
data to a local raw cache, builds canonical Parquet tables, trains models, and
exports the static JSON/binary files the web app and Worker ship.

Run everything through the repo-root `Makefile`. See `../PLAN.md` for the full
project plan and `../docs/` for per-feature specs.
