"""Fixed hex grid for the shot chart's hex-bin visualization
(docs/shot-quality-court-spec.md: "hex IDs computed in Python on a fixed
grid"). Flat-top axial hex coordinates — see redblobgames.com/grids/hexagons
for the math this follows. `HEX_SIZE_FT` is the hex's center-to-corner
radius; 2 ft gives a reasonably fine chart without too many near-empty
cells for a single player-season.
"""

from __future__ import annotations

import math

import pandas as pd

HEX_SIZE_FT = 2.0


def _axial_round(q: float, r: float) -> tuple[int, int]:
    """Rounds fractional axial coordinates to the nearest hex, via cube
    coordinates (q, r, s) with q+r+s=0 — rounding each independently can
    violate that constraint, so the component with the largest rounding
    error is recomputed from the other two.
    """
    x, z = q, r
    y = -x - z
    rx, ry, rz = round(x), round(y), round(z)
    dx, dy, dz = abs(rx - x), abs(ry - y), abs(rz - z)
    if dx > dy and dx > dz:
        rx = -ry - rz
    elif dy > dz:
        ry = -rx - rz
    else:
        rz = -rx - ry
    return int(rx), int(rz)


def to_axial(x_ft: float, y_ft: float, hex_size: float = HEX_SIZE_FT) -> tuple[int, int]:
    q = (2.0 / 3.0 * x_ft) / hex_size
    r = (-1.0 / 3.0 * x_ft + math.sqrt(3) / 3.0 * y_ft) / hex_size
    return _axial_round(q, r)


def hex_id(x_ft: float, y_ft: float, hex_size: float = HEX_SIZE_FT) -> str:
    q, r = to_axial(x_ft, y_ft, hex_size)
    return f"{q}_{r}"


def hex_center(hex_id_str: str, hex_size: float = HEX_SIZE_FT) -> tuple[float, float]:
    """Inverse of `hex_id`, for rendering: axial -> court (x, y) in feet."""
    q, r = (int(v) for v in hex_id_str.split("_"))
    x = hex_size * (3.0 / 2.0 * q)
    y = hex_size * (math.sqrt(3) / 2.0 * q + math.sqrt(3) * r)
    return x, y


def build_hex_aggregates(shots_with_xfg: pd.DataFrame, group_cols: list[str]) -> pd.DataFrame:
    """`shots_with_xfg` needs x_ft, y_ft, shot_made_flag, xfg, plus whatever
    `group_cols` are (e.g. ["player_id"] for a per-player file, or [] for a
    single league-average file).
    """
    df = shots_with_xfg.copy()
    df["hex_id"] = [hex_id(x, y) for x, y in zip(df["x_ft"], df["y_ft"], strict=True)]
    grouped = (
        df.groupby([*group_cols, "hex_id"])
        .agg(
            attempts=("shot_made_flag", "size"),
            makes=("shot_made_flag", "sum"),
            xfg_sum=("xfg", "sum"),
        )
        .reset_index()
    )
    return grouped
