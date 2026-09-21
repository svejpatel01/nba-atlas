import pandas as pd

from hub.shots import player_metrics


def test_shrink_pulls_low_volume_toward_mean():
    value = pd.Series([1.0, 0.0, 0.5])
    volume = pd.Series([4, 4, 400])  # league mean (volume-weighted) = 0.5
    out = player_metrics.shrink(value, volume, k=10.0)
    assert abs(out.iloc[0] - 0.5) < abs(1.0 - 0.5)  # low volume, pulled hard
    assert abs(out.iloc[2] - 0.5) < 0.01  # high volume, barely moves


def test_compute_zone_breakdown_per_zone_stats():
    df = pd.DataFrame(
        {
            "player_id": [1, 1, 1, 1],
            "shot_zone_basic": [
                "Restricted Area",
                "Restricted Area",
                "Mid-Range",
                "Left Corner 3",
            ],
            "shot_made_flag": [1, 0, 1, 0],
            "xfg": [0.6, 0.6, 0.4, 0.35],
        }
    )
    out = player_metrics.compute_zone_breakdown(df)
    row = out[out["player_id"] == 1].iloc[0]
    assert row["restricted_area_attempts"] == 2
    assert row["restricted_area_fg_pct"] == 0.5
    assert abs(row["restricted_area_xfg_pct"] - 0.6) < 1e-9
    assert row["midrange_attempts"] == 1
    assert row["corner3_attempts"] == 1


def test_compute_player_season_metrics_end_to_end():
    df = pd.DataFrame(
        {
            "player_id": [1, 1, 2, 2],
            "player_name": ["A", "A", "B", "B"],
            "shot_made_flag": [1, 0, 1, 1],
            "shot_value": [2, 2, 3, 3],
            "xfg": [0.5, 0.5, 0.35, 0.35],
            "shot_zone_basic": [
                "Restricted Area",
                "Mid-Range",
                "Above the Break 3",
                "Above the Break 3",
            ],
        }
    )
    out = player_metrics.compute_player_season_metrics(df, season="2023-24", shrinkage_k=1.0)
    assert set(out.columns) >= {
        "season",
        "player_id",
        "player_name",
        "attempts",
        "makes",
        "shot_selection",
        "shot_making",
        "fg_pct",
    }
    assert (out["season"] == "2023-24").all()
    player_a = out[out["player_id"] == 1].iloc[0]
    assert player_a["attempts"] == 2
    assert player_a["makes"] == 1
    assert player_a["fg_pct"] == 0.5
