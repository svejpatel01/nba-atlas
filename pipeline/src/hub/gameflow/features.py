"""Feature engineering for the win-probability model (docs/game-flow-spec.md).
Builds one training row per parsed play-by-play event: engineered features
at that game state, plus the game's eventual outcome as the label. Split by
game (never by event) downstream, same discipline as the shot-quality model
— any split by individual event would leak how a specific game ends into
that same game's training rows.
"""

from __future__ import annotations

import polars as pl

from hub.gameflow import parse
from hub.gameflow.elo import DEFAULT_HOME_ADVANTAGE

REGULATION_SECONDS = parse.REGULATION_PERIODS * parse.REGULATION_PERIOD_SECONDS

FEATURE_COLUMNS = ["margin", "margin_time_decay", "elo_diff_time_scaled", "possession_indicator"]
TARGET = "home_win"


def _single_game_features(
    states: pl.DataFrame,
    home_team_id: int,
    away_team_id: int,
    elo_diff_home_adjusted: float,
    home_win: int,
    season: str,
) -> pl.DataFrame:
    """`elo_diff_home_adjusted` is pregame (home elo + home-court advantage
    - away elo), computed once per game and scaled here by the fraction of
    game time remaining — its influence fades as the game itself provides
    more information, per PLAN.md's feature description. Time remaining is
    clipped to regulation length so a game already in overtime doesn't get
    a fraction outside [0, 1] (overtime's "remaining" is scoped to just the
    current OT period, per `parse.seconds_remaining_in_game`, which is
    already <= a regulation period and so naturally stays in range).
    """
    return states.with_columns(
        (pl.col("margin") / (pl.col("seconds_remaining").clip(lower_bound=0) + 1).sqrt()).alias(
            "margin_time_decay"
        ),
        (
            pl.lit(elo_diff_home_adjusted)
            * (
                pl.col("seconds_remaining").clip(lower_bound=0, upper_bound=REGULATION_SECONDS)
                / REGULATION_SECONDS
            )
        ).alias("elo_diff_time_scaled"),
        pl.when(pl.col("possession_team_id") == home_team_id)
        .then(1)
        .when(pl.col("possession_team_id") == away_team_id)
        .then(-1)
        .otherwise(0)
        .alias("possession_indicator"),
        pl.lit(home_win).alias(TARGET),
        pl.lit(season).alias("season"),
        pl.lit(home_team_id).alias("home_team_id"),
        pl.lit(away_team_id).alias("away_team_id"),
    )


def build_game_flow_features(
    pbp_events: pl.DataFrame,
    games: pl.DataFrame,
    elo_ratings: pl.DataFrame,
    home_advantage: float = DEFAULT_HOME_ADVANTAGE,
) -> pl.DataFrame:
    """One row per (game_id, event), scoped to games that have both PBP
    coverage and an Elo rating (the small number of games missing from
    `games.parquet` per the malformed-MATCHUP gap in docs/decisions.md
    naturally have neither, so an inner join excludes them rather than
    needing special-case handling here).

    `elo_ratings` must come from `elo.compute_elo` run over `games`' full
    history — not just the PBP-covered seasons — so pregame ratings
    entering a 2023-24 game already reflect real team strength built up
    over prior seasons, not a fresh BASE_RATING start.
    """
    outcomes = games.select(
        "game_id",
        "season",
        "home_team_id",
        "away_team_id",
        (pl.col("home_score") > pl.col("away_score")).cast(pl.Int8).alias(TARGET),
    )
    pregame_elo = elo_ratings.select("game_id", "pregame_home_elo", "pregame_away_elo")

    scoped_games = (
        outcomes.join(pbp_events.select("game_id").unique(), on="game_id", how="inner")
        .join(pregame_elo, on="game_id", how="inner")
        .sort("game_id")
    )

    if scoped_games.height == 0:
        return pl.DataFrame(
            schema={
                "game_id": pl.Utf8,
                "action_number": pl.Int64,
                "period": pl.Int64,
                "seconds_left_in_period": pl.Float64,
                "seconds_elapsed": pl.Float64,
                "seconds_remaining": pl.Float64,
                "home_score": pl.Int64,
                "away_score": pl.Int64,
                "margin": pl.Int64,
                "possession_team_id": pl.Int64,
                "action_type": pl.Utf8,
                "description": pl.Utf8,
                "margin_time_decay": pl.Float64,
                "elo_diff_time_scaled": pl.Float64,
                "possession_indicator": pl.Int32,
                TARGET: pl.Int8,
                "season": pl.Utf8,
                "home_team_id": pl.Int64,
                "away_team_id": pl.Int64,
            }
        )

    parts = []
    for g in scoped_games.iter_rows(named=True):
        game_events = pbp_events.filter(pl.col("game_id") == g["game_id"])
        states = parse.build_game_states(game_events, g["home_team_id"], g["away_team_id"])
        elo_diff_home_adjusted = g["pregame_home_elo"] + home_advantage - g["pregame_away_elo"]
        parts.append(
            _single_game_features(
                states,
                g["home_team_id"],
                g["away_team_id"],
                elo_diff_home_adjusted,
                g[TARGET],
                g["season"],
            )
        )
    return pl.concat(parts, how="diagonal_relaxed")
