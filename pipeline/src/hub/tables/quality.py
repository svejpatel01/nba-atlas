"""Data quality checks for the canonical tables: row counts, null rates,
unique keys, and join integrity. Each check function returns a small dict
result; `run_all` assembles them into one report written to
data/tables/quality_report.json.
"""

from __future__ import annotations

from typing import Any

import polars as pl


def check_row_count(df: pl.DataFrame, name: str, min_rows: int) -> dict[str, Any]:
    n = df.height
    return {
        "check": "row_count",
        "table": name,
        "rows": n,
        "min_expected": min_rows,
        "ok": n >= min_rows,
    }


def check_null_rate(df: pl.DataFrame, name: str, column: str, max_rate: float) -> dict[str, Any]:
    if df.height == 0:
        rate = 1.0
    else:
        rate = df[column].null_count() / df.height
    return {
        "check": "null_rate",
        "table": name,
        "column": column,
        "rate": rate,
        "max_allowed": max_rate,
        "ok": rate <= max_rate,
    }


def check_unique_key(df: pl.DataFrame, name: str, columns: list[str]) -> dict[str, Any]:
    n_rows = df.height
    n_unique = df.select(columns).unique().height
    return {
        "check": "unique_key",
        "table": name,
        "columns": columns,
        "rows": n_rows,
        "unique_rows": n_unique,
        "ok": n_rows == n_unique,
    }


def check_join_integrity(
    child: pl.DataFrame, child_key: str, parent: pl.DataFrame, parent_key: str, name: str
) -> dict[str, Any]:
    """Every non-null child_key value must exist in parent[parent_key]."""
    child_keys = child.select(pl.col(child_key)).drop_nulls().unique()
    parent_keys = parent.select(pl.col(parent_key).alias(child_key)).unique()
    orphans = child_keys.join(parent_keys, on=child_key, how="anti")
    return {
        "check": "join_integrity",
        "table": name,
        "child_key": child_key,
        "parent_key": parent_key,
        "orphan_count": orphans.height,
        "ok": orphans.height == 0,
    }


def run_all(checks: list[dict[str, Any]]) -> dict[str, Any]:
    failed = [c for c in checks if not c["ok"]]
    return {
        "total_checks": len(checks),
        "failed_checks": len(failed),
        "passed": len(failed) == 0,
        "checks": checks,
    }
