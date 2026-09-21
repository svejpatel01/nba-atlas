import numpy as np
import pandas as pd

from hub.gameflow import model


def test_assign_time_bucket_regulation():
    period = np.array([1, 2, 3, 4, 4])
    seconds_remaining = np.array([2500, 1800, 1000, 500, 60])
    buckets = model.assign_time_bucket(period, seconds_remaining)
    assert list(buckets) == ["q1", "q2", "q3", "q4_early", "final_2_min"]


def test_assign_time_bucket_overtime():
    period = np.array([5, 6])
    seconds_remaining = np.array([250, 30])
    buckets = model.assign_time_bucket(period, seconds_remaining)
    # Overtime always its own bucket, regardless of seconds_remaining value,
    # since OT's "remaining" is scoped to the current OT period only.
    assert list(buckets) == ["overtime", "overtime"]


def test_time_split_separates_by_season_not_row():
    df = pd.DataFrame(
        {
            "season": ["2023-24", "2023-24", "2024-25"],
            "game_id": ["a", "a", "b"],
        }
    )
    train, validate = model.time_split(df, "2024-25")
    assert set(train["season"]) == {"2023-24"}
    assert set(validate["season"]) == {"2024-25"}


def _synthetic_training_frame(n: int = 2000, seed: int = 0) -> pd.DataFrame:
    """Margin and elo strongly predict the outcome; possession weakly does.
    Built directly (not through features.py) so this test is fast and
    doesn't depend on real play-by-play data.
    """
    rng = np.random.default_rng(seed)
    margin = rng.uniform(-20, 20, n)
    margin_time_decay = margin / np.sqrt(rng.uniform(1, 2000, n) + 1)
    elo_diff_time_scaled = rng.uniform(-200, 200, n)
    possession_indicator = rng.integers(-1, 2, n)
    logit = 0.15 * margin + 0.01 * elo_diff_time_scaled + 0.05 * possession_indicator
    prob = 1 / (1 + np.exp(-logit))
    home_win = (rng.uniform(0, 1, n) < prob).astype(int)
    seasons = np.where(np.arange(n) < n // 2, "2023-24", "2024-25")
    return pd.DataFrame(
        {
            "margin": margin,
            "margin_time_decay": margin_time_decay,
            "elo_diff_time_scaled": elo_diff_time_scaled,
            "possession_indicator": possession_indicator,
            "home_win": home_win,
            "season": seasons,
            "period": rng.integers(1, 5, n),
            "seconds_remaining": rng.uniform(0, 2880, n),
        }
    )


def test_fit_logistic_predicts_higher_prob_for_bigger_home_margin():
    train = _synthetic_training_frame()
    fit = model.fit_logistic(train)
    small_lead = pd.DataFrame(
        {
            "margin": [2],
            "margin_time_decay": [0.5],
            "elo_diff_time_scaled": [0.0],
            "possession_indicator": [0],
        }
    )
    big_lead = pd.DataFrame(
        {
            "margin": [15],
            "margin_time_decay": [3.0],
            "elo_diff_time_scaled": [0.0],
            "possession_indicator": [0],
        }
    )
    p_small = model.predict_proba(fit, small_lead)[0]
    p_big = model.predict_proba(fit, big_lead)[0]
    assert p_big > p_small


def test_fit_lightgbm_respects_margin_monotonicity():
    train = _synthetic_training_frame()
    fit = model.fit_lightgbm(train, n_estimators=100)
    base = {
        "margin_time_decay": [1.0],
        "elo_diff_time_scaled": [0.0],
        "possession_indicator": [0],
    }
    margins = list(range(-20, 21, 2))
    probs = [
        model.predict_proba(fit, pd.DataFrame({"margin": [m], **base}))[0] for m in margins
    ]
    # non-decreasing as margin increases, holding everything else fixed
    assert all(later >= earlier - 1e-9 for earlier, later in zip(probs, probs[1:], strict=False))


def test_choose_model_ships_logistic_when_gaps_are_close():
    close_calibration = [{"predicted": 0.5, "actual": 0.51, "n": 100}]
    logistic_eval = {
        "calibration": close_calibration,
        "calibration_by_time_bucket": {"final_2_min": close_calibration},
    }
    lgbm_eval = {
        "calibration": [{"predicted": 0.5, "actual": 0.505, "n": 100}],
        "calibration_by_time_bucket": {
            "final_2_min": [{"predicted": 0.5, "actual": 0.505, "n": 100}]
        },
    }
    assert model.choose_model(logistic_eval, lgbm_eval) == "logistic"


def test_choose_model_ships_lightgbm_on_material_final_2_min_improvement():
    logistic_eval = {
        "calibration": [{"predicted": 0.5, "actual": 0.505, "n": 100}],
        "calibration_by_time_bucket": {
            "final_2_min": [{"predicted": 0.5, "actual": 0.6, "n": 100}]
        },
    }
    lgbm_eval = {
        "calibration": [{"predicted": 0.5, "actual": 0.505, "n": 100}],
        "calibration_by_time_bucket": {
            "final_2_min": [{"predicted": 0.5, "actual": 0.505, "n": 100}]
        },
    }
    assert model.choose_model(logistic_eval, lgbm_eval) == "lightgbm"


def test_evaluate_returns_expected_structure():
    train = _synthetic_training_frame()
    validate = train[train["season"] == "2024-25"]
    fit = model.fit_logistic(train)
    result = model.evaluate(fit, validate)
    assert 0 <= result["log_loss"]
    assert 0 <= result["brier_score"] <= 1
    assert result["n_validated"] == len(validate)
    assert len(result["calibration"]) > 0
    assert isinstance(result["calibration_by_time_bucket"], dict)
