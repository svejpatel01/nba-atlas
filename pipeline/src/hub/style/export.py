"""Fits the style-map models on the full feature table and exports the
static JSON files the web app reads: style_map_modern.json, archetypes.json,
style_model_meta.json, plus an eval report for the methodology page.

    uv run python -m hub.style.export

v1 simplification vs. the spec: fits PCA/GMM/UMAP once on the full 2015-16..
2025-26 history rather than per-season with nightly transform() updates —
the nightly-refresh mechanics are a Phase 6 operational concern, not needed
to ship a first working map. Noted in docs/decisions.md.
"""

from __future__ import annotations

import argparse
import datetime
import json
import logging
import sys
from pathlib import Path

import numpy as np
import polars as pl

from hub.style import evals as style_evals
from hub.style import model, pipeline

logger = logging.getLogger("hub.style.export")

DEFAULT_DATA_ROOT = Path(__file__).resolve().parents[4] / "data"
DEFAULT_OUT_DIR = Path(__file__).resolve().parents[4] / "web" / "public" / "data" / "style"

# A short label for each feature, used to name archetypes from their most
# distinctive raw features. Not exhaustive — falls back to the raw column
# name for anything not mapped, per PLAN.md's "then edit by hand" (a human
# should revisit these names; this is a defensible starting point without
# an LLM call, not a promise every name is polished prose).
FEATURE_LABELS: dict[str, str] = {
    "share_fga_restricted_area": "rim shots",
    "share_fga_paint_non_ra": "paint shots",
    "share_fga_midrange": "midrange shots",
    "share_fga_corner3": "corner 3s",
    "share_fga_atb3": "above-the-break 3s",
    "fta_per_fga": "free throw rate",
    "usg_pct": "usage",
    "ast_pct": "assist rate",
    "ast_to_usg_ratio": "pass-first tendency",
    "oreb_pct": "offensive rebounding",
    "dreb_pct": "defensive rebounding",
    "blk_per100": "shot blocking",
    "stl_per100": "steals",
    "pf_per100": "fouling",
    "pct_uast_2pm": "unassisted 2s",
    "pct_uast_3pm": "unassisted 3s",
    "touches_per36": "touches",
    "sec_per_touch": "time per touch",
    "dribbles_per_touch": "dribbles per touch",
    "drives_per36": "drives",
    "passes_per36": "passing volume",
    "potential_ast_per36": "playmaking",
    "catch_shoot_share_fga": "catch-and-shoot",
    "pull_up_share_fga": "pull-up shooting",
    "paint_touch_share": "paint touches",
    "post_touch_share": "post touches",
    "elbow_touch_share": "elbow touches",
    "playtype_Transition": "transition offense",
    "playtype_Isolation": "isolation",
    "playtype_PRBallHandler": "pick-and-roll ball handling",
    "playtype_PRRollman": "pick-and-roll rolling",
    "playtype_Postup": "post-ups",
    "playtype_Spotup": "spot-up shooting",
    "playtype_Handoff": "handoffs",
    "playtype_Cut": "cutting",
    "playtype_OffScreen": "off-ball screens",
    "playtype_OffRebound": "putbacks",
}


def name_archetype(archetype_id: int, mean_features: dict[str, float]) -> tuple[str, str]:
    ranked = sorted(mean_features.items(), key=lambda kv: abs(kv[1]), reverse=True)
    top = ranked[:2]
    labels = [FEATURE_LABELS.get(col, col) for col, _ in top]
    name = " + ".join(label.title() for label in labels)
    description = f"Distinguished by {' and '.join(labels)} relative to league average."
    return name or f"Archetype {archetype_id}", description


def compute_fingerprint(row: dict, feature_groups: dict[str, list[str]]) -> dict[str, float]:
    return {group: float(np.mean([row[c] for c in cols])) for group, cols in feature_groups.items()}


def run(data_root: Path, out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    sf = pl.read_parquet(data_root / "tables" / "style_features.parquet")
    players = pl.read_parquet(data_root / "tables" / "players.parquet")
    player_seasons = pl.read_parquet(data_root / "tables" / "player_seasons.parquet")
    teams = pl.read_parquet(data_root / "tables" / "teams.parquet")
    current_season = sf["season"].max()

    feature_cols = pipeline.ALL_FEATURE_COLS
    X = sf.select(feature_cols).to_numpy()

    logger.info("fitting PCA on %d player-seasons, %d features", *X.shape)
    pca = model.fit_pca(X)
    vecs = pca.transform(X)
    logger.info(
        "PCA: %d components, %.1f%% variance explained",
        pca.n_components_,
        pca.explained_variance_ratio_.sum() * 100,
    )

    logger.info("fitting Gaussian mixture (BIC search)")
    gmm, bics = model.choose_gmm_components(vecs)
    logger.info(
        "GMM: chose k=%d (BICs: %s)", gmm.n_components, {k: round(v, 1) for k, v in bics.items()}
    )
    arch_probs = gmm.predict_proba(vecs)
    hard_labels = arch_probs.argmax(axis=1)

    logger.info("fitting UMAP layout")
    reducer = model.fit_umap(vecs)
    layout = reducer.transform(vecs)

    sf = sf.with_columns(
        [
            pl.Series("x", layout[:, 0]),
            pl.Series("y", layout[:, 1]),
            pl.Series("archetype_hard", hard_labels),
        ]
    )

    archetypes = []
    for k in range(gmm.n_components):
        mask = hard_labels == k
        mean_features = {col: float(sf[col].to_numpy()[mask].mean()) for col in feature_cols}
        name, description = name_archetype(k, mean_features)
        top_features = sorted(mean_features.items(), key=lambda kv: abs(kv[1]), reverse=True)[:5]
        archetypes.append(
            {
                "id": k,
                "name": name,
                "description": description,
                "color": f"hsl({int(360 * k / gmm.n_components)}, 65%, 50%)",
                "top_features": [{"feature": c, "z_score": round(v, 2)} for c, v in top_features],
                "n_player_seasons": int(mask.sum()),
            }
        )

    panel = player_seasons.select(
        pl.col("player_id"),
        pl.col("season"),
        pl.col("team_id"),
        pl.col("ts_pct"),
        (pl.col("pts") / pl.col("min").replace(0, None) * 36).alias("pts_per36"),
    )
    bios = players.select("player_id", "height", "birthdate", "position")
    team_abbrevs = teams.select("team_id", "abbreviation")

    # player_seasons, players, and teams are all unique-keyed (player_id+season,
    # player_id, and team_id respectively — verified in docs/decisions.md's
    # Phase 1 work), so these left joins can't fan out sf's row order or count.
    sf = (
        sf.join(panel, on=["player_id", "season"], how="left")
        .join(bios, on="player_id", how="left")
        .join(team_abbrevs, on="team_id", how="left")
    )

    feature_groups = pipeline.ALL_FEATURE_GROUPS
    rows = []
    for i, row in enumerate(sf.iter_rows(named=True)):
        fingerprint = compute_fingerprint(row, feature_groups)
        rows.append(
            {
                "player_id": row["player_id"],
                "name": row["name"],
                "season": row["season"],
                "team_id": row["team_id"],
                "team": row["abbreviation"],
                "minutes": int(round(row["minutes"])),
                "provisional": row["season"] == current_season,
                "x": round(float(row["x"]), 4),
                "y": round(float(row["y"]), 4),
                "vec": [round(float(v), 4) for v in vecs[i]],
                "arch": [round(float(p), 4) for p in arch_probs[i]],
                "fingerprint": {g: round(v, 3) for g, v in fingerprint.items()},
                "panel": {
                    "pts_per36": round(row["pts_per36"], 1)
                    if row["pts_per36"] is not None
                    else None,
                    "ts_pct": row["ts_pct"],
                    "height": row["height"],
                    "position": row["position"],
                },
            }
        )

    style_map_path = out_dir / "style_map_modern.json"
    style_map_path.write_text(json.dumps(rows))
    logger.info("wrote %s (%d player-seasons)", style_map_path, len(rows))

    archetypes_path = out_dir / "archetypes.json"
    archetypes_path.write_text(json.dumps(archetypes, indent=2))
    logger.info("wrote %s", archetypes_path)

    meta = {
        "feature_names": feature_cols,
        "feature_groups": feature_groups,
        "pca_components": int(pca.n_components_),
        "pca_explained_variance": round(float(pca.explained_variance_ratio_.sum()), 4),
        "gmm_components": int(gmm.n_components),
        "gmm_bics": {str(k): round(v, 1) for k, v in bics.items()},
        "model_version": 1,
        "data_through": current_season,
        "generated_at": datetime.datetime.now(tz=datetime.UTC).isoformat(),
    }
    meta_path = out_dir / "style_model_meta.json"
    meta_path.write_text(json.dumps(meta, indent=2))
    logger.info("wrote %s", meta_path)

    logger.info("running evals")
    eval_report = style_evals.run_all_evals(sf, vecs, arch_probs, feature_cols)
    eval_path = out_dir / "style_evals.json"
    eval_path.write_text(json.dumps(eval_report, indent=2, default=str))
    logger.info("wrote %s", eval_path)

    return {"meta": meta, "evals": eval_report}


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
