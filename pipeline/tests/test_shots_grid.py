import numpy as np

from hub.shots import grid
from hub.shots.features import ACTION_FAMILIES


def test_build_grid_cells_matches_spec_estimate():
    cells = grid.build_grid_cells()
    # PLAN.md: "roughly 50 by 47 feet, so about 2,350 cells" — exact here
    # since 1-ft cells tile a 50x47 court exactly.
    assert len(cells) == 50 * 47
    assert cells["x_ft"].min() > grid.X_MIN
    assert cells["x_ft"].max() < grid.X_MAX
    assert cells["y_ft"].min() > grid.Y_MIN
    assert cells["y_ft"].max() < grid.Y_MAX


def test_classify_shot_value_arc_and_corner():
    x = np.array([0.0, 0.0, 23.0, 0.0])
    y = np.array([10.0, 25.0, 5.0, 24.0])  # last: straight-away 24ft -> 3
    values = grid.classify_shot_value(x, y)
    assert values[0] == 2  # short, straight on
    assert values[1] == 3  # 25 ft straight on, beyond the arc
    assert values[2] == 3  # corner 3 (23 ft from baseline sideline, y<14)
    assert values[3] == 3  # beyond 23.75 ft arc


def test_quantize_dequantize_round_trip_error_bound():
    probs = np.linspace(0, 1, 1000)
    byte_values = grid.quantize(probs)
    recovered = grid.dequantize(byte_values)
    max_error = np.abs(probs - recovered).max()
    assert max_error < 0.005  # well inside the ~2-3 percentage point tolerance


def test_quantize_clips_out_of_range_values():
    assert grid.quantize(np.array([-0.5, 1.5]))[0] == 0
    assert grid.quantize(np.array([-0.5, 1.5]))[1] == 255


def test_build_grid_binary_and_parity_with_direct_prediction():
    cells = grid.build_grid_cells()

    def fake_predict_proba(model, X):
        # A deterministic stand-in "model": probability falls off with
        # distance, offset slightly by action family — enough to verify the
        # export's per-family blocks and the parity check math, without a
        # real trained model.
        family_offset = {f: i * 0.01 for i, f in enumerate(ACTION_FAMILIES)}
        base = np.clip(0.7 - X["shot_distance"].to_numpy() / 40, 0.02, 0.98)
        return np.clip(base + X["action_family"].map(family_offset).to_numpy(), 0.0, 1.0)

    data, meta = grid.build_grid_binary(
        model=None, predict_proba_fn=fake_predict_proba, cells=cells
    )

    assert meta["family_order"] == ACTION_FAMILIES
    assert meta["n_cells_per_family"] == len(cells)
    assert len(data) == len(ACTION_FAMILIES) * len(cells)  # 1 byte/cell

    # Parity: re-run the "model" directly on a sample and compare against
    # the quantized bytes pulled back out of the exported blob.
    sample_family_idx = 3
    family = ACTION_FAMILIES[sample_family_idx]
    direct_probs = grid.predict_grid_for_family(None, fake_predict_proba, cells, family)
    direct_bytes = grid.quantize(direct_probs)

    block = np.frombuffer(
        data[sample_family_idx * len(cells) : (sample_family_idx + 1) * len(cells)], dtype=np.uint8
    )
    assert np.array_equal(block, direct_bytes)


def test_cell_index_matches_row_major_meshgrid_order():
    cells = grid.build_grid_cells()
    n_x_cells = int(grid.X_MAX - grid.X_MIN)
    # The first row (smallest y) should occupy indices [0, n_x_cells).
    first_row = cells.iloc[:n_x_cells]
    assert (first_row["y_ft"] == first_row["y_ft"].iloc[0]).all()
    for i, row in first_row.reset_index(drop=True).iterrows():
        assert grid.cell_index(row["x_ft"], row["y_ft"], n_x_cells) == i
