"""Shot-quality model: a LightGBM classifier vs. a logistic-regression
baseline with distance/angle splines (docs/shot-quality-court-spec.md).
Split by season (never randomly — a season has a shared shooting
environment that would leak across a random split), train on every season
except the most recent completed one, validate on that one.
"""

from __future__ import annotations

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, SplineTransformer

from hub.shots.features import ACTION_FAMILIES

NUMERIC_FEATURES = ["shot_distance", "angle", "seconds_left_in_period", "period"]
CATEGORICAL_FEATURES = ["action_family", "shot_value"]
FEATURE_COLUMNS = [*NUMERIC_FEATURES, *CATEGORICAL_FEATURES]
TARGET = "shot_made_flag"


def time_split(shots: pd.DataFrame, validate_season: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    train = shots[shots["season"] != validate_season]
    validate = shots[shots["season"] == validate_season]
    return train, validate


def fit_logistic_baseline(train: pd.DataFrame) -> Pipeline:
    """Natural-spline terms on distance and angle (both highly nonlinear
    w.r.t. make probability), one-hot action_family and shot_value, raw
    period/seconds_left (their effect is closer to linear/monotone).
    """
    preprocessor = ColumnTransformer(
        [
            ("distance_spline", SplineTransformer(n_knots=6, degree=3), ["shot_distance"]),
            ("angle_spline", SplineTransformer(n_knots=6, degree=3), ["angle"]),
            ("passthrough", "passthrough", ["seconds_left_in_period", "period"]),
            ("onehot", OneHotEncoder(handle_unknown="ignore"), CATEGORICAL_FEATURES),
        ]
    )
    pipeline = Pipeline(
        [
            ("preprocess", preprocessor),
            ("clf", LogisticRegression(max_iter=5000)),
        ]
    )
    pipeline.fit(train[FEATURE_COLUMNS], train[TARGET])
    return pipeline


def fit_lightgbm(train: pd.DataFrame, **lgb_kwargs) -> lgb.LGBMClassifier:
    params = {
        "max_depth": 5,
        "n_estimators": 500,
        "learning_rate": 0.05,
        "colsample_bytree": 0.8,
        "random_state": 42,
        **lgb_kwargs,
    }
    model = lgb.LGBMClassifier(**params)
    X = train[FEATURE_COLUMNS].copy()
    X["action_family"] = X["action_family"].astype("category")
    X["shot_value"] = X["shot_value"].astype("category")
    model.fit(X, train[TARGET], categorical_feature=["action_family", "shot_value"])
    return model


def predict_proba(model, X: pd.DataFrame) -> np.ndarray:
    if isinstance(model, lgb.LGBMClassifier):
        X = X.copy()
        X["action_family"] = X["action_family"].astype("category")
        X["shot_value"] = X["shot_value"].astype("category")
    return model.predict_proba(X[FEATURE_COLUMNS])[:, 1]


def evaluate(model, validate: pd.DataFrame, n_calibration_bins: int = 10) -> dict:
    y_true = validate[TARGET].to_numpy()
    y_pred = predict_proba(model, validate)

    calibration = _calibration_curve(y_true, y_pred, n_calibration_bins)
    by_family = {}
    for family in ACTION_FAMILIES:
        mask = validate["action_family"] == family
        if mask.sum() < 30:
            continue
        by_family[family] = _calibration_curve(y_true[mask.to_numpy()], y_pred[mask.to_numpy()], 5)

    return {
        "log_loss": float(log_loss(y_true, y_pred)),
        "brier_score": float(brier_score_loss(y_true, y_pred)),
        "auc": float(roc_auc_score(y_true, y_pred)),
        "n_validated": int(len(y_true)),
        "calibration": calibration,
        "calibration_by_action_family": by_family,
    }


def _calibration_curve(y_true: np.ndarray, y_pred: np.ndarray, n_bins: int) -> list[dict]:
    bins = pd.qcut(y_pred, q=min(n_bins, len(np.unique(y_pred))), duplicates="drop")
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
