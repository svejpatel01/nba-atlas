import numpy as np
import pandas as pd

from hub.shots import model


def _make_synthetic_shots(n=2000, seed=0) -> pd.DataFrame:
    """Shots where make probability decreases with distance — a model that
    learns anything sensible should show real discrimination (AUC > 0.5)
    and no confusion trying to fit action_family/shot_value as garbage.
    """
    rng = np.random.default_rng(seed)
    distance = rng.uniform(0, 30, n)
    angle = rng.uniform(-70, 70, n)
    action_family = rng.choice(["layup", "catch_and_shoot", "pull_up"], n)
    shot_value = np.where(distance > 22, 3, 2)
    period = rng.integers(1, 5, n)
    seconds_left = rng.uniform(0, 720, n)

    make_prob = np.clip(0.75 - distance / 40, 0.05, 0.95)
    made = rng.binomial(1, make_prob)

    return pd.DataFrame(
        {
            "season": rng.choice(["2022-23", "2023-24", "2024-25"], n),
            "shot_distance": distance,
            "angle": angle,
            "seconds_left_in_period": seconds_left,
            "period": period,
            "action_family": action_family,
            "shot_value": shot_value,
            "shot_made_flag": made,
        }
    )


def test_time_split_separates_by_season_only():
    df = _make_synthetic_shots(300)
    train, validate = model.time_split(df, "2024-25")
    assert (validate["season"] == "2024-25").all()
    assert (train["season"] != "2024-25").all()
    assert len(train) + len(validate) == len(df)


def test_fit_logistic_baseline_discriminates_by_distance():
    df = _make_synthetic_shots(4000)
    train, validate = model.time_split(df, "2024-25")
    fitted = model.fit_logistic_baseline(train)
    preds = model.predict_proba(fitted, validate)
    # Predictions should be lower for far shots than close ones, on average.
    close = preds[(validate["shot_distance"] < 5).to_numpy()]
    far = preds[(validate["shot_distance"] > 25).to_numpy()]
    assert close.mean() > far.mean()


def test_fit_lightgbm_discriminates_by_distance():
    df = _make_synthetic_shots(4000)
    train, validate = model.time_split(df, "2024-25")
    fitted = model.fit_lightgbm(train, n_estimators=50)
    preds = model.predict_proba(fitted, validate)
    close = preds[(validate["shot_distance"] < 5).to_numpy()]
    far = preds[(validate["shot_distance"] > 25).to_numpy()]
    assert close.mean() > far.mean()


def test_evaluate_returns_expected_shape():
    df = _make_synthetic_shots(4000)
    train, validate = model.time_split(df, "2024-25")
    fitted = model.fit_logistic_baseline(train)
    result = model.evaluate(fitted, validate, n_calibration_bins=5)
    assert 0 <= result["log_loss"]
    assert 0 <= result["brier_score"] <= 1
    assert 0.5 <= result["auc"] <= 1.0
    assert result["n_validated"] == len(validate)
    assert len(result["calibration"]) <= 5
    for bucket in result["calibration"]:
        assert set(bucket.keys()) == {"predicted", "actual", "n"}
    assert set(result["calibration_by_action_family"].keys()) <= {
        "layup",
        "catch_and_shoot",
        "pull_up",
    }


def test_evaluate_calibration_is_reasonably_close_on_a_well_specified_model():
    # A model trained and validated on the same distribution shape should be
    # roughly calibrated — this is a smoke test for the calibration-curve
    # math itself, not a claim about real-world model quality.
    df = _make_synthetic_shots(8000)
    train, validate = model.time_split(df, "2024-25")
    fitted = model.fit_logistic_baseline(train)
    result = model.evaluate(fitted, validate, n_calibration_bins=5)
    for bucket in result["calibration"]:
        assert abs(bucket["predicted"] - bucket["actual"]) < 0.1
