"""Phase 0 smoke test: package imports cleanly."""

import hub


def test_package_imports() -> None:
    assert hub is not None
