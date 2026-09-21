import datetime

from hub.tables import seasons


def test_format_season():
    assert seasons.format_season(2015) == "2015-16"
    assert seasons.format_season(2099) == "2099-00"


def test_season_range():
    assert seasons.season_range(2023, 2025) == ["2023-24", "2024-25", "2025-26"]


def test_current_season_in_offseason_is_the_season_just_played():
    assert seasons.current_season(datetime.date(2026, 9, 16)) == "2025-26"


def test_current_season_mid_season_is_the_season_in_progress():
    assert seasons.current_season(datetime.date(2026, 11, 1)) == "2026-27"
    assert seasons.current_season(datetime.date(2027, 3, 1)) == "2026-27"


def test_most_recent_completed_in_offseason_is_the_season_just_played():
    assert seasons.most_recent_completed_season_start_year(datetime.date(2026, 9, 16)) == 2025


def test_most_recent_completed_mid_season_is_the_prior_season():
    assert seasons.most_recent_completed_season_start_year(datetime.date(2026, 11, 1)) == 2025
    assert seasons.most_recent_completed_season_start_year(datetime.date(2027, 3, 1)) == 2025


def test_most_recent_completed_next_offseason_advances():
    assert seasons.most_recent_completed_season_start_year(datetime.date(2027, 8, 1)) == 2026
