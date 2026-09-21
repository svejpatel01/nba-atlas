"""Builds the player-season style feature table across all seasons: fetches
(from cache) every raw source, builds each feature group, shrinks the
volume-sensitive shares, standardizes within season, applies group weights,
and concatenates into one matrix ready for PCA/GMM/UMAP.

    uv run python -m hub.style.pipeline
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import polars as pl

from hub.fetch import nba
from hub.fetch.cache import RawCache
from hub.fetch.client import NbaFetcher
from hub.style import features, preprocess
from hub.style.fetch_data import PLAY_TYPES
from hub.tables import seasons as season_utils

logger = logging.getLogger("hub.style.pipeline")

DEFAULT_DATA_ROOT = Path(__file__).resolve().parents[4] / "data"
MIN_MINUTES = 500

# (share_col, volume_col, k) — shrinkage pseudo-counts. Shot-zone shares use
# total_fga as volume; play-type shares use each play type's own possession
# count isn't a shared volume, so those are shrunk against total tracked
# possessions instead (see build_season_feature_table).
SHOT_DIET_SHRINK = [
    (col, "total_fga", 20.0)
    for col in [
        "share_fga_restricted_area",
        "share_fga_paint_non_ra",
        "share_fga_midrange",
        "share_fga_corner3",
        "share_fga_atb3",
    ]
]

ALL_FEATURE_GROUPS: dict[str, list[str]] = {
    **features.FEATURE_GROUPS,
    "play_types": [f"playtype_{p}" for p in PLAY_TYPES],
}
ALL_FEATURE_COLS = [c for cols in ALL_FEATURE_GROUPS.values() for c in cols]


def build_season_feature_table(
    fetcher: NbaFetcher, season: str, shots_season: pl.DataFrame
) -> pl.DataFrame:
    base = nba.fetch_league_dash_player_stats(fetcher, season, "Base")
    advanced = nba.fetch_league_dash_player_stats(fetcher, season, "Advanced")
    scoring = nba.fetch_league_dash_player_stats(fetcher, season, "Scoring")
    possessions = nba.fetch_league_dash_pt_stats(fetcher, season, "Possessions")
    drives = nba.fetch_league_dash_pt_stats(fetcher, season, "Drives")
    passing = nba.fetch_league_dash_pt_stats(fetcher, season, "Passing")
    catch_shoot = nba.fetch_league_dash_pt_stats(fetcher, season, "CatchShoot")
    pull_up = nba.fetch_league_dash_pt_stats(fetcher, season, "PullUpShot")
    play_type_dfs = {pt: nba.fetch_synergy_play_type(fetcher, season, pt) for pt in PLAY_TYPES}

    shot_diet = features.add_fta_per_fga(features.build_shot_diet_features(shots_season), base)
    role = features.build_role_features(advanced)
    reb_def = features.build_rebound_defense_features(base, advanced)
    self_creation = features.build_self_creation_features(scoring)
    ball_handling = features.build_ball_handling_features(possessions, drives, passing, base)
    shooting_mode = features.build_shooting_mode_features(catch_shoot, pull_up, base)
    touch_location = features.build_touch_location_features(possessions)
    play_types = features.build_play_type_features(play_type_dfs)

    table = shot_diet
    for part in [
        role,
        reb_def,
        self_creation,
        ball_handling,
        shooting_mode,
        touch_location,
        play_types,
    ]:
        table = table.join(part, on="player_id", how="left")
        if table.height != table["player_id"].n_unique():
            raise ValueError(
                f"{season}: join produced duplicate player_id rows ({table.height} rows, "
                f"{table['player_id'].n_unique()} unique) — a source table has more than "
                "one row per player_id (e.g. a traded player split across teams without "
                "a combined total row)."
            )

    minutes = base.select(pl.col("PLAYER_ID").alias("player_id"), pl.col("MIN").alias("minutes"))
    names = base.select(pl.col("PLAYER_ID").alias("player_id"), pl.col("PLAYER_NAME").alias("name"))
    table = table.join(minutes, on="player_id", how="left").join(names, on="player_id", how="left")

    table = table.filter(pl.col("minutes") >= MIN_MINUTES).fill_null(0)
    table = preprocess.apply_shrinkage(table, SHOT_DIET_SHRINK)
    table = preprocess.standardize_within_season(table, ALL_FEATURE_COLS)
    table = preprocess.apply_group_weights(table, ALL_FEATURE_GROUPS)
    return table.with_columns(pl.lit(season).alias("season"))


def run(data_root: Path, start_year: int, end_year: int) -> pl.DataFrame:
    cache = RawCache(data_root / "raw")
    fetcher = NbaFetcher(cache)
    seasons = season_utils.season_range(start_year, end_year)
    shots = pl.read_parquet(data_root / "tables" / "shots.parquet")

    parts = []
    for i, season in enumerate(seasons, 1):
        logger.info("=== season %s (%d/%d): building features ===", season, i, len(seasons))
        shots_season = shots.filter(pl.col("season") == season)
        parts.append(build_season_feature_table(fetcher, season, shots_season))

    combined = pl.concat(parts, how="diagonal_relaxed")
    logger.info(
        "built feature table: %d player-seasons, %d columns", combined.height, combined.width
    )
    out_path = data_root / "tables" / "style_features.parquet"
    combined.write_parquet(out_path)
    logger.info("wrote %s", out_path)
    return combined


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
