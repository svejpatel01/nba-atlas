import polars as pl
import pytest

from hub.gameflow import parse

HOME = 1
AWAY = 2


def _events(rows: list[dict]) -> pl.DataFrame:
    """Fills in the columns build_game_states needs that most test cases
    don't care about, so each test only spells out what it's testing.
    """
    defaults = {
        "game_id": "0000000001",
        "score_home": "",
        "score_away": "",
        "sub_type": "",
        "description": "",
    }
    full_rows = []
    for i, r in enumerate(rows, start=1):
        row = {**defaults, "action_number": i, **r}
        full_rows.append(row)
    return pl.DataFrame(full_rows)


# --- clock parsing -----------------------------------------------------


def test_parse_clock_to_seconds():
    assert parse.parse_clock_to_seconds("PT12M00.00S") == 720.0
    assert parse.parse_clock_to_seconds("PT00M45.30S") == 45.3
    assert parse.parse_clock_to_seconds("PT07M40.00S") == 460.0


def test_parse_clock_rejects_unknown_format():
    with pytest.raises(ValueError):
        parse.parse_clock_to_seconds("12:00")


# --- elapsed / remaining time -------------------------------------------


def test_seconds_elapsed_start_of_game():
    assert parse.seconds_elapsed_in_game(1, 720.0) == 0.0


def test_seconds_elapsed_end_of_regulation():
    assert parse.seconds_elapsed_in_game(4, 0.0) == 48 * 60


def test_seconds_elapsed_into_overtime():
    # end of the 1st OT period
    assert parse.seconds_elapsed_in_game(5, 0.0) == 48 * 60 + 5 * 60
    # 2 minutes into the 2nd OT period
    assert parse.seconds_elapsed_in_game(6, 3 * 60) == 48 * 60 + 5 * 60 + 2 * 60


def test_seconds_remaining_start_and_end_of_regulation():
    assert parse.seconds_remaining_in_game(1, 720.0) == 48 * 60
    assert parse.seconds_remaining_in_game(4, 0.0) == 0.0


def test_seconds_remaining_in_overtime_uses_only_current_ot_period():
    assert parse.seconds_remaining_in_game(5, 300.0) == 300.0
    assert parse.seconds_remaining_in_game(6, 150.0) == 150.0


# --- possession derivation, via build_game_states -----------------------


def test_made_shot_flips_possession():
    events = _events(
        [
            {"period": 1, "clock": "PT12M00.00S", "team_id": HOME, "action_type": "Made Shot"},
        ]
    )
    out = parse.build_game_states(events, HOME, AWAY)
    assert out["possession_team_id"][0] == AWAY


def test_missed_shot_then_defensive_rebound_flips():
    events = _events(
        [
            {"period": 1, "clock": "PT12M00.00S", "team_id": HOME, "action_type": "Missed Shot"},
            {"period": 1, "clock": "PT11M55.00S", "team_id": AWAY, "action_type": "Rebound"},
        ]
    )
    out = parse.build_game_states(events, HOME, AWAY)
    assert out["possession_team_id"][1] == AWAY


def test_missed_shot_then_offensive_rebound_retains():
    events = _events(
        [
            {"period": 1, "clock": "PT12M00.00S", "team_id": HOME, "action_type": "Missed Shot"},
            {"period": 1, "clock": "PT11M55.00S", "team_id": HOME, "action_type": "Rebound"},
        ]
    )
    out = parse.build_game_states(events, HOME, AWAY)
    assert out["possession_team_id"][1] == HOME


def test_turnover_flips_possession():
    events = _events(
        [
            {"period": 1, "clock": "PT12M00.00S", "team_id": HOME, "action_type": "Turnover"},
        ]
    )
    out = parse.build_game_states(events, HOME, AWAY)
    assert out["possession_team_id"][0] == AWAY


def test_and_one_defers_flip_to_the_free_throw():
    # Made shot by HOME, then an intervening Foul (not possession-relevant,
    # exercises that the and-1 lookahead skips over it), then HOME's FT.
    events = _events(
        [
            {"period": 1, "clock": "PT10M00.00S", "team_id": HOME, "action_type": "Made Shot"},
            {"period": 1, "clock": "PT10M00.00S", "team_id": AWAY, "action_type": "Foul"},
            {
                "period": 1,
                "clock": "PT10M00.00S",
                "team_id": HOME,
                "action_type": "Free Throw",
                "sub_type": "Free Throw 1 of 1",
                "description": "Jones Free Throw 1 of 1 (3 PTS)",
            },
        ]
    )
    out = parse.build_game_states(events, HOME, AWAY)
    # Right after the made shot, possession must NOT have flipped yet.
    assert out["possession_team_id"][0] == HOME
    # After the made free throw, it flips.
    assert out["possession_team_id"][2] == AWAY


def test_missed_final_free_throw_leaves_possession_pending_for_rebound():
    events = _events(
        [
            {
                "period": 1,
                "clock": "PT10M00.00S",
                "team_id": HOME,
                "action_type": "Free Throw",
                "sub_type": "Free Throw 2 of 2",
                "description": "MISS Jones Free Throw 2 of 2",
            },
            {"period": 1, "clock": "PT09M58.00S", "team_id": AWAY, "action_type": "Rebound"},
        ]
    )
    out = parse.build_game_states(events, HOME, AWAY)
    assert out["possession_team_id"][1] == AWAY


def test_non_last_free_throw_does_not_change_possession():
    events = _events(
        [
            {"period": 1, "clock": "PT10M00.00S", "team_id": HOME, "action_type": "Turnover"},
            {
                "period": 1,
                "clock": "PT09M50.00S",
                "team_id": AWAY,
                "action_type": "Free Throw",
                "sub_type": "Free Throw 1 of 2",
                "description": "Smith Free Throw 1 of 2",
            },
        ]
    )
    out = parse.build_game_states(events, HOME, AWAY)
    # Possession set by the turnover (AWAY); the 1-of-2 free throw shouldn't
    # move it even though AWAY is the team shooting.
    assert out["possession_team_id"][0] == AWAY
    assert out["possession_team_id"][1] == AWAY


def test_jump_ball_resolved_by_next_relevant_event():
    events = _events(
        [
            {"period": 1, "clock": "PT12M00.00S", "team_id": 0, "action_type": "Jump Ball"},
            {"period": 1, "clock": "PT11M57.00S", "team_id": AWAY, "action_type": "Missed Shot"},
        ]
    )
    out = parse.build_game_states(events, HOME, AWAY)
    assert out["possession_team_id"][0] is None
    assert out["possession_team_id"][1] == AWAY


def test_jump_ball_own_team_id_is_not_trusted_as_the_tip_winner():
    # Real PlayByPlayV3 data: the Jump Ball row's own team_id is one of the
    # two jumpers' teams, not necessarily the tip recipient's. Here it's
    # HOME, but AWAY is the team that actually acts next (got the tip) —
    # possession must resolve from that next event, not the jump ball row.
    events = _events(
        [
            {"period": 1, "clock": "PT12M00.00S", "team_id": HOME, "action_type": "Jump Ball"},
            {"period": 1, "clock": "PT11M57.00S", "team_id": AWAY, "action_type": "Missed Shot"},
        ]
    )
    out = parse.build_game_states(events, HOME, AWAY)
    assert out["possession_team_id"][0] is None
    assert out["possession_team_id"][1] == AWAY


def test_non_relevant_events_forward_fill_possession():
    events = _events(
        [
            {"period": 1, "clock": "PT12M00.00S", "team_id": HOME, "action_type": "Made Shot"},
            {"period": 1, "clock": "PT11M50.00S", "team_id": None, "action_type": "Timeout"},
        ]
    )
    out = parse.build_game_states(events, HOME, AWAY)
    assert out["possession_team_id"][1] == AWAY


def test_score_ignores_out_of_order_stale_snapshot():
    # Real PlayByPlayV3 data: replay-review / stat-correction rows are
    # sometimes appended after the true end of a period with a *lower*
    # score than what's already been reached (e.g. a technical-foul FT
    # logged after "End of Period" carrying the pre-correction score, or an
    # Instant Replay row echoing the score from the moment under review).
    # Same clock as the prior row (so the seconds_elapsed guard alone
    # wouldn't drop it) isolates the score guard specifically.
    events = _events(
        [
            {
                "period": 4,
                "clock": "PT00M00.00S",
                "team_id": HOME,
                "action_type": "Made Shot",
                "score_home": "100",
                "score_away": "90",
            },
            {
                "period": 4,
                "clock": "PT00M00.00S",
                "team_id": AWAY,
                "action_type": "Instant Replay",
                "score_home": "92",
                "score_away": "90",
            },
        ]
    )
    out = parse.build_game_states(events, HOME, AWAY)
    assert out["home_score"][1] == 100
    assert out["away_score"][1] == 90


def test_drops_events_whose_clock_contradicts_their_stream_position():
    # Real PlayByPlayV3 data: a duplicate/retroactively-logged Turnover
    # whose own clock (9:11 remaining) is far earlier than where it sits in
    # the stream (right before "End of Period", after events at :09 and
    # :00 remaining). Its home_score/margin are correct for its true stream
    # position; its seconds_elapsed is not, and must not be emitted.
    events = _events(
        [
            {
                "period": 4,
                "clock": "PT01M39.00S",
                "team_id": HOME,
                "action_type": "Free Throw",
                "sub_type": "Free Throw 2 of 2",
                "description": "Holiday Free Throw 2 of 2",
                "score_home": "122",
                "score_away": "106",
            },
            {
                "period": 4,
                "clock": "PT00M09.70S",
                "team_id": AWAY,
                "action_type": "Free Throw",
                "sub_type": "Free Throw 2 of 2",
                "description": "Raynaud Free Throw 2 of 2",
                "score_home": "122",
                "score_away": "110",
            },
            {
                "period": 4,
                "clock": "PT09M11.00S",
                "team_id": HOME,
                "action_type": "Turnover",
                "description": "Plowden Lost Ball Turnover",
            },
            {
                "period": 4,
                "clock": "PT00M00.00S",
                "team_id": 0,
                "action_type": "period",
                "description": "End of 4th Period",
                "score_home": "122",
                "score_away": "110",
            },
        ]
    )
    out = parse.build_game_states(events, HOME, AWAY)
    # The mis-logged turnover row is dropped entirely.
    assert out.height == 3
    assert "Plowden Lost Ball Turnover" not in out["description"].to_list()
    # seconds_elapsed stays non-decreasing across the remaining rows.
    elapsed = out["seconds_elapsed"].to_list()
    assert elapsed == sorted(elapsed)


def test_score_forward_fills_between_scoring_events():
    events = _events(
        [
            {
                "period": 1,
                "clock": "PT12M00.00S",
                "team_id": HOME,
                "action_type": "Made Shot",
                "score_home": "2",
                "score_away": "0",
            },
            {"period": 1, "clock": "PT11M50.00S", "team_id": AWAY, "action_type": "Missed Shot"},
        ]
    )
    out = parse.build_game_states(events, HOME, AWAY)
    assert out["home_score"][1] == 2
    assert out["away_score"][1] == 0
    assert out["margin"][1] == 2
