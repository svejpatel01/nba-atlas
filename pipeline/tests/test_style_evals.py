import numpy as np
import polars as pl

from hub.style import evals


def test_cosine_neighbors_excludes_self_and_given_indices():
    vecs = np.array([[1.0, 0.0], [1.0, 0.01], [0.0, 1.0], [1.0, 0.02]])
    neighbors = evals._cosine_neighbors(vecs, 0, k=2)
    assert 0 not in neighbors
    assert set(neighbors) == {1, 3}

    neighbors_excl = evals._cosine_neighbors(vecs, 0, k=2, exclude={1})
    assert 1 not in neighbors_excl
    assert 3 in neighbors_excl


def test_career_continuity_recall_perfect_when_vectors_barely_move():
    # Player 1 has two adjacent seasons with nearly identical vectors, far
    # from an unrelated player 2 — should always find its own next season.
    sf = pl.DataFrame(
        {
            "player_id": [1, 1, 2],
            "season": ["2015-16", "2016-17", "2015-16"],
        }
    )
    vecs = np.array([[1.0, 1.0], [1.01, 1.0], [-5.0, -5.0]])
    result = evals.career_continuity_recall_at_k(sf, vecs, k=1)
    assert result["recall_at_k"] == 1.0
    assert result["n_evaluated"] == 1  # only player 1's 2015-16 has a "next" season present


def test_position_predictability_returns_none_when_too_few_labels():
    sf = pl.DataFrame({"x": [1]})
    vecs = np.random.default_rng(0).normal(size=(5, 3))
    result = evals.position_predictability(sf, vecs, [None, "G", None, None, None])
    assert result["accuracy"] is None


def test_position_predictability_above_chance_on_separable_classes():
    rng = np.random.default_rng(0)
    guards = rng.normal(loc=-5, size=(30, 2))
    centers = rng.normal(loc=5, size=(30, 2))
    vecs = np.vstack([guards, centers])
    positions = ["G"] * 30 + ["C"] * 30
    result = evals.position_predictability(None, vecs, positions)
    assert result["accuracy"] > result["chance_accuracy"]


def test_comp_sanity_check_excludes_own_seasons_from_the_search(monkeypatch):
    # Player A has three of their own seasons clustered tightly together —
    # without excluding A's own seasons, those three fill every k=1..3 slot
    # and the real comp (a bit farther away) never surfaces. With the
    # exclusion, the comp is found.
    sf = pl.DataFrame(
        {
            "name": ["A", "A", "A", "Comp", "Unrelated"],
            "season": ["2015-16", "2016-17", "2017-18", "2015-16", "2015-16"],
        }
    )
    vecs = np.array(
        [
            [1.00, 1.00],
            [1.01, 1.00],
            [1.02, 1.00],
            [1.20, 1.00],
            [-9.0, -9.0],
        ]
    )
    monkeypatch.setattr(evals, "KNOWN_COMPS", [("A", "Comp")])

    result_k1 = evals.comp_sanity_check(sf, vecs, k=1)
    assert result_k1["checked"] == 1
    assert result_k1["results"][0]["hit"] is True
