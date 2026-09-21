"""CLI: build the canonical Parquet tables from the raw cache.

Calls the same `hub.fetch.nba` functions as the backfill, so if the cache is
already populated (via `hub.fetch.backfill`) this makes no network calls at
all — it's a pure transform step. If the cache is missing something, it falls
back to fetching it live (same throttle/retry/cache behavior), so this is
also safe to run standalone for a quick, small-scope table build.

    uv run python -m hub.tables.pipeline
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import polars as pl

from hub.fetch import nba
from hub.fetch.cache import RawCache
from hub.fetch.client import FetchError, NbaFetcher
from hub.tables import build, quality
from hub.tables import seasons as season_utils

logger = logging.getLogger("hub.tables.pipeline")

DEFAULT_DATA_ROOT = Path(__file__).resolve().parents[4] / "data"


def run(
    data_root: Path,
    start_year: int,
    end_year: int,
    pbp_start_year: int,
    pbp_end_year: int,
    max_teams: int | None = None,
    max_games_per_season: int | None = None,
    pbp_cache_only: bool = False,
) -> dict:
    cache = RawCache(data_root / "raw")
    fetcher = NbaFetcher(cache)
    tables_dir = data_root / "tables"
    tables_dir.mkdir(parents=True, exist_ok=True)

    box_seasons = season_utils.season_range(start_year, end_year)
    pbp_seasons = season_utils.season_range(pbp_start_year, pbp_end_year)
    team_ids = [t["id"] for t in nba.get_teams().to_dicts()]
    if max_teams is not None:
        team_ids = team_ids[:max_teams]

    logger.info("=== teams ===")
    teams = build.build_teams(nba.get_teams())
    common_all_players = nba.fetch_common_all_players(fetcher)

    player_game_logs_parts = []
    team_game_logs_parts = []
    player_seasons_parts = []
    shots_parts = []
    skipped: dict[str, list] = {"shots": [], "bios": [], "pbp": []}

    for i, season in enumerate(box_seasons, 1):
        logger.info(
            "=== season %s (%d/%d): game logs & season stats ===", season, i, len(box_seasons)
        )
        player_log = nba.fetch_league_game_log(fetcher, season, "player")
        team_log = nba.fetch_league_game_log(fetcher, season, "team")
        base_stats = nba.fetch_league_dash_player_stats(fetcher, season, "Base")
        advanced_stats = nba.fetch_league_dash_player_stats(fetcher, season, "Advanced")

        player_game_logs_parts.append(build.build_player_game_logs(player_log, season))
        team_game_logs_parts.append(build.build_team_game_logs(team_log, season))
        player_seasons_parts.append(build.build_player_seasons(base_stats, advanced_stats, season))

        logger.info("=== season %s: shots (%d teams) ===", season, len(team_ids))
        for j, team_id in enumerate(team_ids, 1):
            try:
                raw_shots = nba.fetch_shot_chart_team(fetcher, season, team_id)
            except FetchError as exc:
                logger.warning("skipping shots for season %s team %s: %s", season, team_id, exc)
                skipped["shots"].append({"season": season, "team_id": team_id})
                continue
            if raw_shots.height > 0:
                shots_parts.append(build.build_shots(raw_shots, season))
            if j % 10 == 0 or j == len(team_ids):
                logger.info("  season %s shots: team %d/%d done", season, j, len(team_ids))

    player_game_logs = pl.concat(player_game_logs_parts, how="diagonal_relaxed")
    team_game_logs = pl.concat(team_game_logs_parts, how="diagonal_relaxed")
    player_seasons = pl.concat(player_seasons_parts, how="diagonal_relaxed")
    shots = pl.concat(shots_parts, how="diagonal_relaxed")
    games = build.build_games(team_game_logs)

    scoped_player_ids = player_game_logs["player_id"].unique().to_list()
    logger.info("=== player bios (%d players who appear in our scope) ===", len(scoped_player_ids))
    bio_parts = []
    for i, player_id in enumerate(scoped_player_ids, 1):
        try:
            bio_parts.append(nba.fetch_player_bio(fetcher, player_id))
        except FetchError as exc:
            logger.warning("skipping bio for player %s: %s", player_id, exc)
            skipped["bios"].append({"player_id": player_id})
        if i % 50 == 0 or i == len(scoped_player_ids):
            logger.info("  bios: player %d/%d done", i, len(scoped_player_ids))
    bios = pl.concat(bio_parts, how="diagonal_relaxed")
    players = build.build_players(common_all_players, bios)

    pbp_parts = []
    for season in pbp_seasons:
        team_log = nba.fetch_league_game_log(fetcher, season, "team")
        game_ids = team_log["GAME_ID"].unique().to_list()
        if max_games_per_season is not None:
            game_ids = game_ids[:max_games_per_season]
        logger.info("=== season %s: play-by-play (%d games) ===", season, len(game_ids))
        for k, game_id in enumerate(game_ids, 1):
            if pbp_cache_only and not cache.has("playbyplayv3", {"game_id": game_id}):
                skipped["pbp"].append(
                    {"season": season, "game_id": game_id, "reason": "not cached"}
                )
                continue
            try:
                raw_pbp = nba.fetch_play_by_play(fetcher, game_id)
            except FetchError as exc:
                logger.warning("skipping pbp for game %s: %s", game_id, exc)
                skipped["pbp"].append({"season": season, "game_id": game_id, "reason": str(exc)})
                continue
            if raw_pbp.height > 0:
                pbp_parts.append(build.build_pbp_events(raw_pbp))
            if k % 50 == 0 or k == len(game_ids):
                logger.info("  season %s pbp: game %d/%d done", season, k, len(game_ids))
    pbp_events = (
        pl.concat(pbp_parts, how="diagonal_relaxed") if pbp_parts else pl.DataFrame({"game_id": []})
    )

    tables = {
        "teams": teams,
        "players": players,
        "games": games,
        "player_game_logs": player_game_logs,
        "team_game_logs": team_game_logs,
        "player_seasons": player_seasons,
        "shots": shots,
        "pbp_events": pbp_events,
    }
    for name, df in tables.items():
        path = tables_dir / f"{name}.parquet"
        df.write_parquet(path)
        logger.info("wrote %s (%d rows, %d cols)", path, df.height, df.width)

    report = _run_quality_checks(tables)
    report["skipped"] = skipped
    report_path = tables_dir / "quality_report.json"
    report_path.write_text(json.dumps(report, indent=2, default=str))
    logger.info(
        "quality report: %d/%d checks passed, %d shots/%d bios/%d pbp calls skipped -> %s",
        report["total_checks"] - report["failed_checks"],
        report["total_checks"],
        len(skipped["shots"]),
        len(skipped["bios"]),
        len(skipped["pbp"]),
        report_path,
    )
    return report


def _run_quality_checks(tables: dict[str, pl.DataFrame]) -> dict:
    checks = [
        quality.check_row_count(tables["teams"], "teams", min_rows=30),
        quality.check_unique_key(tables["teams"], "teams", ["team_id"]),
        quality.check_row_count(tables["players"], "players", min_rows=100),
        quality.check_unique_key(tables["players"], "players", ["player_id"]),
        quality.check_row_count(tables["games"], "games", min_rows=100),
        quality.check_unique_key(tables["games"], "games", ["game_id"]),
        quality.check_null_rate(tables["games"], "games", "home_score", max_rate=0.01),
        quality.check_unique_key(
            tables["player_game_logs"], "player_game_logs", ["player_id", "game_id"]
        ),
        quality.check_unique_key(
            tables["team_game_logs"], "team_game_logs", ["team_id", "game_id"]
        ),
        quality.check_unique_key(
            tables["player_seasons"], "player_seasons", ["player_id", "team_id", "season"]
        ),
        quality.check_join_integrity(
            tables["player_game_logs"],
            "player_id",
            tables["players"],
            "player_id",
            "player_game_logs",
        ),
        quality.check_join_integrity(
            tables["team_game_logs"], "team_id", tables["teams"], "team_id", "team_game_logs"
        ),
        quality.check_join_integrity(
            tables["games"], "home_team_id", tables["teams"], "team_id", "games"
        ),
        quality.check_join_integrity(
            tables["shots"], "game_id", tables["games"], "game_id", "shots"
        ),
    ]
    if tables["pbp_events"].height > 0:
        checks.append(
            quality.check_join_integrity(
                tables["pbp_events"], "game_id", tables["games"], "game_id", "pbp_events"
            )
        )
    return quality.run_all(checks)


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", stream=sys.stdout
    )

    default_end_year = season_utils.most_recent_completed_season_start_year()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=DEFAULT_DATA_ROOT)
    parser.add_argument("--start-year", type=int, default=2015)
    parser.add_argument("--end-year", type=int, default=default_end_year)
    parser.add_argument("--pbp-start-year", type=int, default=default_end_year - 2)
    parser.add_argument("--pbp-end-year", type=int, default=default_end_year)
    parser.add_argument("--max-teams", type=int, default=None)
    parser.add_argument("--max-games-per-season", type=int, default=None)
    parser.add_argument(
        "--pbp-cache-only",
        action="store_true",
        help="Don't fetch any new play-by-play; build from whatever's already cached "
        "and mark the rest skipped. Useful when stats.nba.com is rate-limiting play-by-play "
        "but the other tables (which don't need new calls) should still be built.",
    )
    args = parser.parse_args(argv)

    run(
        data_root=args.data_root,
        start_year=args.start_year,
        end_year=args.end_year,
        pbp_start_year=args.pbp_start_year,
        pbp_end_year=args.pbp_end_year,
        max_teams=args.max_teams,
        max_games_per_season=args.max_games_per_season,
        pbp_cache_only=args.pbp_cache_only,
    )


if __name__ == "__main__":
    main()
