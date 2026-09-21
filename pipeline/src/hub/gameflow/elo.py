"""FiveThirtyEight-style Elo ratings from final scores only (PLAN.md
Feature 4 / docs/game-flow-spec.md). Used as the pregame-strength feature
in the win-probability model, independent of any betting-line data.
"""

from __future__ import annotations

import polars as pl

BASE_RATING = 1500.0
DEFAULT_K = 20.0
# Elo points added to the home team's effective rating before computing win
# probability (applied at prediction time, not folded into the stored rating,
# so `postgame_*_elo` reflects team strength alone).
DEFAULT_HOME_ADVANTAGE = 75.0
# Fraction of the gap to BASE_RATING reverted at the start of each new
# season, so a rating doesn't fully carry over from a very good/bad prior
# year (spec: "typically 25-35% toward average").
DEFAULT_SEASON_REGRESSION = 0.30


def expected_win_prob(rating_diff: float) -> float:
    """Standard Elo expectation: probability the higher-rated side wins,
    given (effective home rating - away rating), home-advantage included.
    """
    return 1.0 / (1.0 + 10 ** (-rating_diff / 400.0))


def compute_elo(
    games: pl.DataFrame,
    k: float = DEFAULT_K,
    home_advantage: float = DEFAULT_HOME_ADVANTAGE,
    season_regression: float = DEFAULT_SEASON_REGRESSION,
) -> pl.DataFrame:
    """One row per game, processed in chronological order: each team's
    rating going into the game (pregame) and coming out of it (postgame).
    A team not yet seen starts at BASE_RATING. Regression toward the mean is
    applied once, to every team with an existing rating, at each season
    boundary (detected by `season` changing between consecutive games in
    date order) — including teams that don't play the season's first game.
    """
    games_sorted = games.sort(["game_date", "game_id"])
    ratings: dict[int, float] = {}
    current_season: str | None = None
    rows = []

    for g in games_sorted.iter_rows(named=True):
        season = g["season"]
        if current_season is not None and season != current_season:
            for team_id in ratings:
                ratings[team_id] = BASE_RATING + (1 - season_regression) * (
                    ratings[team_id] - BASE_RATING
                )
        current_season = season

        home_id, away_id = g["home_team_id"], g["away_team_id"]
        home_pre = ratings.get(home_id, BASE_RATING)
        away_pre = ratings.get(away_id, BASE_RATING)

        expected_home = expected_win_prob(home_pre + home_advantage - away_pre)
        home_won = 1.0 if g["home_score"] > g["away_score"] else 0.0
        delta = k * (home_won - expected_home)

        ratings[home_id] = home_pre + delta
        ratings[away_id] = away_pre - delta

        rows.append(
            {
                "game_id": g["game_id"],
                "season": season,
                "game_date": g["game_date"],
                "home_team_id": home_id,
                "away_team_id": away_id,
                "pregame_home_elo": home_pre,
                "pregame_away_elo": away_pre,
                "postgame_home_elo": ratings[home_id],
                "postgame_away_elo": ratings[away_id],
            }
        )

    return pl.DataFrame(rows)
