.PHONY: help fetch tables build-style build-shots build-gameflow build-ask export \
        web worker-dev deploy test lint typecheck

help:
	@echo "Targets:"
	@echo "  test           run pipeline, web, and worker test suites"
	@echo "  lint           run ruff, eslint (web + worker)"
	@echo "  typecheck      run tsc --noEmit for web and worker"
	@echo "  web            build the Next.js static export (web/out)"
	@echo "  worker-dev     run the Worker locally with wrangler dev"
	@echo "  deploy         build the site and deploy the Worker (wrangler deploy)"
	@echo "  fetch          [Phase 1] run the nba_api fetch layer"
	@echo "  tables         [Phase 1] build canonical Parquet tables"
	@echo "  fetch-style    [Phase 2] fetch tracking/play-type data for the style map"
	@echo "  build-style    [Phase 2] build the player style map artifacts"
	@echo "  build-shots    [Phase 4] build the shot quality court artifacts"
	@echo "  build-gameflow [Phase 5] build the game flow artifacts"
	@echo "  build-ask      [Phase 3] build the ask-the-box-score DuckDB exports"
	@echo "  export         run all build-* targets and copy exports into web/public/data"

test:
	cd pipeline && uv run pytest
	cd web && pnpm test
	cd worker && pnpm test

lint:
	cd pipeline && uv run ruff check .
	cd web && pnpm lint
	cd worker && pnpm exec tsc --noEmit --project tsconfig.json

typecheck:
	cd web && pnpm typecheck
	cd worker && pnpm typecheck

web:
	cd web && pnpm build

worker-dev: web
	cd worker && pnpm dev

deploy: web
	cd worker && pnpm run deploy

# PYTHONPATH=src bypasses the editable-install .pth file: on this machine the
# repo sits under iCloud-synced ~/Desktop, and iCloud independently flips the
# macOS hidden flag on that .pth at unpredictable times, which Python 3.13
# skips during site init (see docs/decisions.md). Setting PYTHONPATH directly
# is immune to it and doesn't depend on iCloud's sync timing.
fetch:
	cd pipeline && PYTHONPATH=src uv run python -m hub.fetch.backfill

tables:
	cd pipeline && PYTHONPATH=src uv run python -m hub.tables.pipeline

fetch-style:
	cd pipeline && PYTHONPATH=src uv run python -m hub.style.fetch_data

build-style:
	cd pipeline && PYTHONPATH=src uv run python -m hub.style.pipeline
	cd pipeline && PYTHONPATH=src uv run python -m hub.style.export

build-shots:
	cd pipeline && PYTHONPATH=src uv run python -m hub.shots.export

build-gameflow:
	cd pipeline && PYTHONPATH=src uv run python -m hub.gameflow.export

build-ask:
	cd pipeline && PYTHONPATH=src uv run python -m hub.ask.export
	cd pipeline && PYTHONPATH=src uv run python -m hub.ask.examples

export: build-ask build-style build-shots build-gameflow
