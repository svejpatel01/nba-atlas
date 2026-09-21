"""Turns one game's raw `PlayByPlayV3` events (see `hub.tables.build.build_pbp_events`)
into a per-event game-state sequence: period, seconds elapsed/remaining, score,
margin, and team in possession (docs/game-flow-spec.md).

`PlayByPlayV3` doesn't expose possession directly (confirmed against the raw
response), so it's derived from event sequences. Only a subset of
`action_type`s can actually change or resolve possession — "Made Shot",
"Missed Shot", "Rebound", "Turnover", "Free Throw", "Jump Ball"
(`POSSESSION_RELEVANT_TYPES`); events like "Foul", "Timeout", "Substitution"
never do. The derivation runs a single left-to-right pass over just the
relevant events (so an intervening "Foul" between a made basket and its
and-1 free throw doesn't break the lookahead below), then that resolved
value is forward-filled back onto every event, relevant or not.

Rules, in the order applied:

- **Jump Ball**: possession is unknown until whichever team acts in the next
  relevant event (there's no reliable team field on the jump ball event
  itself — confirmed live, the `team_id` on a "Jump Ball" row is one of the
  two jumping players', not the tip recipient's).
- **Missed Shot**: no change yet; unresolved until the following Rebound.
- **Made Shot**: possession flips to the shooting team's opponent, *unless*
  the next relevant event is a Free Throw for the same team (an and-1) — in
  that case the flip is deferred to the free-throw logic below.
- **Free Throw**: only the last attempt in a trip (parsed from
  `sub_type`, e.g. "Free Throw 2 of 2"; a trip with no "N of M" — technical,
  most flagrant-1 cases — is itself the last/only attempt) can change
  possession: a make flips to the opponent, a miss is left unresolved for
  the following Rebound. Makes/misses aren't in `shot_result` for free
  throws (confirmed empty for every FT row); parsed from the "MISS " prefix
  on `description` instead, the only place it's recorded.
- **Rebound**: possession becomes the rebounding team, whether it's an
  offensive or defensive board — the raw data doesn't label which (`sub_type`
  is just "Normal Rebound" or "Unknown"), but it doesn't need to: either way
  the team on the rebound event now has the ball.
- **Turnover**: flips to the opponent.

**Known simplifications** (documented rather than silently assumed —
validate against more hand-checked games before leaning on this heavily):
period-boundary possession (who gets the ball to start Q2-Q4, which
alternates by rule rather than being re-tipped) isn't specially modeled —
it just carries forward from the prior period's last resolved event, which
is usually but not always right. Technical free throws don't force a
possession change even when they're the "last" attempt in their trip, since
a technical FT doesn't cost the fouled-against team its normal possession.
Team-level dead-ball rebounds and rare event orderings (replay reviews,
double technicals) aren't specially handled.
"""

from __future__ import annotations

import re

import polars as pl

REGULATION_PERIODS = 4
REGULATION_PERIOD_SECONDS = 12 * 60
OT_PERIOD_SECONDS = 5 * 60

POSSESSION_RELEVANT_TYPES = {
    "Made Shot",
    "Missed Shot",
    "Rebound",
    "Turnover",
    "Free Throw",
    "Jump Ball",
}

_CLOCK_RE = re.compile(r"^PT(\d+)M([\d.]+)S$")
_FT_TRIP_RE = re.compile(r"(\d+)\s+of\s+(\d+)")


def parse_clock_to_seconds(clock: str) -> float:
    """"PT12M00.00S" -> 720.0. Raw `clock` is an ISO-8601 duration string
    (confirmed live, not the classic "12:00" from older endpoints).
    """
    match = _CLOCK_RE.match(clock)
    if not match:
        raise ValueError(f"Unrecognized clock format: {clock!r}")
    minutes, seconds = match.groups()
    return int(minutes) * 60 + float(seconds)


def seconds_elapsed_in_game(period: int, seconds_left_in_period: float) -> float:
    """Game time played so far. Well-defined at any point without needing
    to know how many periods the game will ultimately go to.
    """
    if period <= REGULATION_PERIODS:
        return (period - 1) * REGULATION_PERIOD_SECONDS + (
            REGULATION_PERIOD_SECONDS - seconds_left_in_period
        )
    ot_index = period - REGULATION_PERIODS
    return (
        REGULATION_PERIODS * REGULATION_PERIOD_SECONDS
        + (ot_index - 1) * OT_PERIOD_SECONDS
        + (OT_PERIOD_SECONDS - seconds_left_in_period)
    )


def seconds_remaining_in_game(period: int, seconds_left_in_period: float) -> float:
    """Time remaining, on the assumption the game ends at the buzzer of the
    current period. In regulation that's remaining-until-48:00; in overtime,
    only the current OT period's remaining time counts, since a further OT
    period isn't knowable in advance — the model treats each OT period like
    its own mini-game rather than assuming a fixed number of them.
    """
    if period <= REGULATION_PERIODS:
        return (REGULATION_PERIODS - period) * REGULATION_PERIOD_SECONDS + seconds_left_in_period
    return seconds_left_in_period


def _is_last_free_throw(sub_type: str) -> bool:
    match = _FT_TRIP_RE.search(sub_type or "")
    if not match:
        return True
    made, total = int(match.group(1)), int(match.group(2))
    return made == total


def _is_missed(description: str) -> bool:
    return (description or "").strip().upper().startswith("MISS")


def _opponent(team_id: int, home_team_id: int, away_team_id: int) -> int:
    return away_team_id if team_id == home_team_id else home_team_id


def _resolve_possession_at_relevant_events(
    relevant: list[dict], home_team_id: int, away_team_id: int
) -> list[int | None]:
    valid_teams = {home_team_id, away_team_id}
    possession: int | None = None
    resolved: list[int | None] = []

    for i, ev in enumerate(relevant):
        action_type = ev["action_type"]
        team_id = ev["team_id"] if ev["team_id"] in valid_teams else None

        if action_type == "Jump Ball":
            # The event's own `team_id` is one of the two jumpers' teams,
            # not the tip recipient's (confirmed live) — resolve to None
            # here and let the *next* relevant event's fallback below seed
            # the real value, rather than falling through to that same
            # fallback on this event using its unreliable team_id.
            possession = None
            resolved.append(possession)
            continue
        elif action_type == "Missed Shot":
            pass
        elif action_type == "Made Shot":
            next_ev = relevant[i + 1] if i + 1 < len(relevant) else None
            is_and_one = (
                next_ev is not None
                and next_ev["action_type"] == "Free Throw"
                and next_ev["team_id"] == team_id
            )
            if not is_and_one and team_id is not None:
                possession = _opponent(team_id, home_team_id, away_team_id)
        elif action_type == "Free Throw":
            if _is_last_free_throw(ev["sub_type"]) and not _is_missed(ev["description"]):
                if team_id is not None:
                    possession = _opponent(team_id, home_team_id, away_team_id)
        elif action_type == "Rebound":
            if team_id is not None:
                possession = team_id
        elif action_type == "Turnover":
            if team_id is not None:
                possession = _opponent(team_id, home_team_id, away_team_id)

        if possession is None and team_id is not None:
            possession = team_id

        resolved.append(possession)

    return resolved


def build_game_states(
    events: pl.DataFrame, home_team_id: int, away_team_id: int
) -> pl.DataFrame:
    """One row per event for a single game, sorted by (period, action_number).
    `events` should already be filtered to one `game_id`.
    """
    rows = events.sort(["period", "action_number"]).to_dicts()

    relevant = [r for r in rows if r["action_type"] in POSSESSION_RELEVANT_TYPES]
    resolved_possession = _resolve_possession_at_relevant_events(
        relevant, home_team_id, away_team_id
    )
    relevant_ids = {id(r) for r in relevant}
    possession_by_id = dict(
        zip((id(r) for r in relevant), resolved_possession, strict=True)
    )

    out = []
    current_possession: int | None = None
    home_score = 0
    away_score = 0
    max_seconds_elapsed = -1.0
    for row in rows:
        # Some rows (confirmed live: stat corrections and replay reviews,
        # e.g. a technical-foul free throw appended after the "End of
        # Period" marker with a lower action_number's score, or an "Instant
        # Replay" row carrying the score from the moment under review) are
        # appended out of true chronological order — higher action_number,
        # but an earlier/incomplete score snapshot. A real score is never
        # lower than the running total, so any non-increasing update is one
        # of these artifacts and is ignored rather than trusted.
        if row["score_home"] not in (None, ""):
            parsed_home = int(row["score_home"])
            if parsed_home >= home_score:
                home_score = parsed_home
        if row["score_away"] not in (None, ""):
            parsed_away = int(row["score_away"])
            if parsed_away >= away_score:
                away_score = parsed_away

        if id(row) in relevant_ids:
            current_possession = possession_by_id[id(row)]

        seconds_left = parse_clock_to_seconds(row["clock"])
        period = row["period"]
        seconds_elapsed = seconds_elapsed_in_game(period, seconds_left)

        # Confirmed live: a small number of events (duplicate/retroactively
        # logged plays — e.g. a "Turnover" whose own `clock` reads mid-Q4
        # but whose `action_number` places it in the stream right before
        # the "End of Period" marker) have a stream position that
        # contradicts their own clock field. `home_score`/`margin`/
        # `possession` above are correct for this row (derived from true
        # stream order), but emitting its clock-derived `seconds_elapsed`
        # would make the game clock jump backward — corrupting the
        # win-probability series' x-axis and, since top-play detection
        # diffs consecutive rows, fabricating a large swing out of two
        # states that were never really adjacent in time. Dropped rather
        # than re-timestamped, since there's no reliable way to know where
        # in the true sequence a mis-logged event actually belongs.
        if seconds_elapsed < max_seconds_elapsed:
            continue
        max_seconds_elapsed = seconds_elapsed

        out.append(
            {
                "game_id": row["game_id"],
                "action_number": row["action_number"],
                "period": period,
                "seconds_left_in_period": seconds_left,
                "seconds_elapsed": seconds_elapsed,
                "seconds_remaining": seconds_remaining_in_game(period, seconds_left),
                "home_score": home_score,
                "away_score": away_score,
                "margin": home_score - away_score,
                "possession_team_id": current_possession,
                "action_type": row["action_type"],
                "description": row["description"],
            }
        )
    return pl.DataFrame(out)
