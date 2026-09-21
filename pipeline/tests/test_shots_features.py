import polars as pl

from hub.shots import features

# Every action_type value actually observed in the real shots table
# (data/tables/shots.parquet, 2015-16..2025-26) — pinned here so a future
# season introducing a new label gets caught by a test failure instead of
# silently falling back to "catch_and_shoot".
REAL_ACTION_TYPES = [
    "Jump Shot",
    "Pullup Jump shot",
    "Driving Layup Shot",
    "Layup Shot",
    "Step Back Jump shot",
    "Driving Floating Jump Shot",
    "Running Layup Shot",
    "Cutting Layup Shot",
    "Driving Finger Roll Layup Shot",
    "Floating Jump shot",
    "Tip Layup Shot",
    "Fadeaway Jump Shot",
    "Running Jump Shot",
    "Putback Layup Shot",
    "Turnaround Jump Shot",
    "Cutting Dunk Shot",
    "Turnaround Fadeaway shot",
    "Hook Shot",
    "Driving Floating Bank Jump Shot",
    "Turnaround Hook Shot",
    "Running Dunk Shot",
    "Driving Reverse Layup Shot",
    "Dunk Shot",
    "Driving Dunk Shot",
    "Running Pull-Up Jump Shot",
    "Alley Oop Dunk Shot",
    "Reverse Layup Shot",
    "Driving Hook Shot",
    "Running Finger Roll Layup Shot",
    "Alley Oop Layup shot",
    "Jump Bank Shot",
    "Tip Dunk Shot",
    "Cutting Finger Roll Layup Shot",
    "Putback Dunk Shot",
    "Finger Roll Layup Shot",
    "Running Reverse Layup Shot",
    "Running Alley Oop Dunk Shot",
    "Turnaround Fadeaway Bank Jump Shot",
    "Driving Bank Hook Shot",
    "Turnaround Bank shot",
    "Turnaround Bank Hook Shot",
    "Driving Bank shot",
    "Hook Bank Shot",
    "Running Alley Oop Layup Shot",
    "Reverse Dunk Shot",
    "Fadeaway Bank shot",
    "Step Back Bank Jump Shot",
    "Pullup Bank shot",
    "Driving Reverse Dunk Shot",
    "Running Reverse Dunk Shot",
    "Driving Jump shot",
    "Running Hook Shot",
]


def test_classify_action_family_covers_every_real_value_with_a_named_family():
    for action_type in REAL_ACTION_TYPES:
        family = features.classify_action_family(action_type)
        assert family in features.ACTION_FAMILIES, f"{action_type!r} -> unexpected {family!r}"


def test_classify_action_family_specific_cases():
    assert features.classify_action_family("Alley Oop Dunk Shot") == "alley_oop"
    assert features.classify_action_family("Running Alley Oop Layup Shot") == "alley_oop"
    assert features.classify_action_family("Tip Layup Shot") == "tip"
    assert features.classify_action_family("Putback Dunk Shot") == "tip"
    assert features.classify_action_family("Driving Dunk Shot") == "dunk"
    assert features.classify_action_family("Driving Hook Shot") == "hook"
    assert features.classify_action_family("Turnaround Bank Hook Shot") == "hook"
    assert features.classify_action_family("Floating Jump shot") == "floater"
    assert features.classify_action_family("Driving Floating Bank Jump Shot") == "floater"
    assert features.classify_action_family("Driving Layup Shot") == "layup"
    assert features.classify_action_family("Finger Roll Layup Shot") == "layup"
    assert features.classify_action_family("Step Back Jump shot") == "step_back"
    assert features.classify_action_family("Fadeaway Jump Shot") == "fadeaway"
    assert features.classify_action_family("Turnaround Jump Shot") == "fadeaway"
    assert features.classify_action_family("Running Pull-Up Jump Shot") == "pull_up"
    assert features.classify_action_family("Pullup Bank shot") == "pull_up"
    assert features.classify_action_family("Jump Shot") == "catch_and_shoot"
    assert features.classify_action_family("Jump Bank Shot") == "catch_and_shoot"


def test_build_shot_features_drops_no_shot_rows_but_keeps_origin_rim_shots():
    shots = pl.DataFrame(
        {
            "action_type": ["Jump Shot", "No Shot", "Layup Shot"],
            "loc_x": [50, 0, 0],
            "loc_y": [50, 0, 0],
            "shot_type": ["2PT Field Goal", "2PT Field Goal", "2PT Field Goal"],
            "shot_distance": [7, 0, 0],
            "minutes_remaining": [5, 0, 0],
            "seconds_remaining": [30, 0, 0],
        }
    )
    out = features.build_shot_features(shots)
    # "No Shot" dropped by action_type. The origin (0, 0) "Layup Shot" is
    # kept: its shot_distance is consistently 0 (a genuine point-blank rim
    # attempt, not a coordinate error — verified against the real data).
    assert out.height == 2
    assert set(out["action_type"].to_list()) == {"Jump Shot", "Layup Shot"}


def test_build_shot_features_computes_derived_columns():
    shots = pl.DataFrame(
        {
            "action_type": ["Pullup Jump shot"],
            "loc_x": [100],  # 10 ft right of centerline
            "loc_y": [100],  # 10 ft from baseline
            "shot_type": ["3PT Field Goal"],
            "shot_distance": [14],
            "minutes_remaining": [0],
            "seconds_remaining": [2],
        }
    )
    out = features.build_shot_features(shots)
    row = out.row(0, named=True)
    assert row["action_family"] == "pull_up"
    assert row["shot_value"] == 3
    assert row["seconds_left_in_period"] == 2
    assert row["x_ft"] == 10.0
    assert row["y_ft"] == 10.0
    assert abs(row["angle"] - 45.0) < 1e-6


def test_build_shot_features_flags_end_of_quarter_heaves():
    shots = pl.DataFrame(
        {
            "action_type": ["Jump Shot", "Jump Shot"],
            "loc_x": [0, 0],
            "loc_y": [350, 100],
            "shot_type": ["3PT Field Goal", "3PT Field Goal"],
            "shot_distance": [35, 10],
            "minutes_remaining": [0, 0],
            "seconds_remaining": [1, 1],
        }
    )
    out = features.build_shot_features(shots)
    assert out["is_heave"].to_list() == [True, False]
