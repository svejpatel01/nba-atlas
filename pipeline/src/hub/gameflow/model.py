"""Win-probability model: logistic regression vs. LightGBM with a monotonic
constraint on margin (docs/game-flow-spec.md). Split by game (never by
event) into training and a held-out validation season, same discipline as
the shot-quality model — a random/event-level split would leak how a
specific game ends into that same game's other rows.
"""

from __future__ import annotations

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, log_loss

from hub.gameflow.features import FEATURE_COLUMNS, TARGET
from hub.gameflow.parse import REGULATION_PERIODS

# Non-overlapping partition of game time, coarsest-to-finest toward the end
# of regulation per the spec's example buckets, plus an explicit
# "final_2_min" bucket (called out separately: "this is where a model most
# commonly misbehaves") and its own "overtime" bucket, since
# `seconds_remaining` there is scoped to just the current OT period (see
# `parse.seconds_remaining_in_game`) and isn't comparable to a regulation
# quarter.
TIME_BUCKET_ORDER = ["q1", "q2", "q3", "q4_early", "final_2_min", "overtime"]
FINAL_2_MIN_BUCKET = "final_2_min"


def assign_time_bucket(period: np.ndarray, seconds_remaining: np.ndarray) -> np.ndarray:
    conditions = [
        period > REGULATION_PERIODS,
        seconds_remaining <= 120,
        seconds_remaining <= 720,
        seconds_remaining <= 1440,
        seconds_remaining <= 2160,
    ]
    choices = ["overtime", "final_2_min", "q4_early", "q3", "q2"]
    return np.select(conditions, choices, default="q1")


def time_split(df: pd.DataFrame, validate_season: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    train = df[df["season"] != validate_season]
    validate = df[df["season"] == validate_season]
    return train, validate


def fit_logistic(train: pd.DataFrame) -> LogisticRegression:
    """Deliberately just a dot product + sigmoid over raw feature values (no
    splines, no one-hot) — ship-ability as a few lines of client-side
    TypeScript is a design goal here, not an afterthought (PLAN.md).
    """
    model = LogisticRegression(max_iter=2000)
    model.fit(train[FEATURE_COLUMNS], train[TARGET])
    return model


def fit_lightgbm(train: pd.DataFrame, **lgb_kwargs) -> lgb.LGBMClassifier:
    """Monotonic constraint on margin and margin_time_decay (both
    margin-derived — constraining one without the other would let the
    model reintroduce non-monotonic quirks in margin's own effect through
    its time-decayed twin): win probability must not decrease as the home
    team's margin increases, holding other features fixed. Elo and
    possession are left unconstrained — the spec only calls out margin
    specifically, and unlike a blowout-margin/garbage-time interaction, a
    perverse Elo or possession effect is a real signal worth letting the
    model fit rather than assume away.
    """
    params = {
        "max_depth": 4,
        "n_estimators": 300,
        "learning_rate": 0.05,
        "random_state": 42,
        "monotone_constraints": [1, 1, 1, 0],
        **lgb_kwargs,
    }
    model = lgb.LGBMClassifier(**params)
    model.fit(train[FEATURE_COLUMNS], train[TARGET])
    return model


def predict_proba(model, X: pd.DataFrame) -> np.ndarray:
    return model.predict_proba(X[FEATURE_COLUMNS])[:, 1]


def _calibration_curve(y_true: np.ndarray, y_pred: np.ndarray, n_bins: int) -> list[dict]:
    n_bins = min(n_bins, len(np.unique(y_pred)))
    if n_bins < 1:
        return []
    bins = pd.qcut(y_pred, q=n_bins, duplicates="drop")
    df = pd.DataFrame({"y_true": y_true, "y_pred": y_pred, "bin": bins})
    grouped = df.groupby("bin", observed=True).agg(
        predicted=("y_pred", "mean"), actual=("y_true", "mean"), n=("y_true", "size")
    )
    return [
        {
            "predicted": round(float(r.predicted), 4),
            "actual": round(float(r.actual), 4),
            "n": int(r.n),
        }
        for r in grouped.itertuples()
    ]


# A calibration curve is "materially better" if its average absolute
# predicted-vs-actual gap is at least this much smaller — otherwise ship
# the simpler, client-portable logistic regression (spec: "Ship logistic
# regression unless LightGBM shows a clear calibration improvement,
# especially in the final-2-minutes bucket").
MATERIAL_CALIBRATION_GAP = 0.01


def _mean_calibration_gap(calibration: list[dict]) -> float:
    if not calibration:
        return 0.0
    return float(np.mean([abs(b["predicted"] - b["actual"]) for b in calibration]))


def choose_model(logistic_eval: dict, lgbm_eval: dict) -> str:
    """The final-2-minutes bucket gets its own (lower) bar, per the spec's
    explicit call-out that this is where a model most commonly misbehaves
    and where visitors will scrutinize the chart most closely — a small
    edge there matters more than the same-sized edge earlier in the game.
    """
    overall_gap_logistic = _mean_calibration_gap(logistic_eval["calibration"])
    overall_gap_lgbm = _mean_calibration_gap(lgbm_eval["calibration"])

    final_2_min_logistic = logistic_eval["calibration_by_time_bucket"].get(FINAL_2_MIN_BUCKET)
    final_2_min_lgbm = lgbm_eval["calibration_by_time_bucket"].get(FINAL_2_MIN_BUCKET)
    final_2_min_gap_logistic = (
        _mean_calibration_gap(final_2_min_logistic) if final_2_min_logistic else 0.0
    )
    final_2_min_gap_lgbm = _mean_calibration_gap(final_2_min_lgbm) if final_2_min_lgbm else 0.0

    overall_improvement = overall_gap_logistic - overall_gap_lgbm
    final_2_min_improvement = final_2_min_gap_logistic - final_2_min_gap_lgbm

    if (
        overall_improvement >= MATERIAL_CALIBRATION_GAP
        or final_2_min_improvement >= MATERIAL_CALIBRATION_GAP
    ):
        return "lightgbm"
    return "logistic"


def evaluate(model, validate: pd.DataFrame, n_calibration_bins: int = 10) -> dict:
    y_true = validate[TARGET].to_numpy()
    y_pred = predict_proba(model, validate)

    buckets = assign_time_bucket(
        validate["period"].to_numpy(), validate["seconds_remaining"].to_numpy()
    )
    by_bucket = {}
    for bucket in TIME_BUCKET_ORDER:
        mask = buckets == bucket
        if mask.sum() < 30:
            continue
        by_bucket[bucket] = _calibration_curve(
            y_true[mask], y_pred[mask], min(5, n_calibration_bins)
        )

    return {
        "log_loss": float(log_loss(y_true, y_pred)),
        "brier_score": float(brier_score_loss(y_true, y_pred)),
        "n_validated": int(len(y_true)),
        "calibration": _calibration_curve(y_true, y_pred, n_calibration_bins),
        "calibration_by_time_bucket": by_bucket,
    }
