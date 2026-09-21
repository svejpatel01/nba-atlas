"""CLI: export DuckDB-friendly Parquet files for "ask the box score" from the
canonical tables in data/tables/. Ships straight into web/public/data/ask/
(gitignored; `make deploy` is what actually publishes it, same as every other
export — data never goes into git).

    uv run python -m hub.ask.export
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import polars as pl

from hub.export.schemas import ASK_SCHEMA_VERSION, assert_columns_match

logger = logging.getLogger("hub.ask.export")

DEFAULT_TABLES_DIR = Path(__file__).resolve().parents[4] / "data" / "tables"
DEFAULT_OUT_DIR = Path(__file__).resolve().parents[4] / "web" / "public" / "data" / "ask"

# Column selection per table: trims fields that don't earn their place in a
# ~2MB-per-season budget (video_available, redundant season_id when we already
# stamp `season`, etc.) without dropping anything a question would plausibly need.
TABLE_COLUMNS: dict[str, list[str]] = {
    "players": [
        "player_id",
        "name",
        "from_year",
        "to_year",
        "position",
        "height",
        "weight",
        "college",
        "country",
        "draft_year",
        "birthdate",
    ],
    "teams": ["team_id", "full_name", "abbreviation", "nickname", "city", "state", "year_founded"],
    "games": [
        "game_id",
        "season",
        "game_date",
        "home_team_id",
        "home_score",
        "home_wl",
        "away_team_id",
        "away_score",
    ],
    "player_game_logs": [
        "season",
        "player_id",
        "player_name",
        "team_id",
        "team_abbreviation",
        "game_id",
        "game_date",
        "matchup",
        "wl",
        "min",
        "fgm",
        "fga",
        "fg_pct",
        "fg3m",
        "fg3a",
        "fg3_pct",
        "ftm",
        "fta",
        "ft_pct",
        "oreb",
        "dreb",
        "reb",
        "ast",
        "stl",
        "blk",
        "tov",
        "pf",
        "pts",
        "plus_minus",
    ],
    "team_game_logs": [
        "season",
        "team_id",
        "team_abbreviation",
        "team_name",
        "game_id",
        "game_date",
        "matchup",
        "wl",
        "min",
        "fgm",
        "fga",
        "fg_pct",
        "fg3m",
        "fg3a",
        "fg3_pct",
        "ftm",
        "fta",
        "ft_pct",
        "oreb",
        "dreb",
        "reb",
        "ast",
        "stl",
        "blk",
        "tov",
        "pf",
        "pts",
        "plus_minus",
    ],
    "player_seasons": [
        "season",
        "player_id",
        "player_name",
        "team_id",
        "gp",
        "min",
        "pts",
        "reb",
        "ast",
        "stl",
        "blk",
        "tov",
        "fg_pct",
        "fg3_pct",
        "ft_pct",
        "usg_pct",
        "ts_pct",
        "ast_pct",
        "oreb_pct",
        "dreb_pct",
        "pie",
    ],
}

TABLE_DESCRIPTIONS: dict[str, str] = {
    "players": "One row per player, career span and bio. Bio fields null outside 2015-16+.",
    "teams": "The 30 NBA franchises.",
    "games": "One row per game: teams, final score, date. home_wl is 'W'/'L' for the home team.",
    "player_game_logs": "One row per player per game they played, regular season, 2015-16 onward.",
    "team_game_logs": "One row per team per game, regular season, 2015-16 onward.",
    "player_seasons": "One row per player per season: season totals and per-game/advanced rates.",
}


def run(tables_dir: Path, out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest: dict = {"schema_version": ASK_SCHEMA_VERSION, "tables": {}}

    for name in ["players", "teams", "games", "team_game_logs", "player_seasons"]:
        df = pl.read_parquet(tables_dir / f"{name}.parquet").select(TABLE_COLUMNS[name])
        assert_columns_match(name, df.columns)
        path = out_dir / f"{name}.parquet"
        df.write_parquet(path, compression="zstd")
        manifest["tables"][name] = {
            "file": path.name,
            "rows": df.height,
            "columns": {c: str(t) for c, t in zip(df.columns, df.dtypes, strict=True)},
            "description": TABLE_DESCRIPTIONS[name],
        }
        logger.info("wrote %s (%d rows)", path, df.height)

    # player_game_logs ships one file per season per the data contract, since
    # a single ~281k-row file would blow the "load lazily on /ask" budget.
    pgl = pl.read_parquet(tables_dir / "player_game_logs.parquet").select(
        TABLE_COLUMNS["player_game_logs"]
    )
    assert_columns_match("player_game_logs", pgl.columns)
    seasons = sorted(pgl["season"].unique().to_list())
    season_files = []
    for season in seasons:
        season_df = pgl.filter(pl.col("season") == season)
        fname = f"player_game_logs_{season}.parquet"
        season_df.write_parquet(out_dir / fname, compression="zstd")
        season_files.append(fname)
    manifest["tables"]["player_game_logs"] = {
        "files": season_files,
        "rows": pgl.height,
        "columns": {c: str(t) for c, t in zip(pgl.columns, pgl.dtypes, strict=True)},
        "description": TABLE_DESCRIPTIONS["player_game_logs"]
        + " Sharded one file per season: player_game_logs_{season}.parquet.",
    }
    logger.info("wrote %d player_game_logs season files", len(season_files))

    manifest_path = out_dir / "schema.json"
    manifest_path.write_text(json.dumps(manifest, indent=2))
    logger.info("wrote %s", manifest_path)
    return manifest


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", stream=sys.stdout
    )
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tables-dir", type=Path, default=DEFAULT_TABLES_DIR)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    args = parser.parse_args(argv)
    run(tables_dir=args.tables_dir, out_dir=args.out_dir)


if __name__ == "__main__":
    main()
