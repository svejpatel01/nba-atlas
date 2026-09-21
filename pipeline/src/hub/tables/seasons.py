"""Season string helpers. nba_api seasons are formatted "2015-16" (start year,
dash, two-digit end year).
"""

from __future__ import annotations

import datetime


def format_season(start_year: int) -> str:
    return f"{start_year}-{(start_year + 1) % 100:02d}"


def season_range(start_year: int, end_year_inclusive: int) -> list[str]:
    """e.g. season_range(2015, 2025) -> ["2015-16", ..., "2025-26"]."""
    return [format_season(y) for y in range(start_year, end_year_inclusive + 1)]


def _in_progress_season_start_year(today: datetime.date) -> int:
    """Start year of the season that has most recently started, whether or
    not it has finished yet (named by its start year: October's tip-off
    starts "this" year's season; before October, the season that tipped off
    the previous October is the reference point).
    """
    return today.year if today.month >= 10 else today.year - 1


def most_recent_completed_season_start_year(today: datetime.date | None = None) -> int:
    """The NBA season runs October -> ~June, named by its start year. In the
    July-September offseason, the season that just tipped-off-reference-year
    has already finished, so it counts as completed. From October through
    June, a season is actively being played, so the most recent *completed*
    one is the year before that.
    """
    today = today or datetime.date.today()
    start_year = _in_progress_season_start_year(today)
    if 7 <= today.month <= 9:
        return start_year
    return start_year - 1


def current_season(today: datetime.date | None = None) -> str:
    """The season with the most recent real data: during the season (or in
    the July-September offseason right after it), that's the season just
    played. Only once a new season's games start (October) does this switch
    to the new one.
    """
    today = today or datetime.date.today()
    return format_season(_in_progress_season_start_year(today))
