"""Builds the player-season feature table for the style map
(docs/player-style-map-spec.md), one function per feature group. Each takes
the relevant raw nba_api DataFrame(s) for one season and returns a
`pl.DataFrame` keyed by `player_id`, so they're testable in isolation with
small fixtures and joined together by `build_feature_table`.
"""

from __future__ import annotations

import polars as pl

# Both tiers (Modern and All-eras) get these three groups.
SHOT_DIET_COLS = [
    "share_fga_restricted_area",
    "share_fga_paint_non_ra",
    "share_fga_midrange",
    "share_fga_corner3",
    "share_fga_atb3",
    "fta_per_fga",
]
ROLE_COLS = ["usg_pct", "ast_pct", "ast_to_usg_ratio"]
REBOUND_DEFENSE_COLS = ["oreb_pct", "dreb_pct", "blk_per100", "stl_per100", "pf_per100"]

# Modern tier only (needs tracking + play-type data, available 2015-16+).
SELF_CREATION_COLS = ["pct_uast_2pm", "pct_uast_3pm"]
BALL_HANDLING_COLS = [
    "touches_per36",
    "sec_per_touch",
    "dribbles_per_touch",
    "drives_per36",
    "passes_per36",
    "potential_ast_per36",
]
SHOOTING_MODE_COLS = ["catch_shoot_share_fga", "pull_up_share_fga"]
TOUCH_LOCATION_COLS = ["paint_touch_share", "post_touch_share", "elbow_touch_share"]

FEATURE_GROUPS: dict[str, list[str]] = {
    "shot_diet": SHOT_DIET_COLS,
    "role": ROLE_COLS,
    "rebound_defense": REBOUND_DEFENSE_COLS,
    "self_creation": SELF_CREATION_COLS,
    "ball_handling": BALL_HANDLING_COLS,
    "shooting_mode": SHOOTING_MODE_COLS,
    "touch_location": TOUCH_LOCATION_COLS,
    # One column per play type, filled in at call time in build_play_type_features.
}


def build_shot_diet_features(shots: pl.DataFrame) -> pl.DataFrame:
    """`shots` is one season's shot log (any players/teams). Shares are of
    total field goal attempts; heaves/backcourt shots count in the
    denominator but have no numerator bucket, so shares don't sum to 1.
    """
    per_player_total = shots.group_by("player_id").agg(pl.len().alias("total_fga"))
    zone_counts = (
        shots.with_columns(
            pl.when(pl.col("shot_zone_basic") == "Restricted Area")
            .then(pl.lit("restricted_area"))
            .when(pl.col("shot_zone_basic") == "In The Paint (Non-RA)")
            .then(pl.lit("paint_non_ra"))
            .when(pl.col("shot_zone_basic") == "Mid-Range")
            .then(pl.lit("midrange"))
            .when(pl.col("shot_zone_basic").is_in(["Left Corner 3", "Right Corner 3"]))
            .then(pl.lit("corner3"))
            .when(pl.col("shot_zone_basic") == "Above the Break 3")
            .then(pl.lit("atb3"))
            .otherwise(None)
            .alias("zone")
        )
        .filter(pl.col("zone").is_not_null())
        .group_by(["player_id", "zone"])
        .agg(pl.len().alias("n"))
        .pivot(on="zone", index="player_id", values="n")
        .fill_null(0)
    )
    out = per_player_total.join(zone_counts, on="player_id", how="left")
    for zone in ["restricted_area", "paint_non_ra", "midrange", "corner3", "atb3"]:
        if zone not in out.columns:
            out = out.with_columns(pl.lit(0).alias(zone))
    out = out.with_columns(
        [
            (pl.col(zone).fill_null(0) / pl.col("total_fga")).alias(f"share_fga_{zone}")
            for zone in ["restricted_area", "paint_non_ra", "midrange", "corner3", "atb3"]
        ]
    )
    return out.select(["player_id", "total_fga", *SHOT_DIET_COLS[:-1]])


def add_fta_per_fga(shot_diet: pl.DataFrame, base_stats: pl.DataFrame) -> pl.DataFrame:
    """`base_stats` is LeagueDashPlayerStats(Base): needs FTA, FGA."""
    fta_fga = base_stats.select(
        pl.col("PLAYER_ID").alias("player_id"),
        (pl.col("FTA") / pl.col("FGA").replace(0, None)).fill_null(0).alias("fta_per_fga"),
    )
    return shot_diet.join(fta_fga, on="player_id", how="left")


def build_role_features(advanced_stats: pl.DataFrame) -> pl.DataFrame:
    """`advanced_stats` is LeagueDashPlayerStats(Advanced): needs USG_PCT, AST_PCT."""
    return advanced_stats.select(
        pl.col("PLAYER_ID").alias("player_id"),
        pl.col("USG_PCT").alias("usg_pct"),
        pl.col("AST_PCT").alias("ast_pct"),
        (pl.col("AST_PCT") / pl.col("USG_PCT").replace(0, None))
        .fill_null(0)
        .alias("ast_to_usg_ratio"),
    )


def build_rebound_defense_features(
    base_stats: pl.DataFrame, advanced_stats: pl.DataFrame
) -> pl.DataFrame:
    """`base_stats` needs BLK, STL, PF; `advanced_stats` needs OREB_PCT, DREB_PCT, POSS."""
    poss = advanced_stats.select(pl.col("PLAYER_ID").alias("player_id"), "POSS")
    joined = base_stats.select(pl.col("PLAYER_ID").alias("player_id"), "BLK", "STL", "PF").join(
        poss, on="player_id", how="left"
    )
    per100 = pl.col("POSS").replace(0, None)
    reb_def = joined.select(
        "player_id",
        (pl.col("BLK") / per100 * 100).fill_null(0).alias("blk_per100"),
        (pl.col("STL") / per100 * 100).fill_null(0).alias("stl_per100"),
        (pl.col("PF") / per100 * 100).fill_null(0).alias("pf_per100"),
    )
    oreb_dreb = advanced_stats.select(
        pl.col("PLAYER_ID").alias("player_id"),
        pl.col("OREB_PCT").alias("oreb_pct"),
        pl.col("DREB_PCT").alias("dreb_pct"),
    )
    return oreb_dreb.join(reb_def, on="player_id", how="left")


def build_self_creation_features(scoring_stats: pl.DataFrame) -> pl.DataFrame:
    """`scoring_stats` is LeagueDashPlayerStats(Scoring): needs PCT_UAST_2PM, PCT_UAST_3PM."""
    return scoring_stats.select(
        pl.col("PLAYER_ID").alias("player_id"),
        pl.col("PCT_UAST_2PM").alias("pct_uast_2pm"),
        pl.col("PCT_UAST_3PM").alias("pct_uast_3pm"),
    )


def build_ball_handling_features(
    possessions: pl.DataFrame, drives: pl.DataFrame, passing: pl.DataFrame, base_stats: pl.DataFrame
) -> pl.DataFrame:
    """Per-36 rates use MIN from `base_stats`; `possessions`/`drives`/`passing`
    are LeagueDashPtStats with measure_type Possessions/Drives/Passing.
    """
    minutes = base_stats.select(pl.col("PLAYER_ID").alias("player_id"), "MIN")
    per36 = (pl.col("MIN").replace(0, None) / 36.0).alias("_36ths")

    poss_feats = (
        possessions.select(
            pl.col("PLAYER_ID").alias("player_id"),
            "TOUCHES",
            "AVG_SEC_PER_TOUCH",
            "AVG_DRIB_PER_TOUCH",
        )
        .join(minutes, on="player_id", how="left")
        .with_columns(per36)
        .select(
            "player_id",
            (pl.col("TOUCHES") / pl.col("_36ths")).fill_null(0).alias("touches_per36"),
            pl.col("AVG_SEC_PER_TOUCH").fill_null(0).alias("sec_per_touch"),
            pl.col("AVG_DRIB_PER_TOUCH").fill_null(0).alias("dribbles_per_touch"),
        )
    )
    drive_feats = (
        drives.select(pl.col("PLAYER_ID").alias("player_id"), "DRIVES")
        .join(minutes, on="player_id", how="left")
        .with_columns(per36)
        .select(
            "player_id", (pl.col("DRIVES") / pl.col("_36ths")).fill_null(0).alias("drives_per36")
        )
    )
    pass_feats = (
        passing.select(pl.col("PLAYER_ID").alias("player_id"), "PASSES_MADE", "POTENTIAL_AST")
        .join(minutes, on="player_id", how="left")
        .with_columns(per36)
        .select(
            "player_id",
            (pl.col("PASSES_MADE") / pl.col("_36ths")).fill_null(0).alias("passes_per36"),
            (pl.col("POTENTIAL_AST") / pl.col("_36ths")).fill_null(0).alias("potential_ast_per36"),
        )
    )
    return poss_feats.join(drive_feats, on="player_id", how="left").join(
        pass_feats, on="player_id", how="left"
    )


def build_shooting_mode_features(
    catch_shoot: pl.DataFrame, pull_up: pl.DataFrame, base_stats: pl.DataFrame
) -> pl.DataFrame:
    """Shares of total FGA (from `base_stats`) that were catch-and-shoot vs. pull-up."""
    fga = base_stats.select(pl.col("PLAYER_ID").alias("player_id"), "FGA")
    cs = catch_shoot.select(pl.col("PLAYER_ID").alias("player_id"), "CATCH_SHOOT_FGA")
    pu = pull_up.select(pl.col("PLAYER_ID").alias("player_id"), "PULL_UP_FGA")
    return (
        fga.join(cs, on="player_id", how="left")
        .join(pu, on="player_id", how="left")
        .select(
            "player_id",
            (pl.col("CATCH_SHOOT_FGA") / pl.col("FGA").replace(0, None))
            .fill_null(0)
            .alias("catch_shoot_share_fga"),
            (pl.col("PULL_UP_FGA") / pl.col("FGA").replace(0, None))
            .fill_null(0)
            .alias("pull_up_share_fga"),
        )
    )


def build_touch_location_features(possessions: pl.DataFrame) -> pl.DataFrame:
    """Shares of all touches spent in the paint/post/elbow."""
    total = pl.col("TOUCHES").replace(0, None)
    return possessions.select(
        pl.col("PLAYER_ID").alias("player_id"),
        (pl.col("PAINT_TOUCHES") / total).fill_null(0).alias("paint_touch_share"),
        (pl.col("POST_TOUCHES") / total).fill_null(0).alias("post_touch_share"),
        (pl.col("ELBOW_TOUCHES") / total).fill_null(0).alias("elbow_touch_share"),
    )


def build_play_type_features(play_types: dict[str, pl.DataFrame]) -> pl.DataFrame:
    """`play_types` maps play-type name -> that play type's SynergyPlayType
    DataFrame for the season. Returns share of total tracked possessions
    spent in each play type, one column per play type (`playtype_<name>`).

    Unlike every other endpoint here, SynergyPlayTypes gives a separate row
    per team for a traded player instead of one combined total (confirmed
    live) — summed by player_id first so a trade doesn't fan out into
    multiple rows once these get joined against the rest of the feature
    table.
    """
    per_type = []
    for name, df in play_types.items():
        per_type.append(
            df.group_by(pl.col("PLAYER_ID").alias("player_id")).agg(
                pl.col("POSS").sum().alias(f"poss_{name}")
            )
        )
    joined = per_type[0]
    for df in per_type[1:]:
        joined = joined.join(df, on="player_id", how="full", coalesce=True)
    poss_cols = [f"poss_{name}" for name in play_types]
    joined = joined.fill_null(0).with_columns(pl.sum_horizontal(poss_cols).alias("total_poss"))
    shares = joined.select(
        "player_id",
        *[
            (pl.col(f"poss_{name}") / pl.col("total_poss").replace(0, None))
            .fill_null(0)
            .alias(f"playtype_{name}")
            for name in play_types
        ],
    )
    return shares
