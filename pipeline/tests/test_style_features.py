import polars as pl

from hub.style import features


def test_build_shot_diet_features_computes_zone_shares():
    shots = pl.DataFrame(
        {
            "player_id": [1, 1, 1, 1, 2],
            "shot_zone_basic": [
                "Restricted Area",
                "Restricted Area",
                "Mid-Range",
                "Left Corner 3",
                "Above the Break 3",
            ],
        }
    )
    out = features.build_shot_diet_features(shots)
    row = out.filter(pl.col("player_id") == 1).row(0, named=True)
    assert row["total_fga"] == 4
    assert row["share_fga_restricted_area"] == 0.5
    assert row["share_fga_midrange"] == 0.25
    assert row["share_fga_corner3"] == 0.25
    assert row["share_fga_atb3"] == 0.0

    row2 = out.filter(pl.col("player_id") == 2).row(0, named=True)
    assert row2["share_fga_atb3"] == 1.0


def test_add_fta_per_fga():
    shot_diet = pl.DataFrame({"player_id": [1], "total_fga": [10]})
    base = pl.DataFrame({"PLAYER_ID": [1], "FTA": [5], "FGA": [10]})
    out = features.add_fta_per_fga(shot_diet, base)
    assert out["fta_per_fga"][0] == 0.5


def test_build_role_features():
    advanced = pl.DataFrame({"PLAYER_ID": [1], "USG_PCT": [0.25], "AST_PCT": [0.1]})
    out = features.build_role_features(advanced)
    row = out.row(0, named=True)
    assert row["usg_pct"] == 0.25
    assert row["ast_pct"] == 0.1
    assert row["ast_to_usg_ratio"] == 0.4


def test_build_rebound_defense_features_per100():
    base = pl.DataFrame({"PLAYER_ID": [1], "BLK": [10], "STL": [20], "PF": [50]})
    advanced = pl.DataFrame(
        {"PLAYER_ID": [1], "OREB_PCT": [0.05], "DREB_PCT": [0.15], "POSS": [1000]}
    )
    out = features.build_rebound_defense_features(base, advanced)
    row = out.row(0, named=True)
    assert row["blk_per100"] == 1.0
    assert row["stl_per100"] == 2.0
    assert row["pf_per100"] == 5.0
    assert row["oreb_pct"] == 0.05


def test_build_self_creation_features():
    scoring = pl.DataFrame({"PLAYER_ID": [1], "PCT_UAST_2PM": [0.3], "PCT_UAST_3PM": [0.1]})
    out = features.build_self_creation_features(scoring)
    assert out["pct_uast_2pm"][0] == 0.3


def test_build_ball_handling_features_per36():
    possessions = pl.DataFrame(
        {
            "PLAYER_ID": [1],
            "TOUCHES": [720],
            "AVG_SEC_PER_TOUCH": [3.5],
            "AVG_DRIB_PER_TOUCH": [2.1],
        }
    )
    drives = pl.DataFrame({"PLAYER_ID": [1], "DRIVES": [360]})
    passing = pl.DataFrame({"PLAYER_ID": [1], "PASSES_MADE": [720], "POTENTIAL_AST": [72]})
    base = pl.DataFrame({"PLAYER_ID": [1], "MIN": [720]})  # 20 * 36
    out = features.build_ball_handling_features(possessions, drives, passing, base)
    row = out.row(0, named=True)
    assert row["touches_per36"] == 36.0
    assert row["drives_per36"] == 18.0
    assert row["passes_per36"] == 36.0
    assert row["potential_ast_per36"] == 3.6
    assert row["sec_per_touch"] == 3.5


def test_build_shooting_mode_features_shares():
    base = pl.DataFrame({"PLAYER_ID": [1], "FGA": [100]})
    catch_shoot = pl.DataFrame({"PLAYER_ID": [1], "CATCH_SHOOT_FGA": [40]})
    pull_up = pl.DataFrame({"PLAYER_ID": [1], "PULL_UP_FGA": [20]})
    out = features.build_shooting_mode_features(catch_shoot, pull_up, base)
    row = out.row(0, named=True)
    assert row["catch_shoot_share_fga"] == 0.4
    assert row["pull_up_share_fga"] == 0.2


def test_build_touch_location_features_shares():
    possessions = pl.DataFrame(
        {
            "PLAYER_ID": [1],
            "TOUCHES": [100],
            "PAINT_TOUCHES": [20],
            "POST_TOUCHES": [10],
            "ELBOW_TOUCHES": [5],
        }
    )
    out = features.build_touch_location_features(possessions)
    row = out.row(0, named=True)
    assert row["paint_touch_share"] == 0.2
    assert row["post_touch_share"] == 0.1
    assert row["elbow_touch_share"] == 0.05


def test_build_play_type_features_shares_sum_to_one():
    play_types = {
        "Isolation": pl.DataFrame({"PLAYER_ID": [1, 2], "POSS": [50, 0]}),
        "Transition": pl.DataFrame({"PLAYER_ID": [1, 2], "POSS": [50, 100]}),
    }
    out = features.build_play_type_features(play_types)
    row1 = out.filter(pl.col("player_id") == 1).row(0, named=True)
    assert row1["playtype_Isolation"] == 0.5
    assert row1["playtype_Transition"] == 0.5
    row2 = out.filter(pl.col("player_id") == 2).row(0, named=True)
    assert row2["playtype_Isolation"] == 0.0
    assert row2["playtype_Transition"] == 1.0
