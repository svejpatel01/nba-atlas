import pandas as pd

from hub.shots import hex as hexmod


def test_axial_round_exact_integers_stay_put():
    assert hexmod._axial_round(3.0, -1.0) == (3, -1)


def test_to_axial_origin_is_hex_zero_zero():
    assert hexmod.to_axial(0.0, 0.0) == (0, 0)


def test_hex_id_is_stable_for_nearby_points():
    # Start from a verified hex center (not an arbitrary point, which could
    # happen to sit near a cell boundary) and perturb by well under the
    # hex's inradius (size * sqrt(3)/2 ~= 1.73 ft for HEX_SIZE_FT=2) — that
    # small a nudge should never cross into a neighboring hex.
    cx, cy = hexmod.hex_center(hexmod.hex_id(10.0, 10.0))
    assert hexmod.hex_id(cx, cy) == hexmod.hex_id(cx + 0.3, cy + 0.2)


def test_hex_id_differs_for_far_apart_points():
    assert hexmod.hex_id(0.0, 0.0) != hexmod.hex_id(20.0, 20.0)


def test_hex_center_round_trips_reasonably():
    x, y = 12.0, 18.0
    hid = hexmod.hex_id(x, y)
    cx, cy = hexmod.hex_center(hid)
    # The recovered hex center should be within one hex diameter of the
    # original point, not necessarily exactly equal.
    assert abs(cx - x) < hexmod.HEX_SIZE_FT * 2
    assert abs(cy - y) < hexmod.HEX_SIZE_FT * 2


def test_build_hex_aggregates_counts_attempts_and_makes():
    df = pd.DataFrame(
        {
            "player_id": [1, 1, 1, 2],
            "x_ft": [10.0, 10.1, 20.0, 10.0],
            "y_ft": [10.0, 10.1, 20.0, 10.0],
            "shot_made_flag": [1, 0, 1, 1],
            "xfg": [0.5, 0.5, 0.4, 0.6],
        }
    )
    out = hexmod.build_hex_aggregates(df, group_cols=["player_id"])
    player1_hex_a = out[(out["player_id"] == 1) & (out["hex_id"] == hexmod.hex_id(10.0, 10.0))]
    assert player1_hex_a["attempts"].iloc[0] == 2
    assert player1_hex_a["makes"].iloc[0] == 1
    assert abs(player1_hex_a["xfg_sum"].iloc[0] - 1.0) < 1e-9

    player2_rows = out[out["player_id"] == 2]
    assert len(player2_rows) == 1
    assert player2_rows["attempts"].iloc[0] == 1


def test_build_hex_aggregates_league_average_ignores_group_cols():
    df = pd.DataFrame(
        {
            "x_ft": [10.0, 10.1],
            "y_ft": [10.0, 10.1],
            "shot_made_flag": [1, 1],
            "xfg": [0.5, 0.5],
        }
    )
    out = hexmod.build_hex_aggregates(df, group_cols=[])
    assert len(out) == 1
    assert out["attempts"].iloc[0] == 2
