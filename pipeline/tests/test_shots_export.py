from hub.shots import export


def _eval_with_gap(gap: float) -> dict:
    return {"calibration": [{"predicted": 0.5, "actual": 0.5 + gap, "n": 100}]}


def test_choose_model_picks_logistic_when_close():
    baseline = _eval_with_gap(0.01)
    lgbm = _eval_with_gap(0.009)  # barely better, under the materiality bar
    assert export.choose_model(baseline, lgbm) == "logistic"


def test_choose_model_picks_lightgbm_when_materially_better():
    baseline = _eval_with_gap(0.02)
    lgbm = _eval_with_gap(0.001)  # clearly tighter calibration
    assert export.choose_model(baseline, lgbm) == "lightgbm"
