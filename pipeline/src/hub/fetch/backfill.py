"""CLI: populate the raw cache for the full Phase 1 scope.

Doesn't build canonical tables — that's `hub.tables.pipeline`, which reads
through the same fetch functions (and therefore hits this cache instead of
the network). Safe to interrupt (Ctrl-C, machine sleep, crash) and rerun:
every completed (endpoint, params) call is cached and skipped on rerun, so
this is the resumability PLAN.md asks for.

    uv run python -m hub.fetch.backfill
    uv run python -m hub.fetch.backfill --start-year 2015 --end-year 2025 \\
        --pbp-start-year 2023 --pbp-end-year 2025
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from hub.fetch import nba
from hub.fetch.cache import RawCache
from hub.fetch.client import FetchError, NbaFetcher
from hub.tables import seasons as season_utils

logger = logging.getLogger("hub.fetch.backfill")

DEFAULT_DATA_ROOT = Path(__file__).resolve().parents[4] / "data"


def run(
    data_root: Path,
    start_year: int,
    end_year: int,
    pbp_start_year: int,
    pbp_end_year: int,
    max_teams: int | None = None,
    max_games_per_season: int | None = None,
) -> None:
    cache = RawCache(data_root / "raw")
    fetcher = NbaFetcher(cache)

    box_seasons = season_utils.season_range(start_year, end_year)
    pbp_seasons = season_utils.season_range(pbp_start_year, pbp_end_year)
    team_ids = [t["id"] for t in nba.get_teams().to_dicts()]
    if max_teams is not None:
        team_ids = team_ids[:max_teams]

    logger.info(
        "Backfill scope: box/shots seasons %s..%s (%d seasons), "
        "pbp seasons %s..%s (%d seasons), %d teams",
        box_seasons[0],
        box_seasons[-1],
        len(box_seasons),
        pbp_seasons[0],
        pbp_seasons[-1],
        len(pbp_seasons),
        len(team_ids),
    )

    logger.info("=== players & teams (one-time) ===")
    nba.fetch_common_all_players(fetcher)

    all_player_ids: set[int] = set()
    for i, season in enumerate(box_seasons, 1):
        logger.info(
            "=== season %s (%d/%d): game logs & season stats ===", season, i, len(box_seasons)
        )
        player_log = nba.fetch_league_game_log(fetcher, season, "player")
        all_player_ids.update(player_log["PLAYER_ID"].unique().to_list())
        nba.fetch_league_game_log(fetcher, season, "team")
        nba.fetch_league_dash_player_stats(fetcher, season, "Base")
        nba.fetch_league_dash_player_stats(fetcher, season, "Advanced")

        logger.info("=== season %s: shots (%d teams) ===", season, len(team_ids))
        for j, team_id in enumerate(team_ids, 1):
            try:
                nba.fetch_shot_chart_team(fetcher, season, team_id)
            except FetchError as exc:
                logger.warning("skipping shots for season %s team %s: %s", season, team_id, exc)
            if j % 10 == 0 or j == len(team_ids):
                logger.info("  season %s shots: team %d/%d done", season, j, len(team_ids))

    logger.info("=== player bios (%d players who appear in our scope) ===", len(all_player_ids))
    for i, player_id in enumerate(sorted(all_player_ids), 1):
        try:
            nba.fetch_player_bio(fetcher, player_id)
        except FetchError as exc:
            logger.warning("skipping bio for player %s: %s", player_id, exc)
        if i % 50 == 0 or i == len(all_player_ids):
            logger.info("  bios: player %d/%d done", i, len(all_player_ids))

    for season in pbp_seasons:
        team_log = nba.fetch_league_game_log(fetcher, season, "team")
        game_ids = team_log["GAME_ID"].unique().to_list()
        if max_games_per_season is not None:
            game_ids = game_ids[:max_games_per_season]
        logger.info("=== season %s: play-by-play (%d games) ===", season, len(game_ids))
        for k, game_id in enumerate(game_ids, 1):
            try:
                nba.fetch_play_by_play(fetcher, game_id)
            except FetchError as exc:
                logger.warning("skipping pbp for game %s: %s", game_id, exc)
            if k % 50 == 0 or k == len(game_ids):
                logger.info("  season %s pbp: game %d/%d done", season, k, len(game_ids))

    logger.info("Backfill complete.")


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
    parser.add_argument(
        "--max-teams", type=int, default=None, help="Testing: cap teams per season."
    )
    parser.add_argument(
        "--max-games-per-season", type=int, default=None, help="Testing: cap PBP games per season."
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
    )


if __name__ == "__main__":
    main()
