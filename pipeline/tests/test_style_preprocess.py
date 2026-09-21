import math

import polars as pl

from hub.style import preprocess


def test_shrink_share_pulls_low_volume_toward_league_mean():
    df = pl.DataFrame(
        {
            "player_id": [1, 2, 3],
            "share": [1.0, 0.0, 0.5],  # league average share = 0.5 (equal volumes)
            "volume": [4, 4, 400],
        }
    )
    out = preprocess.apply_shrinkage(df, [("share", "volume", 10.0)])
    row1 = out.filter(pl.col("player_id") == 1).row(0, named=True)
    row3 = out.filter(pl.col("player_id") == 3).row(0, named=True)
    # Low-volume player (4 attempts) with an extreme share gets pulled hard toward 0.5.
    assert abs(row1["share"] - 0.5) < abs(1.0 - 0.5)
    # High-volume player (400 attempts) barely moves from their true share.
    assert abs(row3["share"] - 0.5) < 0.01


def test_standardize_within_season_zero_mean_unit_std():
    df = pl.DataFrame({"x": [1.0, 2.0, 3.0, 4.0, 5.0]})
    out = preprocess.standardize_within_season(df, ["x"])
    assert abs(out["x"].mean()) < 1e-9
    assert math.isclose(out["x"].std(), 1.0, rel_tol=1e-9)


def test_standardize_within_season_handles_zero_variance():
    df = pl.DataFrame({"x": [5.0, 5.0, 5.0]})
    out = preprocess.standardize_within_season(df, ["x"])
    assert out["x"].to_list() == [0.0, 0.0, 0.0]


def test_apply_group_weights_divides_by_sqrt_group_size():
    df = pl.DataFrame({"a": [4.0], "b": [4.0], "c": [4.0]})
    groups = {"pair": ["a", "b"], "single": ["c"]}
    out = preprocess.apply_group_weights(df, groups)
    assert math.isclose(out["a"][0], 4.0 / math.sqrt(2))
    assert math.isclose(out["b"][0], 4.0 / math.sqrt(2))
    assert math.isclose(out["c"][0], 4.0 / math.sqrt(1))
