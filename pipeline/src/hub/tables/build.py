"""Transforms raw nba_api DataFrames into the canonical tables.

Every function here is a pure transform (DataFrame(s) in, DataFrame out), so
it's testable with small fixtures with no network or disk dependency. The
orchestration that calls these with real fetched data lives in
`hub.tables.pipeline`.
"""

from __future__ import annotations

import polars as pl


def build_teams(raw_teams: pl.DataFrame) -> pl.DataFrame:
    """From hub.fetch.nba.get_teams(); just a rename to canonical column names."""
    return raw_teams.rename(
        {
            "id": "team_id",
            "full_name": "full_name",
            "abbreviation": "abbreviation",
            "nickname": "nickname",
            "city": "city",
            "state": "state",
            "year_founded": "year_founded",
        }
    ).select(["team_id", "full_name", "abbreviation", "nickname", "city", "state", "year_founded"])


def build_players(common_all_players: pl.DataFrame, bios: pl.DataFrame) -> pl.DataFrame:
    """`players` = full historical roster (CommonAllPlayers) enriched with bio
    fields from per-player CommonPlayerInfo calls (see hub.fetch.nba.fetch_player_bio).
    `bios` is typically scoped to only players who appear in player_game_logs,
    so players outside that scope get null bio fields.
    """
    base = common_all_players.select(
        [
            pl.col("PERSON_ID").alias("player_id"),
            pl.col("DISPLAY_FIRST_LAST").alias("name"),
            pl.col("FROM_YEAR").cast(pl.Int32).alias("from_year"),
            pl.col("TO_YEAR").cast(pl.Int32).alias("to_year"),
        ]
    )
    bio = bios.select(
        [
            pl.col("PERSON_ID").alias("player_id"),
            pl.col("POSITION").alias("position"),
            pl.col("HEIGHT").alias("height"),
            pl.col("WEIGHT").alias("weight"),
            pl.col("SCHOOL").alias("college"),
            pl.col("COUNTRY").alias("country"),
            pl.col("DRAFT_YEAR").alias("draft_year"),
            pl.col("BIRTHDATE").alias("birthdate"),
        ]
    ).unique(subset=["player_id"])
    return base.join(bio, on="player_id", how="left")


def build_games(team_game_logs: pl.DataFrame) -> pl.DataFrame:
    """Pairs the two team-game_log rows for each game_id into one row with
    home/away teams and scores, using MATCHUP's "vs." (home) / "@" (away).
    """
    with_home_flag = team_game_logs.with_columns(
        pl.col("matchup").str.contains(" vs. ").alias("is_home")
    )
    home = with_home_flag.filter(pl.col("is_home")).select(
        [
            pl.col("game_id"),
            pl.col("season"),
            pl.col("game_date"),
            pl.col("team_id").alias("home_team_id"),
            pl.col("pts").alias("home_score"),
            pl.col("wl").alias("home_wl"),
        ]
    )
    away = with_home_flag.filter(~pl.col("is_home")).select(
        [
            pl.col("game_id"),
            pl.col("team_id").alias("away_team_id"),
            pl.col("pts").alias("away_score"),
        ]
    )
    return home.join(away, on="game_id", how="inner").sort("game_date")


def build_player_game_logs(raw: pl.DataFrame, season: str) -> pl.DataFrame:
    return raw.rename({c: c.lower() for c in raw.columns}).with_columns(
        pl.lit(season).alias("season")
    )


def build_team_game_logs(raw: pl.DataFrame, season: str) -> pl.DataFrame:
    return raw.rename({c: c.lower() for c in raw.columns}).with_columns(
        pl.lit(season).alias("season")
    )


def build_player_seasons(
    base_stats: pl.DataFrame, advanced_stats: pl.DataFrame, season: str
) -> pl.DataFrame:
    """Joins Base + Advanced LeagueDashPlayerStats (Totals) on player_id+team_id."""
    base = base_stats.select(
        [
            pl.col("PLAYER_ID").alias("player_id"),
            pl.col("PLAYER_NAME").alias("player_name"),
            pl.col("TEAM_ID").alias("team_id"),
            pl.col("GP").alias("gp"),
            pl.col("MIN").alias("min"),
            pl.col("PTS").alias("pts"),
            pl.col("REB").alias("reb"),
            pl.col("AST").alias("ast"),
            pl.col("STL").alias("stl"),
            pl.col("BLK").alias("blk"),
            pl.col("TOV").alias("tov"),
            pl.col("FG_PCT").alias("fg_pct"),
            pl.col("FG3_PCT").alias("fg3_pct"),
            pl.col("FT_PCT").alias("ft_pct"),
        ]
    )
    advanced = advanced_stats.select(
        [
            pl.col("PLAYER_ID").alias("player_id"),
            pl.col("TEAM_ID").alias("team_id"),
            pl.col("USG_PCT").alias("usg_pct"),
            pl.col("TS_PCT").alias("ts_pct"),
            pl.col("AST_PCT").alias("ast_pct"),
            pl.col("OREB_PCT").alias("oreb_pct"),
            pl.col("DREB_PCT").alias("dreb_pct"),
            pl.col("PIE").alias("pie"),
        ]
    )
    return base.join(advanced, on=["player_id", "team_id"], how="left").with_columns(
        pl.lit(season).alias("season")
    )


def build_shots(raw: pl.DataFrame, season: str) -> pl.DataFrame:
    return raw.rename({c: c.lower() for c in raw.columns}).with_columns(
        pl.lit(season).alias("season")
    )


def build_pbp_events(raw: pl.DataFrame) -> pl.DataFrame:
    """Renames PlayByPlayV3's camelCase columns to snake_case. `raw` should
    already have a `game_id` column matching every other table (PlayByPlayV3's
    own `gameId` column is included and kept for redundancy/validation).
    """
    return raw.rename({c: _camel_to_snake(c) for c in raw.columns})


def _camel_to_snake(name: str) -> str:
    out = []
    for i, ch in enumerate(name):
        if ch.isupper() and i > 0:
            out.append("_")
        out.append(ch.lower())
    return "".join(out)
