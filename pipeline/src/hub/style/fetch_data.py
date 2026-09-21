"""CLI: populate the raw cache with tracking stats, scoring splits, and
play-type data needed for the player style map's Modern-mode features
(docs/player-style-map-spec.md). Doesn't build the feature table — that's
`hub.style.features`, which reads through these same fetch functions.

    uv run python -m hub.style.fetch_data

~187 calls total for the full 2015-16..2025-26 range: 5 tracking measure
types + 1 scoring split, per season (66 calls), plus 10 play types per
season (110 calls), plus a couple of one-time calls.
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

logger = logging.getLogger("hub.style.fetch_data")

DEFAULT_DATA_ROOT = Path(__file__).resolve().parents[4] / "data"

# The five LeagueDashPtStats measure types that cover ball-handling,
# shooting-mode, and touch-location features — confirmed live that
# "Possessions" alone includes touches, seconds/dribbles per touch, and
# elbow/post/paint touch counts, so no separate touch-type calls are needed.
PT_MEASURE_TYPES = ["Possessions", "Drives", "Passing", "CatchShoot", "PullUpShot"]

# The style-map spec's 10 offensive play types (excludes nba_api's "Misc"
# catch-all, which isn't one of the spec's named categories).
PLAY_TYPES = [
    "Transition",
    "Isolation",
    "PRBallHandler",
    "PRRollman",
    "Postup",
    "Spotup",
    "Handoff",
    "Cut",
    "OffScreen",
    "OffRebound",
]


def run(data_root: Path, start_year: int, end_year: int) -> None:
    cache = RawCache(data_root / "raw")
    fetcher = NbaFetcher(cache)
    seasons = season_utils.season_range(start_year, end_year)

    logger.info(
        "Style data scope: %s..%s (%d seasons), %d pt measure types, %d play types",
        seasons[0],
        seasons[-1],
        len(seasons),
        len(PT_MEASURE_TYPES),
        len(PLAY_TYPES),
    )

    for i, season in enumerate(seasons, 1):
        logger.info("=== season %s (%d/%d): tracking stats ===", season, i, len(seasons))
        for measure_type in PT_MEASURE_TYPES:
            try:
                nba.fetch_league_dash_pt_stats(fetcher, season, measure_type)
            except FetchError as exc:
                logger.warning("skipping pt stats %s/%s: %s", season, measure_type, exc)

        try:
            nba.fetch_league_dash_player_stats(fetcher, season, "Scoring")
        except FetchError as exc:
            logger.warning("skipping scoring stats %s: %s", season, exc)

        logger.info("=== season %s: play types (%d) ===", season, len(PLAY_TYPES))
        for play_type in PLAY_TYPES:
            try:
                nba.fetch_synergy_play_type(fetcher, season, play_type)
            except FetchError as exc:
                logger.warning("skipping play type %s/%s: %s", season, play_type, exc)

    logger.info("Style data fetch complete.")


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", stream=sys.stdout
    )
    default_end_year = season_utils.most_recent_completed_season_start_year()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=DEFAULT_DATA_ROOT)
    parser.add_argument("--start-year", type=int, default=2015)
    parser.add_argument("--end-year", type=int, default=default_end_year)
    args = parser.parse_args(argv)
    run(data_root=args.data_root, start_year=args.start_year, end_year=args.end_year)


if __name__ == "__main__":
    main()
