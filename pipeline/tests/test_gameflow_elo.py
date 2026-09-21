import datetime

import polars as pl
import pytest

from hub.gameflow import elo


def _games(rows: list[dict]) -> pl.DataFrame:
    return pl.DataFrame(rows)


def test_expected_win_prob_symmetric_at_zero_diff():
    assert elo.expected_win_prob(0.0) == pytest.approx(0.5)


def test_expected_win_prob_favors_higher_rating():
    assert elo.expected_win_prob(400.0) > 0.9
    assert elo.expected_win_prob(-400.0) < 0.1


def test_new_teams_start_at_base_rating():
    games = _games(
        [
            {
                "game_id": "1",
                "season": "2015-16",
                "game_date": datetime.date(2015, 10, 27),
                "home_team_id": 1,
                "home_score": 100,
                "away_team_id": 2,
                "away_score": 90,
            }
        ]
    )
    out = elo.compute_elo(games)
    row = out.row(0, named=True)
    assert row["pregame_home_elo"] == elo.BASE_RATING
    assert row["pregame_away_elo"] == elo.BASE_RATING


def test_rating_change_is_zero_sum():
    games = _games(
        [
            {
                "game_id": "1",
                "season": "2015-16",
                "game_date": datetime.date(2015, 10, 27),
                "home_team_id": 1,
                "home_score": 100,
                "away_team_id": 2,
                "away_score": 90,
            }
        ]
    )
    row = elo.compute_elo(games).row(0, named=True)
    home_delta = row["postgame_home_elo"] - row["pregame_home_elo"]
    away_delta = row["postgame_away_elo"] - row["pregame_away_elo"]
    assert home_delta == pytest.approx(-away_delta)


def test_winner_gains_rating_loser_loses_it():
    games = _games(
        [
            {
                "game_id": "1",
                "season": "2015-16",
                "game_date": datetime.date(2015, 10, 27),
                "home_team_id": 1,
                "home_score": 100,
                "away_team_id": 2,
                "away_score": 90,
            }
        ]
    )
    row = elo.compute_elo(games).row(0, named=True)
    assert row["postgame_home_elo"] > row["pregame_home_elo"]
    assert row["postgame_away_elo"] < row["pregame_away_elo"]


def test_ratings_carry_forward_within_a_season():
    games = _games(
        [
            {
                "game_id": "1",
                "season": "2015-16",
                "game_date": datetime.date(2015, 10, 27),
                "home_team_id": 1,
                "home_score": 100,
                "away_team_id": 2,
                "away_score": 90,
            },
            {
                "game_id": "2",
                "season": "2015-16",
                "game_date": datetime.date(2015, 10, 30),
                "home_team_id": 1,
                "home_score": 100,
                "away_team_id": 3,
                "away_score": 90,
            },
        ]
    )
    out = elo.compute_elo(games)
    game1_postgame_home = out.row(0, named=True)["postgame_home_elo"]
    game2_pregame_home = out.row(1, named=True)["pregame_home_elo"]
    assert game1_postgame_home == pytest.approx(game2_pregame_home)


def test_season_boundary_regresses_toward_base_rating():
    games = _games(
        [
            {
                "game_id": "1",
                "season": "2015-16",
                "game_date": datetime.date(2015, 10, 27),
                "home_team_id": 1,
                "home_score": 130,
                "away_team_id": 2,
                "away_score": 90,
            },
            {
                "game_id": "2",
                "season": "2016-17",
                "game_date": datetime.date(2016, 10, 26),
                "home_team_id": 1,
                "home_score": 100,
                "away_team_id": 3,
                "away_score": 99,
            },
        ]
    )
    out = elo.compute_elo(games, season_regression=0.3)
    end_of_2015_16 = out.row(0, named=True)["postgame_home_elo"]
    start_of_2016_17 = out.row(1, named=True)["pregame_home_elo"]
    assert end_of_2015_16 > elo.BASE_RATING
    assert start_of_2016_17 < end_of_2015_16
    assert start_of_2016_17 > elo.BASE_RATING
    expected = elo.BASE_RATING + 0.7 * (end_of_2015_16 - elo.BASE_RATING)
    assert start_of_2016_17 == pytest.approx(expected)


def test_home_advantage_shifts_expected_win_prob_at_equal_ratings():
    games = _games(
        [
            {
                "game_id": "1",
                "season": "2015-16",
                "game_date": datetime.date(2015, 10, 27),
                "home_team_id": 1,
                "home_score": 100,
                "away_team_id": 2,
                "away_score": 99,
            }
        ]
    )
    with_advantage = elo.compute_elo(games, home_advantage=100.0).row(0, named=True)
    no_advantage = elo.compute_elo(games, home_advantage=0.0).row(0, named=True)
    # Same result (barely a home win) but a bigger home-court cushion means
    # the win was *more* expected, so the home team's rating gain is smaller.
    home_gain_with_advantage = (
        with_advantage["postgame_home_elo"] - with_advantage["pregame_home_elo"]
    )
    home_gain_no_advantage = no_advantage["postgame_home_elo"] - no_advantage["pregame_home_elo"]
    assert home_gain_with_advantage < home_gain_no_advantage
