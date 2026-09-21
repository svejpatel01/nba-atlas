"""End-to-end game-flow pipeline: computes Elo, builds event-level features,
trains and evaluates both win-probability models, picks one, refits it on
the full window, scores every event, computes per-game summaries, and
exports the season index + monthly bundles (docs/game-flow-spec.md).

    uv run python -m hub.gameflow.export
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections import defaultdict
from pathlib import Path

import polars as pl

from hub.gameflow import elo as elo_mod
from hub.gameflow import model as model_mod
from hub.gameflow import summaries as summaries_mod
from hub.gameflow.features import FEATURE_COLUMNS, build_game_flow_features
from hub.tables import seasons as season_utils

logger = logging.getLogger("hub.gameflow.export")

DEFAULT_DATA_ROOT = Path(__file__).resolve().parents[4] / "data"
DEFAULT_OUT_DIR = Path(__file__).resolve().parents[4] / "web" / "public" / "data" / "gameflow"


def run(data_root: Path, out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)

    games = pl.read_parquet(data_root / "tables" / "games.parquet")
    pbp = pl.read_parquet(data_root / "tables" / "pbp_events.parquet")
    teams = pl.read_parquet(data_root / "tables" / "teams.parquet")

    logger.info("computing Elo ratings over full history")
    elo_ratings = elo_mod.compute_elo(games)

    logger.info("building event-level features")
    feats = build_game_flow_features(pbp, games, elo_ratings).to_pandas()
    logger.info("features built: %d rows across %d games", len(feats), feats["game_id"].nunique())

    validate_season = season_utils.format_season(
        season_utils.most_recent_completed_season_start_year()
    )
    train, validate = model_mod.time_split(feats, validate_season)

    logger.info("fitting logistic baseline")
    logistic = model_mod.fit_logistic(train)
    logistic_eval = model_mod.evaluate(logistic, validate)
    logger.info(
        "logistic: log_loss=%.4f brier=%.4f",
        logistic_eval["log_loss"],
        logistic_eval["brier_score"],
    )

    logger.info("fitting LightGBM")
    lgbm = model_mod.fit_lightgbm(train)
    lgbm_eval = model_mod.evaluate(lgbm, validate)
    logger.info(
        "lightgbm: log_loss=%.4f brier=%.4f", lgbm_eval["log_loss"], lgbm_eval["brier_score"]
    )

    chosen_name = model_mod.choose_model(logistic_eval, lgbm_eval)
    logger.info("chosen model: %s", chosen_name)

    # A TypeScript reimplementation (milestone 5) only exists for logistic
    # regression's dot-product-and-sigmoid form. If a future run of this
    # pipeline ever picks LightGBM, that's a real scope change (a tree
    # structure would need its own exporter and its own parity test), so
    # this fails loudly here rather than silently shipping a Python-only
    # model the frontend can't actually reproduce.
    if chosen_name != "logistic":
        raise NotImplementedError(
            f"chose {chosen_name}, but only logistic regression has a TypeScript "
            "reimplementation (hub.gameflow.model docstring / milestone 5). Build that "
            "before shipping a non-logistic model."
        )

    logger.info("refitting %s on the full window (train + validate)", chosen_name)
    final_model = model_mod.fit_logistic(feats)
    feats["win_prob"] = model_mod.predict_proba(final_model, feats)

    coefficients = dict(zip(FEATURE_COLUMNS, final_model.coef_[0].tolist(), strict=True))
    intercept = float(final_model.intercept_[0])

    team_abbrev = dict(
        zip(teams["team_id"].to_list(), teams["abbreviation"].to_list(), strict=True)
    )
    elo_by_game = {
        row["game_id"]: (row["pregame_home_elo"], row["pregame_away_elo"])
        for row in elo_ratings.iter_rows(named=True)
    }
    game_meta = (
        games.select(
            "game_id",
            "season",
            "game_date",
            "home_team_id",
            "away_team_id",
            "home_score",
            "away_score",
        )
        .to_pandas()
        .set_index("game_id")
    )

    logger.info("computing per-game summaries")
    games_index: dict[str, list[dict]] = defaultdict(list)
    monthly_bundles: dict[tuple[str, str], list[dict]] = defaultdict(list)
    skipped = 0

    for game_id, game_df in feats.groupby("game_id", sort=False):
        if game_id not in game_meta.index:
            skipped += 1
            continue
        meta = game_meta.loc[game_id]
        game_df = game_df.sort_values(["period", "action_number"])
        home_win = bool(meta["home_score"] > meta["away_score"])
        summary = summaries_mod.summarize_game(game_df, home_win)

        season = str(meta["season"])
        game_date = str(meta["game_date"])
        month_key = game_date[:7]  # "YYYY-MM"
        home_elo, away_elo = elo_by_game[game_id]

        games_index[season].append(
            {
                "game_id": game_id,
                "date": game_date,
                "home_team": team_abbrev.get(meta["home_team_id"], str(meta["home_team_id"])),
                "away_team": team_abbrev.get(meta["away_team_id"], str(meta["away_team_id"])),
                "home_score": int(meta["home_score"]),
                "away_score": int(meta["away_score"]),
                "excitement": summary["excitement"],
                "comeback_factor": summary["comeback_factor"],
            }
        )
        monthly_bundles[(season, month_key)].append(
            {
                "game_id": game_id,
                "series": summary["series"],
                "top_plays": summary["top_plays"],
                "pregame_elo": {"home": round(home_elo, 1), "away": round(away_elo, 1)},
            }
        )

    if skipped:
        logger.warning(
            "skipped %d games with PBP but no games.parquet row (known MATCHUP gap, see "
            "docs/decisions.md)",
            skipped,
        )

    for season, rows in games_index.items():
        rows.sort(key=lambda r: r["date"])
        (out_dir / f"games_{season}.json").write_text(json.dumps(rows))
    logger.info("wrote games_{season}.json for %d seasons", len(games_index))

    for (season, month), rows in monthly_bundles.items():
        rows.sort(key=lambda r: r["game_id"])
        (out_dir / f"gameflow_{season}_{month}.json").write_text(json.dumps(rows))
    logger.info("wrote %d monthly bundles", len(monthly_bundles))

    report = {
        "validate_season": validate_season,
        "chosen_model": chosen_name,
        "logistic_eval": logistic_eval,
        "lightgbm_eval": lgbm_eval,
        "logistic_coefficients": coefficients,
        "logistic_intercept": intercept,
        "n_games_exported": sum(len(v) for v in games_index.values()),
        "n_games_skipped": skipped,
    }
    (out_dir / "gameflow_evals.json").write_text(json.dumps(report, indent=2, default=str))
    logger.info("wrote gameflow_evals.json")
    return report


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
