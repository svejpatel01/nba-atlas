import polars as pl

from hub.tables import build


def test_build_teams_renames_and_selects():
    raw = pl.DataFrame(
        [
            {
                "id": 1610612737,
                "full_name": "Atlanta Hawks",
                "abbreviation": "ATL",
                "nickname": "Hawks",
                "city": "Atlanta",
                "state": "Georgia",
                "year_founded": 1949,
            }
        ]
    )
    out = build.build_teams(raw)
    assert out.columns == [
        "team_id",
        "full_name",
        "abbreviation",
        "nickname",
        "city",
        "state",
        "year_founded",
    ]
    assert out["team_id"][0] == 1610612737


def test_build_players_left_joins_bio_and_keeps_players_without_bio():
    common = pl.DataFrame(
        [
            {
                "PERSON_ID": 1,
                "DISPLAY_FIRST_LAST": "Retired Guy",
                "FROM_YEAR": "1998",
                "TO_YEAR": "2005",
            },
            {
                "PERSON_ID": 2,
                "DISPLAY_FIRST_LAST": "Active Guy",
                "FROM_YEAR": "2020",
                "TO_YEAR": "2024",
            },
        ]
    )
    bios = pl.DataFrame(
        [
            {
                "PERSON_ID": 2,
                "POSITION": "G",
                "HEIGHT": "6-3",
                "WEIGHT": "195",
                "SCHOOL": "Duke",
                "COUNTRY": "USA",
                "DRAFT_YEAR": "2020",
                "BIRTHDATE": "1998-01-01T00:00:00",
            }
        ]
    )
    out = build.build_players(common, bios)
    assert out.shape == (2, 11)
    retired = out.filter(pl.col("player_id") == 1)
    assert retired["position"][0] is None
    active = out.filter(pl.col("player_id") == 2)
    assert active["height"][0] == "6-3"


def test_build_games_pairs_home_and_away_rows():
    raw = pl.DataFrame(
        [
            {
                "game_id": "G1",
                "season": "2023-24",
                "game_date": "2023-10-24",
                "team_id": 1,
                "matchup": "DEN vs. LAL",
                "wl": "W",
                "pts": 119,
            },
            {
                "game_id": "G1",
                "season": "2023-24",
                "game_date": "2023-10-24",
                "team_id": 2,
                "matchup": "LAL @ DEN",
                "wl": "L",
                "pts": 107,
            },
        ]
    )
    out = build.build_games(raw)
    assert out.shape == (1, 8)
    row = out.row(0, named=True)
    assert row["home_team_id"] == 1
    assert row["away_team_id"] == 2
    assert row["home_score"] == 119
    assert row["away_score"] == 107


def test_build_player_game_logs_lowercases_columns_and_stamps_season():
    raw = pl.DataFrame([{"PLAYER_ID": 1, "PTS": 20}])
    out = build.build_player_game_logs(raw, "2023-24")
    assert set(out.columns) == {"player_id", "pts", "season"}
    assert out["season"][0] == "2023-24"


def test_build_player_seasons_joins_base_and_advanced():
    base = pl.DataFrame(
        [
            {
                "PLAYER_ID": 1,
                "PLAYER_NAME": "A",
                "TEAM_ID": 10,
                "GP": 70,
                "MIN": 2000.0,
                "PTS": 1400,
                "REB": 300,
                "AST": 200,
                "STL": 50,
                "BLK": 20,
                "TOV": 100,
                "FG_PCT": 0.48,
                "FG3_PCT": 0.36,
                "FT_PCT": 0.85,
            }
        ]
    )
    advanced = pl.DataFrame(
        [
            {
                "PLAYER_ID": 1,
                "TEAM_ID": 10,
                "USG_PCT": 0.25,
                "TS_PCT": 0.58,
                "AST_PCT": 0.15,
                "OREB_PCT": 0.03,
                "DREB_PCT": 0.12,
                "PIE": 0.11,
            }
        ]
    )
    out = build.build_player_seasons(base, advanced, "2023-24")
    assert out.shape == (1, 21)
    assert out["usg_pct"][0] == 0.25
    assert out["season"][0] == "2023-24"


def test_build_pbp_events_converts_camel_case_to_snake_case():
    raw = pl.DataFrame([{"gameId": "0022300061", "actionNumber": 2, "playerName": "Jokić"}])
    out = build.build_pbp_events(raw)
    assert set(out.columns) == {"game_id", "action_number", "player_name"}
