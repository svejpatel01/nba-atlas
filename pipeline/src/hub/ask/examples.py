"""Curated question/SQL pairs for the "ask the box score" example gallery.

These ship as clickable chips that use zero LLM calls (per PLAN.md's "staying
free" section). Every query here is validated at build time — see `run()` —
against the real exported Parquet files, so a broken example can never ship.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import duckdb

logger = logging.getLogger("hub.ask.examples")

DEFAULT_DATA_DIR = Path(__file__).resolve().parents[4] / "web" / "public" / "data" / "ask"

EXAMPLES: list[dict[str, str]] = [
    {
        "category": "easy",
        "question": "Who scored the most points in the 2023-24 season?",
        "sql": "SELECT player_name, pts FROM player_seasons WHERE season = '2023-24' "
        "ORDER BY pts DESC LIMIT 10",
    },
    {
        "category": "easy",
        "question": "Which teams made the most 3-pointers as a team in the 2023-24 season?",
        "sql": "SELECT team_name, SUM(fg3m) AS total_threes FROM team_game_logs "
        "WHERE season = '2023-24' GROUP BY team_name ORDER BY total_threes DESC LIMIT 10",
    },
    {
        "category": "easy",
        "question": "Who led the league in assists per game in 2023-24 (minimum 50 games)?",
        "sql": "SELECT player_name, ROUND(ast * 1.0 / gp, 1) AS ast_per_game FROM player_seasons "
        "WHERE season = '2023-24' AND gp >= 50 ORDER BY ast_per_game DESC LIMIT 10",
    },
    {
        "category": "easy",
        "question": "What was the highest-scoring game in the 2023-24 season?",
        "sql": "SELECT game_date, home_team_id, away_team_id, home_score, away_score, "
        "(home_score + away_score) AS total_points FROM games WHERE season = '2023-24' "
        "ORDER BY total_points DESC LIMIT 10",
    },
    {
        "category": "easy",
        "question": "Which players are listed at 7 feet or taller?",
        "sql": "SELECT name, position, height, weight, country FROM players "
        "WHERE TRY_CAST(SPLIT_PART(height, '-', 1) AS INTEGER) >= 7 ORDER BY name LIMIT 50",
    },
    {
        "category": "medium",
        "question": "Who had the most 30-point games in the 2023-24 season?",
        "sql": "SELECT player_name, COUNT(*) AS games_with_30 FROM player_game_logs "
        "WHERE season = '2023-24' AND pts >= 30 GROUP BY player_name "
        "ORDER BY games_with_30 DESC LIMIT 10",
    },
    {
        "category": "medium",
        "question": "Who had the most 30-point games on fewer than 15 shots in the 2023-24 season?",
        "sql": "SELECT player_name, COUNT(*) AS efficient_30s FROM player_game_logs "
        "WHERE season = '2023-24' AND pts >= 30 AND fga < 15 GROUP BY player_name "
        "ORDER BY efficient_30s DESC LIMIT 10",
    },
    {
        "category": "medium",
        "question": "Which players had a triple-double in the 2023-24 season?",
        "sql": "SELECT player_name, game_date, pts, reb, ast FROM player_game_logs "
        "WHERE season = '2023-24' AND pts >= 10 AND reb >= 10 AND ast >= 10 "
        "ORDER BY game_date LIMIT 50",
    },
    {
        "category": "medium",
        "question": "What was the largest margin of victory in the 2023-24 season?",
        "sql": "SELECT game_date, home_team_id, away_team_id, home_score, away_score, "
        "ABS(home_score - away_score) AS margin FROM games WHERE season = '2023-24' "
        "ORDER BY margin DESC LIMIT 10",
    },
    {
        "category": "medium",
        "question": "Which team had the best regular season record in 2023-24?",
        "sql": "SELECT team_name, "
        "SUM(CASE WHEN wl = 'W' THEN 1 ELSE 0 END) AS wins, "
        "SUM(CASE WHEN wl = 'L' THEN 1 ELSE 0 END) AS losses "
        "FROM team_game_logs WHERE season = '2023-24' GROUP BY team_name "
        "ORDER BY wins DESC LIMIT 10",
    },
    {
        "category": "medium",
        "question": "Who had the best true shooting percentage in 2023-24 (minimum 500 minutes)?",
        "sql": "SELECT player_name, ROUND(ts_pct, 3) AS true_shooting FROM player_seasons "
        "WHERE season = '2023-24' AND min >= 500 ORDER BY ts_pct DESC LIMIT 10",
    },
    {
        "category": "medium",
        "question": "Which player had the most steals in a single game in the 2023-24 season?",
        "sql": "SELECT player_name, game_date, stl FROM player_game_logs "
        "WHERE season = '2023-24' ORDER BY stl DESC LIMIT 10",
    },
    {
        "category": "medium",
        "question": "What was the closest (smallest margin) game in the 2023-24 season?",
        "sql": "SELECT game_date, home_team_id, away_team_id, home_score, away_score, "
        "ABS(home_score - away_score) AS margin FROM games WHERE season = '2023-24' "
        "ORDER BY margin ASC LIMIT 10",
    },
    {
        "category": "medium",
        "question": "How has Nikola Jokic's scoring changed across seasons?",
        "sql": "SELECT ps.season, ps.pts, ROUND(ps.pts * 1.0 / ps.gp, 1) AS pts_per_game "
        "FROM player_seasons ps JOIN players p ON ps.player_id = p.player_id "
        "WHERE p.name = 'Nikola Jokić' ORDER BY ps.season",
    },
    {
        "category": "hard",
        "question": "Which players have played for the most different teams since 2015-16?",
        "sql": "SELECT player_name, COUNT(DISTINCT team_id) AS teams_played_for "
        "FROM player_game_logs GROUP BY player_name "
        "ORDER BY teams_played_for DESC LIMIT 10",
    },
    {
        "category": "hard",
        "question": "Which rookie season scored the most points?",
        "sql": "SELECT ps.player_name, ps.season, ps.pts FROM player_seasons ps "
        "JOIN players p ON ps.player_id = p.player_id "
        "WHERE ps.season = (CAST(p.from_year AS VARCHAR) || '-' || "
        "LPAD(CAST((p.from_year + 1) % 100 AS VARCHAR), 2, '0')) "
        "ORDER BY ps.pts DESC LIMIT 10",
    },
    {
        "category": "hard",
        "question": "Which teams improved the most in win percentage from 2022-23 to 2023-24?",
        "sql": "WITH by_season AS ( "
        "SELECT team_name, season, "
        "SUM(CASE WHEN wl = 'W' THEN 1 ELSE 0 END) * 1.0 / COUNT(*) AS win_pct "
        "FROM team_game_logs WHERE season IN ('2022-23', '2023-24') "
        "GROUP BY team_name, season) "
        "SELECT b24.team_name, b24.win_pct - b23.win_pct AS improvement "
        "FROM by_season b24 JOIN by_season b23 "
        "ON b24.team_name = b23.team_name AND b24.season = '2023-24' AND b23.season = '2022-23' "
        "ORDER BY improvement DESC LIMIT 10",
    },
    {
        "category": "hard",
        "question": "What's the biggest single-game scoring outburst by a player since 2015-16?",
        "sql": "SELECT player_name, season, game_date, pts FROM player_game_logs "
        "ORDER BY pts DESC LIMIT 10",
    },
    {
        "category": "off-topic",
        "question": "What's the weather like today?",
        "sql": "REFUSE: this dataset only covers NBA box scores, games, and season stats "
        "from 2015-16 onward. Try one of the example questions instead.",
    },
    {
        "category": "unanswerable",
        "question": "Who is going to win the championship next year?",
        "sql": "REFUSE: this dataset has historical stats only, no predictions or future data.",
    },
]


def validate(data_dir: Path) -> list[dict[str, str]]:
    """Runs every real (non-refusal) example SQL against the actual exported
    Parquet files. Raises if any fails, so a broken example can never ship.
    """
    con = duckdb.connect()
    for name in ["players", "teams", "games", "team_game_logs", "player_seasons"]:
        con.execute(
            f"CREATE TABLE {name} AS SELECT * FROM read_parquet('{data_dir / f'{name}.parquet'}')"
        )
    season_files = sorted(data_dir.glob("player_game_logs_*.parquet"))
    files_list = ", ".join(f"'{f}'" for f in season_files)
    con.execute(f"CREATE TABLE player_game_logs AS SELECT * FROM read_parquet([{files_list}])")

    validated = []
    for example in EXAMPLES:
        if example["sql"].startswith("REFUSE:"):
            validated.append(example)
            continue
        try:
            result = con.execute(example["sql"]).fetchall()
        except Exception as exc:  # noqa: BLE001
            raise AssertionError(
                f"Example failed to execute: {example['question']!r}: {exc}"
            ) from exc
        if len(result) == 0:
            raise AssertionError(f"Example returned zero rows: {example['question']!r}")
        validated.append(example)
        logger.info("validated (%d rows): %s", len(result), example["question"])
    return validated


def run(data_dir: Path) -> Path:
    validated = validate(data_dir)
    out_path = data_dir / "examples.json"
    out_path.write_text(json.dumps(validated, indent=2))
    logger.info("wrote %s (%d examples)", out_path, len(validated))
    return out_path


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", stream=sys.stdout
    )
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    args = parser.parse_args(argv)
    run(args.data_dir)


if __name__ == "__main__":
    main()
