"""Shrinkage, within-season standardization, and group weighting for the
style map's feature table (docs/player-style-map-spec.md's "Preprocessing"
section).
"""

from __future__ import annotations

import polars as pl


def shrink_share(df: pl.DataFrame, share_col: str, volume_col: str, k: float) -> pl.Expr:
    """Blends a per-player share toward the league-average share for that
    column, weighted by `k` pseudo-observations: shrunk = (share*volume +
    k*league_share) / (volume + k). A low-volume player's extreme share gets
    pulled toward the league mean; a high-volume player's is barely moved.
    """
    league_share = (df[share_col] * df[volume_col]).sum() / df[volume_col].sum()
    return (
        (pl.col(share_col) * pl.col(volume_col) + k * league_share) / (pl.col(volume_col) + k)
    ).alias(share_col)


def apply_shrinkage(df: pl.DataFrame, shrink_specs: list[tuple[str, str, float]]) -> pl.DataFrame:
    """`shrink_specs` is a list of (share_col, volume_col, k) tuples."""
    exprs = [
        shrink_share(df, share_col, volume_col, k) for share_col, volume_col, k in shrink_specs
    ]
    return df.with_columns(exprs)


def standardize_within_season(df: pl.DataFrame, columns: list[str]) -> pl.DataFrame:
    """Z-scores each column against this DataFrame's own mean/std — call once
    per season so "shoots more 3s than peers" reflects that season's league
    distribution, not the whole history's. Zero-variance columns become 0
    (avoids inf from dividing by a zero std).
    """
    exprs = []
    for col in columns:
        mean = df[col].mean()
        std = df[col].std()
        if std is None or std == 0:
            exprs.append(pl.lit(0.0).alias(col))
        else:
            exprs.append(((pl.col(col) - mean) / std).alias(col))
    return df.with_columns(exprs)


def apply_group_weights(df: pl.DataFrame, feature_groups: dict[str, list[str]]) -> pl.DataFrame:
    """Divides each standardized feature by sqrt(size of its group), so a
    group with many columns (e.g. play types, 10 columns) doesn't dominate
    distances just because it has more columns than a group with 2.
    """
    exprs = []
    for _group, cols in feature_groups.items():
        weight = len(cols) ** 0.5
        for col in cols:
            if col in df.columns:
                exprs.append((pl.col(col) / weight).alias(col))
    return df.with_columns(exprs)
