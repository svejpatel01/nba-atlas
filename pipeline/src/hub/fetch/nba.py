"""Thin wrappers around specific nba_api endpoints.

Each function fetches through `NbaFetcher` (cached, throttled, retried) and
returns a polars DataFrame. `extract` differs by endpoint: most use
`get_normalized_dict()` (a `{result_set_name: [row_dict, ...]}` mapping,
JSON-serializable and self-describing), but PlayByPlayV3 returns an empty
normalized dict for its play-by-play rows — verified live against the API —
so it's cached from its `{headers, data}` dataset instead.

Endpoint choices and parameter names are confirmed against the installed
nba_api 1.11.4 (see docs/decisions.md), not assumed from memory.
"""

from __future__ import annotations

from typing import Any

import polars as pl
from nba_api.stats.endpoints import (
    commonallplayers,
    commonplayerinfo,
    leaguedashplayerstats,
    leaguedashptstats,
    leaguegamelog,
    playbyplayv3,
    shotchartdetail,
    synergyplaytypes,
)
from nba_api.stats.static import teams as static_teams

from hub.fetch.client import NbaFetcher


def _normalized_extract(result_set: str) -> callable[[Any], dict[str, Any]]:
    def extract(endpoint: Any) -> dict[str, Any]:
        normalized = endpoint.get_normalized_dict()
        return {result_set: normalized[result_set]}

    return extract


def get_teams() -> pl.DataFrame:
    """Static list of the 30 current franchises; no network call."""
    return pl.DataFrame(static_teams.get_teams())


def fetch_common_all_players(fetcher: NbaFetcher) -> pl.DataFrame:
    """Every player who has ever appeared in an NBA game, with career from/to years."""
    params = {"is_only_current_season": 0}
    payload = fetcher.fetch(
        "commonallplayers",
        params,
        lambda: commonallplayers.CommonAllPlayers(
            is_only_current_season=0, timeout=fetcher.timeout
        ),
        _normalized_extract("CommonAllPlayers"),
    )
    return pl.DataFrame(payload["CommonAllPlayers"])


def fetch_player_bio(fetcher: NbaFetcher, player_id: int) -> pl.DataFrame:
    """One player's bio (height, weight, position, birthdate, draft, school).

    One call per player_id — there's no bulk historical-bio endpoint.
    PlayerIndex looked like the bulk option but, confirmed live,
    PlayerIndex(season="2023-24") returns only players on a *current* roster
    (141 rows) regardless of the season param, versus 572 unique players who
    actually logged a game that season per LeagueGameLog — useless for
    historical bios. CommonPlayerInfo is per-player but complete; callers
    should scope player_id to only the players that actually appear in
    player_game_logs, not the full all-time roster, to bound the call count.
    """
    params = {"player_id": player_id}
    payload = fetcher.fetch(
        "commonplayerinfo",
        params,
        lambda: commonplayerinfo.CommonPlayerInfo(player_id=player_id, timeout=fetcher.timeout),
        _normalized_extract("CommonPlayerInfo"),
    )
    return pl.DataFrame(payload["CommonPlayerInfo"])


def fetch_league_game_log(fetcher: NbaFetcher, season: str, mode: str) -> pl.DataFrame:
    """One row per player-game (mode="player") or team-game (mode="team")."""
    if mode not in ("player", "team"):
        raise ValueError(f"mode must be 'player' or 'team', got {mode!r}")
    abbr = "P" if mode == "player" else "T"
    params = {"season": season, "mode": mode, "season_type": "Regular Season"}
    payload = fetcher.fetch(
        "leaguegamelog",
        params,
        lambda: leaguegamelog.LeagueGameLog(
            season=season,
            player_or_team_abbreviation=abbr,
            season_type_all_star="Regular Season",
            timeout=fetcher.timeout,
        ),
        _normalized_extract("LeagueGameLog"),
    )
    return pl.DataFrame(payload["LeagueGameLog"])


def fetch_league_dash_player_stats(
    fetcher: NbaFetcher, season: str, measure_type: str
) -> pl.DataFrame:
    """Season-aggregate per-player stats. measure_type: "Base" or "Advanced"."""
    params = {"season": season, "measure_type": measure_type, "per_mode": "Totals"}
    payload = fetcher.fetch(
        "leaguedashplayerstats",
        params,
        lambda: leaguedashplayerstats.LeagueDashPlayerStats(
            season=season,
            measure_type_detailed_defense=measure_type,
            per_mode_detailed="Totals",
            season_type_all_star="Regular Season",
            timeout=fetcher.timeout,
        ),
        _normalized_extract("LeagueDashPlayerStats"),
    )
    return pl.DataFrame(payload["LeagueDashPlayerStats"])


def fetch_league_dash_pt_stats(fetcher: NbaFetcher, season: str, measure_type: str) -> pl.DataFrame:
    """Player tracking stats. measure_type one of: Possessions, Drives, Passing,
    CatchShoot, PullUpShot (the five that cover the style-map spec's ball-handling,
    shooting-mode, and touch-location feature groups — Possessions alone includes
    touches, seconds/dribbles per touch, and elbow/post/paint touch counts).
    """
    params = {"season": season, "measure_type": measure_type}
    payload = fetcher.fetch(
        "leaguedashptstats",
        params,
        lambda: leaguedashptstats.LeagueDashPtStats(
            season=season,
            player_or_team="Player",
            pt_measure_type=measure_type,
            per_mode_simple="Totals",
            season_type_all_star="Regular Season",
            timeout=fetcher.timeout,
        ),
        _normalized_extract("LeagueDashPtStats"),
    )
    return pl.DataFrame(payload["LeagueDashPtStats"])


def fetch_synergy_play_type(fetcher: NbaFetcher, season: str, play_type: str) -> pl.DataFrame:
    """Offensive play-type frequency and efficiency for one play type, one season.
    One call per play type — confirmed live there's no bulk "all play types" mode.
    Requires type_grouping_nullable='offensive' explicitly; without it the
    endpoint returns zero rows (confirmed live, not documented). The result-set
    key is "SynergyPlayType" (singular) despite the endpoint class being plural
    — also confirmed live, not documented.
    """
    params = {"season": season, "play_type": play_type}
    payload = fetcher.fetch(
        "synergyplaytypes",
        params,
        lambda: synergyplaytypes.SynergyPlayTypes(
            season=season,
            player_or_team_abbreviation="P",
            season_type_all_star="Regular Season",
            per_mode_simple="Totals",
            play_type_nullable=play_type,
            type_grouping_nullable="offensive",
            timeout=fetcher.timeout,
        ),
        _normalized_extract("SynergyPlayType"),
    )
    return pl.DataFrame(payload["SynergyPlayType"])


def fetch_shot_chart_team(fetcher: NbaFetcher, season: str, team_id: int) -> pl.DataFrame:
    """Every shot attempt for one team in one season.

    Confirmed live: querying team_id=0 (league-wide) truncates at exactly
    102,400 rows and cuts off mid-season (575 of ~1,230 games). Must query
    per team (30 calls/season) to get complete data — see docs/decisions.md.
    """
    params = {"season": season, "team_id": team_id}
    payload = fetcher.fetch(
        "shotchartdetail",
        params,
        lambda: shotchartdetail.ShotChartDetail(
            team_id=team_id,
            player_id=0,
            season_nullable=season,
            context_measure_simple="FGA",
            season_type_all_star="Regular Season",
            timeout=fetcher.timeout,
        ),
        _normalized_extract("Shot_Chart_Detail"),
    )
    return pl.DataFrame(payload["Shot_Chart_Detail"])


def fetch_play_by_play(fetcher: NbaFetcher, game_id: str) -> pl.DataFrame:
    """Every play-by-play event for one game.

    Confirmed live: PlayByPlayV3's get_normalized_dict() returns no data
    (its response shape isn't the classic resultSets format nba_api's
    normalizer expects). Cache its `.play_by_play` dataset directly instead:
    {"headers": [...], "data": [[...], ...]}.
    """
    params = {"game_id": game_id}

    def extract(endpoint: Any) -> dict[str, Any]:
        return endpoint.play_by_play.get_dict()

    payload = fetcher.fetch(
        "playbyplayv3",
        params,
        lambda: playbyplayv3.PlayByPlayV3(game_id=game_id, timeout=fetcher.timeout),
        extract,
    )
    return pl.DataFrame(payload["data"], schema=payload["headers"], orient="row")
