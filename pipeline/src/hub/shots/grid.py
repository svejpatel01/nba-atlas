"""The xFG lookup grid: the browser never runs the model directly (PLAN.md —
"Ship a lookup table, not a model"). 1-foot cells across the offensive half
court, one grid per action family, quantized to a single byte per cell.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from hub.shots.features import ACTION_FAMILIES

CELL_SIZE_FT = 1.0
X_MIN, X_MAX = -25.0, 25.0  # court is 50 ft wide
Y_MIN, Y_MAX = 0.0, 47.0  # baseline to half court

# A "typical" in-game context for the click-anywhere grid, so it reflects a
# normal possession rather than a garbage-time heave or a last-second shot
# (PLAN.md: "evaluated at a fixed 'typical' period and seconds-remaining").
GRID_CONTEXT = {"period": 2, "seconds_left_in_period": 360}


def build_grid_cells() -> pd.DataFrame:
    """Cell centers on a 1-ft grid across the offensive half court —
    (X_MAX - X_MIN) * (Y_MAX - Y_MIN) = 50 * 47 = 2,350 cells, matching
    PLAN.md's estimate exactly.
    """
    xs = np.arange(X_MIN + CELL_SIZE_FT / 2, X_MAX, CELL_SIZE_FT)
    ys = np.arange(Y_MIN + CELL_SIZE_FT / 2, Y_MAX, CELL_SIZE_FT)
    xx, yy = np.meshgrid(xs, ys)
    x_ft = xx.ravel()
    y_ft = yy.ravel()
    distance = np.sqrt(x_ft**2 + y_ft**2)
    angle = np.degrees(np.arctan2(x_ft, y_ft))
    shot_value = classify_shot_value(x_ft, y_ft)
    return pd.DataFrame(
        {
            "x_ft": x_ft,
            "y_ft": y_ft,
            "shot_distance": distance,
            "angle": angle,
            "shot_value": shot_value,
        }
    )


def classify_shot_value(x_ft: np.ndarray, y_ft: np.ndarray) -> np.ndarray:
    """Real NBA 3-point geometry: a 22-ft straight line in the corners
    (out to 14 ft from the baseline, where the arc takes over), a 23.75-ft
    arc everywhere else.
    """
    distance = np.sqrt(x_ft**2 + y_ft**2)
    in_corner = (np.abs(x_ft) >= 22.0) & (y_ft <= 14.0)
    is_three = in_corner | (distance >= 23.75)
    return np.where(is_three, 3, 2)


def predict_grid_for_family(
    model, predict_proba_fn, cells: pd.DataFrame, action_family: str
) -> np.ndarray:
    X = cells.copy()
    X["action_family"] = action_family
    X["period"] = GRID_CONTEXT["period"]
    X["seconds_left_in_period"] = GRID_CONTEXT["seconds_left_in_period"]
    return predict_proba_fn(model, X)


def quantize(probabilities: np.ndarray) -> np.ndarray:
    """Linear 0-255 quantization. Max error is 1/510 ~= 0.2 percentage
    points from rounding, well inside the ~2-3pp calibration tolerance.
    """
    clipped = np.clip(probabilities, 0.0, 1.0)
    return np.round(clipped * 255).astype(np.uint8)


def dequantize(byte_values: np.ndarray) -> np.ndarray:
    return byte_values.astype(np.float64) / 255.0


def build_grid_binary(model, predict_proba_fn, cells: pd.DataFrame) -> tuple[bytes, dict]:
    """Builds the full concatenated grid (one block per action family, in
    ACTION_FAMILIES order) plus its metadata header.
    """
    blocks = []
    for family in ACTION_FAMILIES:
        probs = predict_grid_for_family(model, predict_proba_fn, cells, family)
        blocks.append(quantize(probs))
    data = b"".join(block.tobytes() for block in blocks)
    meta = {
        "family_order": ACTION_FAMILIES,
        "cell_size_ft": CELL_SIZE_FT,
        "x_min": X_MIN,
        "x_max": X_MAX,
        "y_min": Y_MIN,
        "y_max": Y_MAX,
        "n_cells_per_family": len(cells),
        "grid_context": GRID_CONTEXT,
    }
    return data, meta


def cell_index(x_ft: float, y_ft: float, n_x_cells: int) -> int:
    """Maps a court (x, y) in feet to its flat cell index, matching the
    row-major meshgrid order `build_grid_cells` produces (y varies slowest).
    """
    col = int(math.floor((x_ft - X_MIN) / CELL_SIZE_FT))
    row = int(math.floor((y_ft - Y_MIN) / CELL_SIZE_FT))
    return row * n_x_cells + col
