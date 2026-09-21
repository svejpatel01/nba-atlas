"""Feature engineering for the shot-quality model
(docs/shot-quality-court-spec.md). Location (x, y) and distance come
straight from ShotChartDetail (tenths of a foot for x/y; distance already in
feet — verified live: row loc_x=76, loc_y=95 gives distance
sqrt(7.6^2+9.5^2)=12.2, matching the recorded shot_distance=12). Angle isn't
provided and is derived here.
"""

from __future__ import annotations

import polars as pl

# Checked in priority order (first match wins) against action_type, since
# names combine modifiers freely (e.g. "Turnaround Fadeaway Bank Jump Shot",
# "Running Alley Oop Dunk Shot") and the most specific/defining term should
# win over a generic one. Verified against all 53 distinct action_type
# values in the real shots table, not guessed.
ACTION_FAMILY_RULES: list[tuple[str, str]] = [
    ("Alley Oop", "alley_oop"),
    ("Tip", "tip"),
    ("Putback", "tip"),
    ("Dunk", "dunk"),
    ("Hook", "hook"),
    ("Floating", "floater"),
    ("Layup", "layup"),
    ("Finger Roll", "layup"),
    ("Step Back", "step_back"),
    ("Fadeaway", "fadeaway"),
    ("Turnaround", "fadeaway"),
    ("Pullup", "pull_up"),
    ("Pull-Up", "pull_up"),
]
DEFAULT_ACTION_FAMILY = "catch_and_shoot"  # plain "Jump Shot" and similar
ACTION_FAMILIES = [
    "layup",
    "dunk",
    "hook",
    "floater",
    "catch_and_shoot",
    "pull_up",
    "step_back",
    "fadeaway",
    "tip",
    "alley_oop",
]


def classify_action_family(action_type: str) -> str:
    for keyword, family in ACTION_FAMILY_RULES:
        if keyword.lower() in action_type.lower():
            return family
    return DEFAULT_ACTION_FAMILY


def build_shot_features(shots: pl.DataFrame) -> pl.DataFrame:
    """Drops the "No Shot" action_type (a small, genuine data artifact — 81
    rows league-wide) and adds the model's feature columns. `shots` should
    already be filtered to one season if that's the caller's intent; this
    doesn't filter by season itself.

    Deliberately does NOT drop shots at the exact (0, 0) origin: checked
    live, all ~35,000 such rows have shot_distance=0 too (consistent, not
    contradictory), so they're genuine point-blank rim attempts — likely a
    rounding convention introduced around 2020-21, not a data error. PLAN.md
    flagged the origin as a "sometimes indicates a data error" case;
    verified here that for this dataset it doesn't, and dropping them would
    have thrown out ~1.5% of real dunk/layup training data.

    Does drop the 341 rows (2015-16 and 2016-17 only — 0.015% of all shots)
    with entirely null loc_x/loc_y/shot_distance: unlike the origin rows,
    these have no coordinate data at all, a genuine early-API gap rather
    than a rounding convention.
    """
    clean = shots.filter(
        (pl.col("action_type") != "No Shot") & pl.col("shot_distance").is_not_null()
    )

    family_map = {at: classify_action_family(at) for at in clean["action_type"].unique().to_list()}
    seconds_left_in_period = pl.col("minutes_remaining") * 60 + pl.col("seconds_remaining")

    return clean.with_columns(
        [
            pl.col("action_type").replace(family_map).alias("action_family"),
            pl.when(pl.col("shot_type") == "3PT Field Goal")
            .then(3)
            .otherwise(2)
            .alias("shot_value"),
            seconds_left_in_period.alias("seconds_left_in_period"),
            ((seconds_left_in_period < 3) & (pl.col("shot_distance") > 30)).alias("is_heave"),
            (pl.col("loc_x") / 10.0).alias("x_ft"),
            (pl.col("loc_y") / 10.0).alias("y_ft"),
        ]
    ).with_columns(
        # atan2(x, y): 0 degrees is straight on (along the hoop centerline),
        # positive/negative toward each sideline.
        pl.arctan2("x_ft", "y_ft").degrees().alias("angle")
    )
