# NBA data hub

An NBA data hub with four interactive views built from stats.nba.com data:
player style map, ask the box score, shot quality court, and game flow. See
[`PLAN.md`](PLAN.md) for the full build plan and [`docs/`](docs/) for
per-feature specs. Notable choices and corrections are logged in
[`docs/decisions.md`](docs/decisions.md).

All heavy compute runs offline (`pipeline/`); the site ships precomputed
static files served by a single Cloudflare Worker (`worker/`), with a
Next.js static export (`web/`) as the frontend. The whole project runs on
Cloudflare's free plan.

## Layout

- `pipeline/` — Python: fetches stats.nba.com data, builds canonical tables,
  trains models, exports static files. Managed with `uv`.
- `web/` — Next.js app (static export). Managed with `pnpm`.
- `worker/` — Cloudflare Worker: serves the static export and handles
  `/api/*`. Managed with `pnpm` + `wrangler`.
- `data/` — gitignored. Raw cache, canonical tables, models, exports.
- `evals/` — golden datasets for the "ask the box score" eval.

## Getting started

Requires `uv`, `pnpm`, and Node 22+.

```
make test    # pipeline pytest + web vitest + worker vitest
make lint    # ruff + eslint + tsc --noEmit
make web     # build the Next.js static export (web/out)
make worker-dev  # run the Worker locally (wrangler dev), serving web/out
make deploy  # build the site and wrangler deploy (requires `wrangler login` first)
```

Run `make help` for the full target list, including the (not yet built)
per-feature pipeline targets.

## Status

Phase 0 (scaffold) complete: repo layout, `uv`/`pnpm` tooling, lint and test
wired up in each of `pipeline/`, `web/`, and `worker/`, CI running lint and
tests on push, and a Worker serving the static site plus a stub
`/api/health`. See `PLAN.md` for the phase list.
