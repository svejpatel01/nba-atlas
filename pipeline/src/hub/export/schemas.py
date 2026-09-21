"""Pydantic row schemas for exported tables, per the working agreement that
every export has one. These aren't used to validate every row (millions of
rows would make that slow for no benefit, since the data already comes from
our own typed pipeline) — they're the documented contract: CI checks a small
fixture export against both this and the matching TypeScript types in
`web/lib/types/`, so a schema drift shows up immediately.
"""

from __future__ import annotations

from pydantic import BaseModel

ASK_SCHEMA_VERSION = 1


class PlayerRow(BaseModel):
    player_id: int
    name: str
    from_year: int
    to_year: int
    position: str | None
    height: str | None
    weight: str | None
    college: str | None
    country: str | None
    draft_year: str | None
    birthdate: str | None


class TeamRow(BaseModel):
    team_id: int
    full_name: str
    abbreviation: str
    nickname: str
    city: str
    state: str
    year_founded: int


class GameRow(BaseModel):
    game_id: str
    season: str
    game_date: str
    home_team_id: int
    home_score: int
    home_wl: str
    away_team_id: int
    away_score: int


class PlayerGameLogRow(BaseModel):
    season: str
    player_id: int
    player_name: str
    team_id: int
    team_abbreviation: str
    game_id: str
    game_date: str
    matchup: str
    wl: str
    min: int
    fgm: int
    fga: int
    fg_pct: float | None
    fg3m: int
    fg3a: int
    fg3_pct: float | None
    ftm: int
    fta: int
    ft_pct: float | None
    oreb: int
    dreb: int
    reb: int
    ast: int
    stl: int
    blk: int
    tov: int
    pf: int
    pts: int
    plus_minus: float | None


class TeamGameLogRow(BaseModel):
    season: str
    team_id: int
    team_abbreviation: str
    team_name: str
    game_id: str
    game_date: str
    matchup: str
    wl: str
    min: int
    fgm: int
    fga: int
    fg_pct: float | None
    fg3m: int
    fg3a: int
    fg3_pct: float | None
    ftm: int
    fta: int
    ft_pct: float | None
    oreb: int
    dreb: int
    reb: int
    ast: int
    stl: int
    blk: int
    tov: int
    pf: int
    pts: int
    plus_minus: float | None


class PlayerSeasonRow(BaseModel):
    season: str
    player_id: int
    player_name: str
    team_id: int
    gp: int
    min: float
    pts: int
    reb: int
    ast: int
    stl: int
    blk: int
    tov: int
    fg_pct: float | None
    fg3_pct: float | None
    ft_pct: float | None
    usg_pct: float | None
    ts_pct: float | None
    ast_pct: float | None
    oreb_pct: float | None
    dreb_pct: float | None
    pie: float | None


ASK_TABLE_SCHEMAS: dict[str, type[BaseModel]] = {
    "players": PlayerRow,
    "teams": TeamRow,
    "games": GameRow,
    "player_game_logs": PlayerGameLogRow,
    "team_game_logs": TeamGameLogRow,
    "player_seasons": PlayerSeasonRow,
}


def assert_columns_match(table_name: str, columns: list[str]) -> None:
    """Fast sanity check: the DataFrame's columns are exactly the pydantic
    model's fields (order-independent). Raises AssertionError with a clear
    diff on mismatch, instead of silently exporting a table that's drifted
    from its documented contract.
    """
    model = ASK_TABLE_SCHEMAS[table_name]
    expected = set(model.model_fields.keys())
    actual = set(columns)
    if expected != actual:
        missing = expected - actual
        extra = actual - expected
        raise AssertionError(
            f"{table_name} columns don't match {model.__name__}: missing={missing}, extra={extra}"
        )
