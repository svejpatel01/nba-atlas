import json

import polars as pl

from hub.ask import export
from hub.export.schemas import ASK_SCHEMA_VERSION, PlayerRow, assert_columns_match


def test_assert_columns_match_passes_for_correct_columns():
    assert_columns_match("players", list(PlayerRow.model_fields.keys()))


def test_assert_columns_match_raises_on_missing_column():
    cols = [c for c in PlayerRow.model_fields if c != "height"]
    try:
        assert_columns_match("players", cols)
        raise AssertionError("expected AssertionError")
    except AssertionError as exc:
        assert "height" in str(exc)


def _write_fixture_tables(tables_dir):
    tables_dir.mkdir(parents=True)
    pl.DataFrame(
        {
            "player_id": [1],
            "name": ["Test Player"],
            "from_year": [2020],
            "to_year": [2024],
            "position": ["G"],
            "height": ["6-3"],
            "weight": ["190"],
            "college": ["Nowhere U"],
            "country": ["USA"],
            "draft_year": ["2020"],
            "birthdate": ["1998-01-01T00:00:00"],
        }
    ).write_parquet(tables_dir / "players.parquet")

    pl.DataFrame(
        {
            "team_id": [1],
            "full_name": ["Test Team"],
            "abbreviation": ["TST"],
            "nickname": ["Testers"],
            "city": ["Testville"],
            "state": ["TS"],
            "year_founded": [2000],
        }
    ).write_parquet(tables_dir / "teams.parquet")

    pl.DataFrame(
        {
            "game_id": ["G1"],
            "season": ["2023-24"],
            "game_date": ["2023-10-24"],
            "home_team_id": [1],
            "home_score": [100],
            "home_wl": ["W"],
            "away_team_id": [1],
            "away_score": [90],
        }
    ).write_parquet(tables_dir / "games.parquet")

    pgl_cols = {
        "season": ["2023-24", "2024-25"],
        "player_id": [1, 1],
        "player_name": ["Test Player", "Test Player"],
        "team_id": [1, 1],
        "team_abbreviation": ["TST", "TST"],
        "game_id": ["G1", "G2"],
        "game_date": ["2023-10-24", "2024-10-24"],
        "matchup": ["TST vs. OPP", "TST vs. OPP"],
        "wl": ["W", "L"],
        "min": [30, 28],
        "fgm": [5, 4],
        "fga": [10, 9],
        "fg_pct": [0.5, 0.44],
        "fg3m": [1, 1],
        "fg3a": [3, 2],
        "fg3_pct": [0.33, 0.5],
        "ftm": [2, 1],
        "fta": [2, 2],
        "ft_pct": [1.0, 0.5],
        "oreb": [1, 0],
        "dreb": [4, 3],
        "reb": [5, 3],
        "ast": [3, 2],
        "stl": [1, 0],
        "blk": [0, 1],
        "tov": [2, 1],
        "pf": [2, 3],
        "pts": [13, 10],
        "plus_minus": [5.0, -3.0],
    }
    pl.DataFrame(pgl_cols).write_parquet(tables_dir / "player_game_logs.parquet")

    tgl_cols = {**{k: v for k, v in pgl_cols.items() if k not in ("player_id", "player_name")}}
    tgl_cols["team_name"] = ["Test Team", "Test Team"]
    pl.DataFrame(tgl_cols).write_parquet(tables_dir / "team_game_logs.parquet")

    pl.DataFrame(
        {
            "season": ["2023-24"],
            "player_id": [1],
            "player_name": ["Test Player"],
            "team_id": [1],
            "gp": [70],
            "min": [2000.0],
            "pts": [900],
            "reb": [300],
            "ast": [200],
            "stl": [50],
            "blk": [20],
            "tov": [100],
            "fg_pct": [0.48],
            "fg3_pct": [0.36],
            "ft_pct": [0.85],
            "usg_pct": [0.22],
            "ts_pct": [0.58],
            "ast_pct": [0.18],
            "oreb_pct": [0.03],
            "dreb_pct": [0.12],
            "pie": [0.1],
        }
    ).write_parquet(tables_dir / "player_seasons.parquet")


def test_export_run_writes_expected_files_and_manifest(tmp_path):
    tables_dir = tmp_path / "tables"
    out_dir = tmp_path / "out"
    _write_fixture_tables(tables_dir)

    manifest = export.run(tables_dir, out_dir)

    assert manifest["schema_version"] == ASK_SCHEMA_VERSION
    assert (out_dir / "players.parquet").exists()
    assert (out_dir / "teams.parquet").exists()
    assert (out_dir / "games.parquet").exists()
    assert (out_dir / "team_game_logs.parquet").exists()
    assert (out_dir / "player_seasons.parquet").exists()
    assert (out_dir / "player_game_logs_2023-24.parquet").exists()
    assert (out_dir / "player_game_logs_2024-25.parquet").exists()

    schema_on_disk = json.loads((out_dir / "schema.json").read_text())
    assert schema_on_disk == manifest
    assert set(manifest["tables"]["player_game_logs"]["files"]) == {
        "player_game_logs_2023-24.parquet",
        "player_game_logs_2024-25.parquet",
    }
