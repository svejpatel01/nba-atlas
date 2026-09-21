import numpy as np
import pandas as pd
import pytest

from hub.gameflow import summaries


def _downsample(seconds, wp):
    """Wraps downsample_series with dummy monotonic scores, for tests that
    only care about the seconds/win-prob downsampling behavior.
    """
    n = len(seconds)
    home_score = np.arange(n)
    away_score = np.arange(n)
    return summaries.downsample_series(seconds, wp, home_score, away_score)


def test_downsample_series_always_keeps_first_and_last():
    seconds = np.linspace(0, 2880, 500)
    wp = np.full(500, 0.5)  # perfectly flat: nothing crosses the threshold
    series = _downsample(seconds, wp)
    assert series[0][0] == pytest.approx(0.0)
    assert series[-1][0] == pytest.approx(2880.0)


def test_downsample_series_includes_score_at_each_point():
    seconds = np.array([0, 10, 20])
    wp = np.array([0.5, 0.6, 0.7])
    home_score = np.array([0, 2, 4])
    away_score = np.array([0, 0, 1])
    series = summaries.downsample_series(seconds, wp, home_score, away_score)
    assert series[0] == [0.0, 0.5, 0, 0]
    assert series[-1] == [20.0, 0.7, 4, 1]


def test_downsample_series_caps_at_max_points():
    seconds = np.linspace(0, 2880, 5000)
    # Alternates every event: trips the WP_CHANGE_THRESHOLD constantly.
    wp = np.where(np.arange(5000) % 2 == 0, 0.1, 0.9)
    series = _downsample(seconds, wp)
    assert len(series) <= summaries.MAX_SERIES_POINTS


def test_downsample_series_keeps_a_point_at_least_every_minute_in_a_blowout():
    seconds = np.linspace(0, 2880, 300)
    event_spacing = seconds[1] - seconds[0]
    wp = np.full(300, 0.95)  # no swings at all
    series = _downsample(seconds, wp)
    gaps = np.diff([p[0] for p in series])
    # Events only arrive every `event_spacing` seconds, so the gap before the
    # "at least once a minute" check can next fire is bounded by
    # MIN_SECONDS_BETWEEN_KEPT_POINTS plus one event's worth of slack.
    assert gaps.max() <= summaries.MIN_SECONDS_BETWEEN_KEPT_POINTS + event_spacing


def test_downsample_series_keeps_a_point_on_a_big_swing():
    seconds = np.array([0, 10, 20, 30, 40])
    wp = np.array([0.5, 0.5, 0.9, 0.9, 0.9])  # jumps 0.4 between index 1 and 2
    series = _downsample(seconds, wp)
    kept_seconds = {p[0] for p in series}
    assert 20.0 in kept_seconds


def _game_df(win_probs, descriptions=None, home_scores=None, away_scores=None) -> pd.DataFrame:
    n = len(win_probs)
    return pd.DataFrame(
        {
            "seconds_elapsed": np.arange(n) * 10.0,
            "win_prob": win_probs,
            "home_score": home_scores or [0] * n,
            "away_score": away_scores or [0] * n,
            "description": descriptions or [f"play {i}" for i in range(n)],
        }
    )


def test_top_plays_excludes_first_event_and_sorts_chronologically():
    df = _game_df([0.5, 0.5, 0.9, 0.4, 0.6])
    top = summaries.compute_top_plays(df, n=5)
    # 4 diffable events (indices 1-4); chronological order preserved
    assert len(top) == 4
    assert [p["seconds_elapsed"] for p in top] == sorted(p["seconds_elapsed"] for p in top)


def test_top_plays_ranks_by_absolute_change():
    # Biggest single jump is index 2 (0.5 -> 0.95, +0.45)
    df = _game_df([0.5, 0.5, 0.95, 0.9, 0.89])
    top = summaries.compute_top_plays(df, n=1)
    assert len(top) == 1
    assert top[0]["seconds_elapsed"] == 20.0
    assert top[0]["wp_change"] == pytest.approx(0.45)


def test_excitement_index_sums_absolute_changes():
    df = _game_df([0.5, 0.6, 0.4, 0.4, 0.9])
    # |0.1| + |0.2| + |0| + |0.5| = 0.8
    assert summaries.compute_excitement_index(df) == pytest.approx(0.8)


def test_comeback_factor_home_winner_uses_own_min_win_prob():
    df = _game_df([0.5, 0.1, 0.05, 0.6, 0.9])
    assert summaries.compute_comeback_factor(df, home_win=True) == pytest.approx(0.05)


def test_comeback_factor_away_winner_uses_one_minus_win_prob():
    df = _game_df([0.5, 0.9, 0.95, 0.6, 0.1])
    # away's own win prob is 1 - home's; away's lowest point is home's peak (0.95)
    assert summaries.compute_comeback_factor(df, home_win=False) == pytest.approx(0.05)


def test_summarize_game_returns_expected_keys():
    df = _game_df(
        [0.5, 0.6, 0.9, 0.4, 0.6], home_scores=[0, 2, 4, 4, 6], away_scores=[0, 0, 0, 3, 3]
    )
    summary = summaries.summarize_game(df, home_win=True)
    assert set(summary.keys()) == {"series", "top_plays", "excitement", "comeback_factor"}
    assert len(summary["series"]) >= 2
    assert len(summary["top_plays"]) <= summaries.TOP_PLAYS_N
