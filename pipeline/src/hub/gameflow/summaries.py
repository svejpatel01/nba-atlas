"""Per-game summaries computed once in the pipeline (docs/game-flow-spec.md):
a downsampled win-probability series, the top plays by win-probability
swing, an excitement index, and a comeback factor. Operates on one game's
already-scored event rows (a `win_prob` column — P(home wins) — must
already be present, added by whichever model was chosen in
`hub.gameflow.model`).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

MAX_SERIES_POINTS = 150
# Keep a point whenever win probability has moved more than this since the
# last kept point ("more resolution in high-volatility stretches")...
WP_CHANGE_THRESHOLD = 0.02
# ...or at least once every this many seconds regardless ("less in
# blowouts" — a lopsided game with no swings still gets roughly a
# point-per-minute shape instead of collapsing to just its first and last
# points).
MIN_SECONDS_BETWEEN_KEPT_POINTS = 60
TOP_PLAYS_N = 5


def downsample_series(
    seconds_elapsed: np.ndarray,
    win_prob: np.ndarray,
    home_score: np.ndarray,
    away_score: np.ndarray,
) -> list[list[float]]:
    """Returns `[seconds_elapsed, home_win_prob, home_score, away_score]`
    points, always including the first and last event, at most
    `MAX_SERIES_POINTS` points. Carrying score alongside win probability
    (a small deviation from the spec's 2-tuple data contract table) is what
    makes the UI spec's hover-scrubbing requirement possible — "shows the
    exact score and clock at that point, not just at annotated plays" needs
    score data at every scrubbed point, not just at `top_plays`. Cheap in
    practice: two small, slowly-changing integers per point, well inside
    the monthly-bundle size budget (measured: largest bundle gzips to
    ~175KB against a 1MB budget).
    """
    n = len(seconds_elapsed)
    if n == 0:
        return []
    if n == 1:
        return [
            [
                round(float(seconds_elapsed[0]), 1),
                round(float(win_prob[0]), 4),
                int(home_score[0]),
                int(away_score[0]),
            ]
        ]

    kept = {0, n - 1}
    last_kept_wp = win_prob[0]
    last_kept_t = seconds_elapsed[0]
    for i in range(1, n - 1):
        moved_enough = abs(win_prob[i] - last_kept_wp) > WP_CHANGE_THRESHOLD
        long_enough = (seconds_elapsed[i] - last_kept_t) >= MIN_SECONDS_BETWEEN_KEPT_POINTS
        if moved_enough or long_enough:
            kept.add(i)
            last_kept_wp = win_prob[i]
            last_kept_t = seconds_elapsed[i]

    kept_idx = sorted(kept)
    if len(kept_idx) > MAX_SERIES_POINTS:
        # Rare (a game volatile enough to trip the threshold constantly):
        # evenly subsample the kept indices rather than the raw events, so
        # the volatility-aware selection above still shapes which points
        # survive, and always keep the true first/last.
        step = (len(kept_idx) - 1) / (MAX_SERIES_POINTS - 1)
        sampled = {kept_idx[round(i * step)] for i in range(MAX_SERIES_POINTS)}
        kept_idx = sorted(sampled | {kept_idx[0], kept_idx[-1]})

    return [
        [
            round(float(seconds_elapsed[i]), 1),
            round(float(win_prob[i]), 4),
            int(home_score[i]),
            int(away_score[i]),
        ]
        for i in kept_idx
    ]


def compute_top_plays(game_df: pd.DataFrame, n: int = TOP_PLAYS_N) -> list[dict]:
    """`game_df` must be one game, chronologically ordered, with `win_prob`.
    The first event has no prior state to diff against and is excluded.
    """
    wp_change = game_df["win_prob"].diff()
    candidates = game_df.assign(wp_change=wp_change).iloc[1:]
    if candidates.empty:
        return []
    top = candidates.loc[candidates["wp_change"].abs().sort_values(ascending=False).index].head(n)
    top = top.sort_values("seconds_elapsed")
    return [
        {
            "description": row["description"] or "",
            "seconds_elapsed": round(float(row["seconds_elapsed"]), 1),
            "home_score": int(row["home_score"]),
            "away_score": int(row["away_score"]),
            "wp_change": round(float(row["wp_change"]), 4),
        }
        for _, row in top.iterrows()
    ]


def compute_excitement_index(game_df: pd.DataFrame) -> float:
    """Sum of absolute win-probability changes across the whole game, at
    full event resolution (not the downsampled series) — a simple,
    defensible measure of how much the outcome was in doubt throughout.
    """
    return float(game_df["win_prob"].diff().abs().sum())


def compute_comeback_factor(game_df: pd.DataFrame, home_win: bool) -> float:
    """The eventual winner's single lowest win probability at any point in
    the game — higher means a bigger comeback. `win_prob` is always
    P(home wins), so the away winner's own win probability is `1 - win_prob`.
    """
    win_prob = game_df["win_prob"].to_numpy()
    if home_win:
        return float(win_prob.min())
    return float((1.0 - win_prob).min())


def summarize_game(game_df: pd.DataFrame, home_win: bool) -> dict:
    """`game_df`: one game's scored event rows, chronologically ordered,
    with columns seconds_elapsed, win_prob, home_score, away_score,
    description.
    """
    series = downsample_series(
        game_df["seconds_elapsed"].to_numpy(),
        game_df["win_prob"].to_numpy(),
        game_df["home_score"].to_numpy(),
        game_df["away_score"].to_numpy(),
    )
    return {
        "series": series,
        "top_plays": compute_top_plays(game_df),
        "excitement": round(compute_excitement_index(game_df), 4),
        "comeback_factor": round(compute_comeback_factor(game_df, home_win), 4),
    }
