import math

import polars as pl
import pytest

from hub.gameflow import features

HOME = 1
AWAY = 2


def _events(game_id: str, rows: list[dict]) -> pl.DataFrame:
    defaults = {
        "game_id": game_id,
        "score_home": "",
        "score_away": "",
        "sub_type": "",
        "description": "",
    }
    return pl.DataFrame([{**defaults, "action_number": i, **r} for i, r in enumerate(rows, 1)])


def _games(rows: list[dict]) -> pl.DataFrame:
    return pl.DataFrame(rows)


def _elo(rows: list[dict]) -> pl.DataFrame:
    return pl.DataFrame(rows)


def _one_game_setup(home_score=100, away_score=90):
    game_id = "0000000001"
    events = _events(
        game_id,
        [
            {
                "period": 1,
                "clock": "PT06M00.00S",
                "team_id": HOME,
                "action_type": "Made Shot",
                "score_home": "4",
                "score_away": "2",
            },
        ],
    )
    games = _games(
        [
            {
                "game_id": game_id,
                "season": "2023-24",
                "home_team_id": HOME,
                "away_team_id": AWAY,
                "home_score": home_score,
                "away_score": away_score,
            }
        ]
    )
    elo = _elo(
        [
            {
                "game_id": game_id,
                "pregame_home_elo": 1600.0,
                "pregame_away_elo": 1500.0,
            }
        ]
    )
    return events, games, elo


def test_home_win_label_matches_final_score():
    events, games, elo = _one_game_setup(home_score=100, away_score=90)
    out = features.build_game_flow_features(events, games, elo)
    assert out[features.TARGET][0] == 1


def test_home_loss_label():
    events, games, elo = _one_game_setup(home_score=90, away_score=100)
    out = features.build_game_flow_features(events, games, elo)
    assert out[features.TARGET][0] == 0


def test_margin_time_decay_matches_formula():
    events, games, elo = _one_game_setup()
    out = features.build_game_flow_features(events, games, elo)
    row = out.row(0, named=True)
    # period 1, clock 6:00 left -> seconds_remaining = 3*720 + 360 = 2520
    expected_seconds_remaining = 3 * 720 + 360
    expected = row["margin"] / math.sqrt(expected_seconds_remaining + 1)
    assert row["margin_time_decay"] == pytest.approx(expected)


def test_elo_diff_time_scaled_at_start_of_game_is_full_strength():
    events = _events(
        "0000000001",
        [{"period": 1, "clock": "PT12M00.00S", "team_id": HOME, "action_type": "Made Shot"}],
    )
    games = _games(
        [
            {
                "game_id": "0000000001",
                "season": "2023-24",
                "home_team_id": HOME,
                "away_team_id": AWAY,
                "home_score": 100,
                "away_score": 90,
            }
        ]
    )
    elo = _elo(
        [{"game_id": "0000000001", "pregame_home_elo": 1600.0, "pregame_away_elo": 1500.0}]
    )
    out = features.build_game_flow_features(events, games, elo, home_advantage=0.0)
    # tip-off: seconds_remaining == full regulation length -> fraction == 1
    assert out["elo_diff_time_scaled"][0] == pytest.approx(100.0)


def test_elo_diff_time_scaled_fades_to_zero_at_end_of_regulation():
    events = _events(
        "0000000001",
        [{"period": 4, "clock": "PT00M00.00S", "team_id": HOME, "action_type": "Made Shot"}],
    )
    games = _games(
        [
            {
                "game_id": "0000000001",
                "season": "2023-24",
                "home_team_id": HOME,
                "away_team_id": AWAY,
                "home_score": 100,
                "away_score": 90,
            }
        ]
    )
    elo = _elo(
        [{"game_id": "0000000001", "pregame_home_elo": 1600.0, "pregame_away_elo": 1500.0}]
    )
    out = features.build_game_flow_features(events, games, elo, home_advantage=0.0)
    assert out["elo_diff_time_scaled"][0] == pytest.approx(0.0)


def test_possession_indicator_encoding():
    events = _events(
        "0000000001",
        [
            {"period": 1, "clock": "PT12M00.00S", "team_id": HOME, "action_type": "Turnover"},
            {"period": 1, "clock": "PT11M50.00S", "team_id": AWAY, "action_type": "Turnover"},
        ],
    )
    games = _games(
        [
            {
                "game_id": "0000000001",
                "season": "2023-24",
                "home_team_id": HOME,
                "away_team_id": AWAY,
                "home_score": 100,
                "away_score": 90,
            }
        ]
    )
    elo = _elo(
        [{"game_id": "0000000001", "pregame_home_elo": 1500.0, "pregame_away_elo": 1500.0}]
    )
    out = features.build_game_flow_features(events, games, elo)
    # HOME turns it over -> AWAY has the ball -> -1
    assert out["possession_indicator"][0] == -1
    # AWAY turns it over -> HOME has the ball -> +1
    assert out["possession_indicator"][1] == 1


def test_excludes_games_without_pbp_coverage():
    events, games, elo = _one_game_setup()
    extra_game = _games(
        [
            {
                "game_id": "9999999999",
                "season": "2023-24",
                "home_team_id": HOME,
                "away_team_id": AWAY,
                "home_score": 100,
                "away_score": 90,
            }
        ]
    )
    all_games = pl.concat([games, extra_game])
    out = features.build_game_flow_features(events, all_games, elo)
    assert set(out["game_id"].unique().to_list()) == {"0000000001"}


def test_excludes_games_without_elo_rating():
    events, games, _ = _one_game_setup()
    empty_elo = pl.DataFrame(
        schema={"game_id": pl.Utf8, "pregame_home_elo": pl.Float64, "pregame_away_elo": pl.Float64}
    )
    out = features.build_game_flow_features(events, games, empty_elo)
    assert out.height == 0
