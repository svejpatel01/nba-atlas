"""Per-player-season shot selection and shot-making metrics
(docs/shot-quality-court-spec.md), computed from per-shot xFG over the full
log (not the coarser grid — the grid is only for the browser's
click-anywhere feature).
"""

from __future__ import annotations

import pandas as pd

ZONE_MAP = {
    "Restricted Area": "restricted_area",
    "In The Paint (Non-RA)": "paint_non_ra",
    "Mid-Range": "midrange",
    "Left Corner 3": "corner3",
    "Right Corner 3": "corner3",
    "Above the Break 3": "atb3",
}


def shrink(value: pd.Series, volume: pd.Series, k: float) -> pd.Series:
    """Shrinks each player's value toward the volume-weighted league mean by
    `k` pseudo-attempts — a 40-attempt player's extreme score gets pulled
    toward average; a 1,000-attempt player's barely moves.
    """
    league_mean = (value * volume).sum() / volume.sum()
    return (value * volume + k * league_mean) / (volume + k)


def compute_player_season_metrics(
    shots_with_xfg: pd.DataFrame, season: str, shrinkage_k: float = 150.0
) -> pd.DataFrame:
    """`shots_with_xfg` must have player_id, player_name, shot_made_flag,
    shot_value, xfg (per-shot predicted probability), shot_zone_basic.
    """
    df = shots_with_xfg.copy()
    df["points"] = df["shot_made_flag"] * df["shot_value"]
    df["expected_points"] = df["xfg"] * df["shot_value"]

    per_player = df.groupby(["player_id", "player_name"]).agg(
        attempts=("shot_made_flag", "size"),
        makes=("shot_made_flag", "sum"),
        avg_xfg=("xfg", "mean"),
        avg_points=("points", "mean"),
        avg_expected_points=("expected_points", "mean"),
    )
    per_player["raw_selection"] = per_player["avg_xfg"] - df["xfg"].mean()
    per_player["raw_making"] = per_player["avg_points"] - per_player["avg_expected_points"]
    per_player["shot_selection"] = shrink(
        per_player["raw_selection"], per_player["attempts"], shrinkage_k
    )
    per_player["shot_making"] = shrink(
        per_player["raw_making"], per_player["attempts"], shrinkage_k
    )
    per_player["fg_pct"] = per_player["makes"] / per_player["attempts"]
    per_player = per_player.drop(columns=["raw_selection", "raw_making"]).reset_index()
    per_player.insert(0, "season", season)

    zone_stats = compute_zone_breakdown(df)
    return per_player.merge(zone_stats, on=["player_id"], how="left")


def compute_zone_breakdown(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["zone"] = df["shot_zone_basic"].map(ZONE_MAP)
    df = df.dropna(subset=["zone"])
    grouped = df.groupby(["player_id", "zone"]).agg(
        attempts=("shot_made_flag", "size"),
        makes=("shot_made_flag", "sum"),
        xfg_sum=("xfg", "sum"),
    )
    grouped["fg_pct"] = grouped["makes"] / grouped["attempts"]
    grouped["xfg_pct"] = grouped["xfg_sum"] / grouped["attempts"]
    wide = grouped[["attempts", "fg_pct", "xfg_pct"]].unstack("zone")
    wide.columns = [f"{zone}_{metric}" for metric, zone in wide.columns]
    return wide.reset_index()
