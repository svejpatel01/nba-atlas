"""End-to-end shot-quality pipeline: builds features, trains and evaluates
both models, picks one, retrains it on the full window, exports the xFG
grid (+ parity test), per-player-season metrics, hex aggregates, and the
quadrant scatter (docs/shot-quality-court-spec.md).

    uv run python -m hub.shots.export
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import polars as pl

from hub.shots import grid as grid_mod
from hub.shots import hex as hex_mod
from hub.shots import model as model_mod
from hub.shots import player_metrics as metrics_mod
from hub.shots.features import build_shot_features
from hub.tables import seasons as season_utils

logger = logging.getLogger("hub.shots.export")

DEFAULT_DATA_ROOT = Path(__file__).resolve().parents[4] / "data"
DEFAULT_OUT_DIR = Path(__file__).resolve().parents[4] / "web" / "public" / "data" / "shots"
N_SHARDS = 32
# A calibration curve is "materially better" if its average absolute
# predicted-vs-actual gap across deciles is at least this much smaller —
# otherwise ship the simpler logistic baseline (PLAN.md: "if they're close,
# prefer logistic regression for simplicity and easier grid derivation").
MATERIAL_CALIBRATION_GAP = 0.003


def _mean_calibration_gap(calibration: list[dict]) -> float:
    return float(np.mean([abs(b["predicted"] - b["actual"]) for b in calibration]))


def choose_model(baseline_eval: dict, lgbm_eval: dict) -> str:
    baseline_gap = _mean_calibration_gap(baseline_eval["calibration"])
    lgbm_gap = _mean_calibration_gap(lgbm_eval["calibration"])
    if baseline_gap - lgbm_gap >= MATERIAL_CALIBRATION_GAP:
        return "lightgbm"
    return "logistic"


def run(data_root: Path, out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    shots = pl.read_parquet(data_root / "tables" / "shots.parquet")
    built = build_shot_features(shots)
    df = built.to_pandas()
    logger.info("shot features built: %d rows", len(df))

    validate_season = season_utils.format_season(
        season_utils.most_recent_completed_season_start_year()
    )
    train, validate = model_mod.time_split(df, validate_season)
    logger.info(
        "train: %d rows, validate (%s): %d rows", len(train), validate_season, len(validate)
    )

    logger.info("fitting logistic baseline")
    baseline = model_mod.fit_logistic_baseline(train)
    baseline_eval = model_mod.evaluate(baseline, validate)
    logger.info("baseline: log_loss=%.4f auc=%.4f", baseline_eval["log_loss"], baseline_eval["auc"])

    logger.info("fitting LightGBM")
    lgbm = model_mod.fit_lightgbm(train)
    lgbm_eval = model_mod.evaluate(lgbm, validate)
    logger.info("lightgbm: log_loss=%.4f auc=%.4f", lgbm_eval["log_loss"], lgbm_eval["auc"])

    chosen_name = choose_model(baseline_eval, lgbm_eval)
    logger.info("chosen model: %s", chosen_name)

    logger.info("refitting %s on the full window (all seasons)", chosen_name)
    final_model = (
        model_mod.fit_lightgbm(df)
        if chosen_name == "lightgbm"
        else model_mod.fit_logistic_baseline(df)
    )

    df["xfg"] = model_mod.predict_proba(final_model, df)

    logger.info("building xFG grid")
    cells = grid_mod.build_grid_cells()
    grid_bytes, grid_meta = grid_mod.build_grid_binary(final_model, model_mod.predict_proba, cells)
    (out_dir / "xfg_grid.bin").write_bytes(grid_bytes)
    (out_dir / "xfg_grid_meta.json").write_text(json.dumps(grid_meta, indent=2))
    logger.info("wrote xfg_grid.bin (%d bytes)", len(grid_bytes))

    parity = run_parity_test(final_model, cells, grid_bytes, grid_meta)
    logger.info(
        "grid parity: max_abs_error=%.5f (n=%d)", parity["max_abs_error"], parity["n_sampled"]
    )

    export_player_and_hex_data(df, out_dir)

    report = {
        "validate_season": validate_season,
        "chosen_model": chosen_name,
        "baseline_eval": baseline_eval,
        "lightgbm_eval": lgbm_eval,
        "grid_parity": parity,
    }
    (out_dir / "shot_quality_evals.json").write_text(json.dumps(report, indent=2, default=str))
    logger.info("wrote shot_quality_evals.json")
    return report


def run_parity_test(
    model, cells: pd.DataFrame, grid_bytes: bytes, meta: dict, n_samples: int = 200
) -> dict:
    """Re-runs the trained model directly on a sample of grid-cell centers
    and compares against the quantized values pulled back out of the
    exported binary — catches silent bugs in grid generation (wrong
    coordinate transform, wrong family encoding) that wouldn't show up in
    the model's own metrics.
    """
    rng = np.random.default_rng(42)
    n_cells = len(cells)
    sample_idx = rng.choice(n_cells, size=min(n_samples, n_cells), replace=False)
    errors = []
    for family_idx, family in enumerate(meta["family_order"]):
        block_start = family_idx * n_cells
        block = np.frombuffer(grid_bytes[block_start : block_start + n_cells], dtype=np.uint8)
        sampled_cells = cells.iloc[sample_idx]
        direct_probs = grid_mod.predict_grid_for_family(
            model, model_mod.predict_proba, sampled_cells, family
        )
        direct_bytes = grid_mod.quantize(direct_probs)
        exported_bytes = block[sample_idx]
        errors.extend(np.abs(direct_bytes.astype(int) - exported_bytes.astype(int)).tolist())
    max_abs_error_bytes = max(errors)
    return {
        "n_sampled": len(errors),
        "max_abs_error_bytes": int(max_abs_error_bytes),
        "max_abs_error": round(max_abs_error_bytes / 255.0, 5),
    }


def export_player_and_hex_data(df: pd.DataFrame, out_dir: Path) -> None:
    for season, season_df in df.groupby("season"):
        metrics = metrics_mod.compute_player_season_metrics(season_df, season=str(season))
        metrics.to_json(out_dir / f"player_metrics_{season}.json", orient="records")

        qualified = metrics[metrics["attempts"] >= 50]
        qualified[
            ["player_id", "player_name", "shot_selection", "shot_making", "attempts"]
        ].to_json(out_dir / f"shot_quadrant_{season}.json", orient="records")

        league_hex = hex_mod.build_hex_aggregates(season_df, group_cols=[])
        (out_dir / f"league_hex_{season}.json").write_text(league_hex.to_json(orient="records"))

        player_hex = hex_mod.build_hex_aggregates(season_df, group_cols=["player_id"])
        player_hex["shard"] = player_hex["player_id"] % N_SHARDS
        for shard, shard_df in player_hex.groupby("shard"):
            path = out_dir / f"shot_hexes_{season}_{shard}.json"
            shard_df.drop(columns=["shard"]).to_json(path, orient="records")
        logger.info(
            "season %s: exported hex aggregates (%d players)",
            season,
            season_df["player_id"].nunique(),
        )


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", stream=sys.stdout
    )
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=DEFAULT_DATA_ROOT)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    args = parser.parse_args(argv)
    run(data_root=args.data_root, out_dir=args.out_dir)


if __name__ == "__main__":
    main()
