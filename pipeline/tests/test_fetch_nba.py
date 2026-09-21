"""Tests for the nba_api endpoint wrappers, using a fake NbaFetcher so no
network call happens. These pin down the "extract" logic discovered by
inspecting live responses (see docs/decisions.md) — in particular that
PlayByPlayV3 needs its raw {headers, data} dataset, not get_normalized_dict().
"""

from hub.fetch import nba


class FakeFetcher:
    """Stands in for NbaFetcher: calls make_endpoint() and extract() itself,
    skipping the cache/throttle/retry machinery, and returns whatever extract
    returns.
    """

    timeout = 30

    def __init__(self, endpoint_factory):
        self._endpoint_factory = endpoint_factory

    def fetch(self, endpoint_name, params, make_endpoint, extract):
        endpoint = self._endpoint_factory()
        return extract(endpoint)


class FakeNormalizedEndpoint:
    def __init__(self, normalized: dict):
        self._normalized = normalized

    def get_normalized_dict(self):
        return self._normalized


def test_fetch_common_all_players_builds_dataframe():
    endpoint = FakeNormalizedEndpoint(
        {"CommonAllPlayers": [{"PERSON_ID": 1, "DISPLAY_FIRST_LAST": "A B"}]}
    )
    fetcher = FakeFetcher(lambda: endpoint)
    df = nba.fetch_common_all_players(fetcher)
    assert df.shape == (1, 2)
    assert df["PERSON_ID"][0] == 1


def test_fetch_shot_chart_team_picks_shot_chart_detail_key():
    endpoint = FakeNormalizedEndpoint(
        {
            "Shot_Chart_Detail": [{"GAME_ID": "1", "LOC_X": 0, "LOC_Y": 0}],
            "LeagueAverages": [{"SHOT_ZONE_BASIC": "Restricted Area"}],
        }
    )
    fetcher = FakeFetcher(lambda: endpoint)
    df = nba.fetch_shot_chart_team(fetcher, "2023-24", team_id=1610612743)
    assert df.shape == (1, 3)
    assert "GAME_ID" in df.columns
    assert "SHOT_ZONE_BASIC" not in df.columns


class FakePlayByPlayEndpoint:
    """Mirrors the real PlayByPlayV3: get_normalized_dict() is empty, and the
    real payload lives in .play_by_play as {headers, data}.
    """

    def get_normalized_dict(self):
        return {}

    class _DataSet:
        def get_dict(self):
            return {"headers": ["gameId", "actionNumber"], "data": [["1", 1], ["1", 2]]}

    play_by_play = _DataSet()


def test_fetch_play_by_play_uses_headers_data_shape():
    fetcher = FakeFetcher(lambda: FakePlayByPlayEndpoint())
    df = nba.fetch_play_by_play(fetcher, "0022300061")
    assert df.shape == (2, 2)
    assert df.columns == ["gameId", "actionNumber"]
    assert df["actionNumber"].to_list() == [1, 2]


def test_get_teams_returns_30_current_franchises():
    df = nba.get_teams()
    assert df.shape[0] == 30
    assert "abbreviation" in df.columns


def test_fetch_league_dash_pt_stats_builds_dataframe():
    endpoint = FakeNormalizedEndpoint({"LeagueDashPtStats": [{"PLAYER_ID": 1, "DRIVES": 100}]})
    fetcher = FakeFetcher(lambda: endpoint)
    df = nba.fetch_league_dash_pt_stats(fetcher, "2023-24", "Drives")
    assert df.shape == (1, 2)
    assert df["DRIVES"][0] == 100


def test_fetch_synergy_play_type_builds_dataframe():
    endpoint = FakeNormalizedEndpoint(
        {"SynergyPlayType": [{"PLAYER_ID": 1, "PLAY_TYPE": "Isolation", "POSS": 50}]}
    )
    fetcher = FakeFetcher(lambda: endpoint)
    df = nba.fetch_synergy_play_type(fetcher, "2023-24", "Isolation")
    assert df.shape == (1, 3)
    assert df["PLAY_TYPE"][0] == "Isolation"
