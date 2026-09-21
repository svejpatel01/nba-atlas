import polars as pl

from hub.tables import quality


def test_check_row_count_ok_and_not_ok():
    df = pl.DataFrame({"a": [1, 2, 3]})
    assert quality.check_row_count(df, "t", min_rows=3)["ok"] is True
    assert quality.check_row_count(df, "t", min_rows=4)["ok"] is False


def test_check_null_rate():
    df = pl.DataFrame({"a": [1, None, None, 4]})
    result = quality.check_null_rate(df, "t", "a", max_rate=0.5)
    assert result["rate"] == 0.5
    assert result["ok"] is True
    assert quality.check_null_rate(df, "t", "a", max_rate=0.25)["ok"] is False


def test_check_unique_key():
    unique_df = pl.DataFrame({"id": [1, 2, 3]})
    dup_df = pl.DataFrame({"id": [1, 1, 2]})
    assert quality.check_unique_key(unique_df, "t", ["id"])["ok"] is True
    result = quality.check_unique_key(dup_df, "t", ["id"])
    assert result["ok"] is False
    assert result["rows"] == 3
    assert result["unique_rows"] == 2


def test_check_join_integrity_detects_orphans():
    parent = pl.DataFrame({"player_id": [1, 2, 3]})
    clean_child = pl.DataFrame({"player_id": [1, 2]})
    dirty_child = pl.DataFrame({"player_id": [1, 99]})

    clean_result = quality.check_join_integrity(clean_child, "player_id", parent, "player_id", "t")
    assert clean_result["ok"] is True
    assert clean_result["orphan_count"] == 0

    dirty_result = quality.check_join_integrity(dirty_child, "player_id", parent, "player_id", "t")
    assert dirty_result["ok"] is False
    assert dirty_result["orphan_count"] == 1


def test_run_all_aggregates_pass_and_fail():
    checks = [{"ok": True}, {"ok": False}, {"ok": True}]
    report = quality.run_all(checks)
    assert report["total_checks"] == 3
    assert report["failed_checks"] == 1
    assert report["passed"] is False
