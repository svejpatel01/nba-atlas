"""Style-map evals (docs/player-style-map-spec.md's "Evaluation" section):
career continuity, position predictability, cluster stability, and a
hand-written comp sanity check. Each takes the already-built feature table
(with `x`/`y`/`archetype_hard` columns) plus the PCA vectors and archetype
probabilities, so it can run right after `hub.style.export` fits the models.
"""

from __future__ import annotations

import numpy as np
import polars as pl
from sklearn.metrics import adjusted_rand_score
from sklearn.mixture import GaussianMixture
from sklearn.model_selection import cross_val_score
from sklearn.neighbors import KNeighborsClassifier

# A starter hand-written comp list (widely agreed, not exhaustive — spec
# wants ~30; this is a v1 subset to extend). Each pair is (player name,
# widely-agreed comp's name); checked using each player's most recent season.
KNOWN_COMPS: list[tuple[str, str]] = [
    ("Stephen Curry", "Damian Lillard"),
    ("Giannis Antetokounmpo", "LeBron James"),
    ("Rudy Gobert", "Tyson Chandler"),
    ("Chris Paul", "Trae Young"),
    ("Klay Thompson", "Bradley Beal"),
    ("Kevin Durant", "Brandon Ingram"),
    ("Russell Westbrook", "Ja Morant"),
    ("Kevin Durant", "Paul George"),
    ("DeAndre Jordan", "Clint Capela"),
    ("James Harden", "Luka Dončić"),
]


def _cosine_neighbors(
    vecs: np.ndarray, query_idx: int, k: int, exclude: set[int] | None = None
) -> np.ndarray:
    query = vecs[query_idx]
    norms = np.linalg.norm(vecs, axis=1) * np.linalg.norm(query)
    norms[norms == 0] = 1e-9
    sims = (vecs @ query) / norms
    sims[query_idx] = -np.inf
    if exclude:
        sims[list(exclude)] = -np.inf
    return np.argsort(sims)[::-1][:k]


def career_continuity_recall_at_k(sf: pl.DataFrame, vecs: np.ndarray, k: int = 10) -> dict:
    """For each player-season, checks whether that same player's very next
    season (by season string) appears among the k nearest neighbors (cosine
    similarity) of the current season's vector.
    """
    player_ids = sf["player_id"].to_numpy()
    seasons = sf["season"].to_list()
    season_start_years = [int(s.split("-")[0]) for s in seasons]

    by_player: dict[int, list[tuple[int, int]]] = {}
    for i, (pid, year) in enumerate(zip(player_ids, season_start_years, strict=True)):
        by_player.setdefault(int(pid), []).append((year, i))

    hits = 0
    total = 0
    for entries in by_player.values():
        entries.sort()
        year_to_idx = dict(entries)
        for year, idx in entries:
            next_idx = year_to_idx.get(year + 1)
            if next_idx is None:
                continue
            total += 1
            neighbors = _cosine_neighbors(vecs, idx, k)
            if next_idx in neighbors:
                hits += 1

    recall = hits / total if total else 0.0
    return {"recall_at_k": round(recall, 4), "k": k, "n_evaluated": total}


def position_predictability(
    sf: pl.DataFrame, vecs: np.ndarray, positions: list[str | None]
) -> dict:
    """A kNN classifier's cross-validated accuracy predicting listed position
    from the style vectors. Expected to land clearly above chance but well
    short of perfect — the gap is the point (style correlates with, but
    isn't determined by, position).
    """
    mask = np.array([p is not None and p != "" for p in positions])
    if mask.sum() < 20:
        return {
            "accuracy": None,
            "n_evaluated": int(mask.sum()),
            "note": "too few labeled positions",
        }
    X = vecs[mask]
    y = np.array(positions)[mask]
    n_classes = len(set(y))
    clf = KNeighborsClassifier(n_neighbors=15)
    scores = cross_val_score(clf, X, y, cv=5)
    chance = 1.0 / n_classes
    return {
        "accuracy": round(float(scores.mean()), 4),
        "chance_accuracy": round(chance, 4),
        "n_evaluated": int(mask.sum()),
        "n_classes": n_classes,
    }


def cluster_stability(
    vecs: np.ndarray, n_components: int, hard_labels: np.ndarray, n_bootstrap: int = 5
) -> dict:
    """Refits a GMM on bootstrap resamples and measures agreement (adjusted
    Rand index) with the original hard cluster assignments on the full data.
    High and flat ARI across resamples means the archetypes aren't an
    artifact of one particular sample.
    """
    rng = np.random.default_rng(42)
    aris = []
    n = len(vecs)
    for i in range(n_bootstrap):
        sample_idx = rng.choice(n, size=n, replace=True)
        model = GaussianMixture(
            n_components=n_components, covariance_type="full", random_state=i, n_init=1
        )
        model.fit(vecs[sample_idx])
        refit_labels = model.predict(vecs)
        aris.append(adjusted_rand_score(hard_labels, refit_labels))
    return {
        "mean_ari": round(float(np.mean(aris)), 4),
        "min_ari": round(float(np.min(aris)), 4),
        "n_bootstrap": n_bootstrap,
    }


def comp_sanity_check(sf: pl.DataFrame, vecs: np.ndarray, k: int = 10) -> dict:
    """For each (player, expected comp) pair, uses the player's most recent
    season and checks whether *any* of the comp's seasons is in the top-k
    nearest neighbors. Excludes the player's own other seasons from the
    neighbor search — without that, a player's career is usually similar
    enough season to season that their own past/future seasons fill most of
    the top-10, crowding out true cross-player comps (confirmed empirically:
    without this exclusion, e.g. Rudy Gobert's top 10 was mostly other Rudy
    Gobert seasons). The real UI has the same toggle for this reason
    (docs/player-style-map-spec.md: "hiding the player's own other seasons").

    Checking *any* comp season rather than specifically the comp's own most
    recent one matters: two players' careers rarely overlap in calendar time
    (e.g. Rudy Gobert's latest season here is 2025-26, but Tyson Chandler's
    last qualifying season is 2018-19) — comparing "current Gobert" against
    "2018-19 Chandler" is exactly the comp being claimed, whereas requiring
    "current Gobert" to match "current Chandler" conflates career stage with
    style and would fail even a perfect model.
    """
    names = sf["name"].to_list()
    seasons = sf["season"].to_list()
    latest_idx: dict[str, int] = {}
    own_season_idxs: dict[str, set[int]] = {}
    for i, name in enumerate(names):
        own_season_idxs.setdefault(name, set()).add(i)
        if name not in latest_idx or seasons[i] > seasons[latest_idx[name]]:
            latest_idx[name] = i

    results = []
    hits = 0
    checked = 0
    for player, comp in KNOWN_COMPS:
        comp_idxs = own_season_idxs.get(comp)
        if player not in latest_idx or not comp_idxs:
            results.append({"player": player, "comp": comp, "checked": False})
            continue
        checked += 1
        neighbors = _cosine_neighbors(vecs, latest_idx[player], k, exclude=own_season_idxs[player])
        hit = bool(comp_idxs & set(neighbors.tolist()))
        hits += int(hit)
        results.append({"player": player, "comp": comp, "checked": True, "hit": hit})

    return {
        "hit_rate": round(hits / checked, 4) if checked else None,
        "checked": checked,
        "total_pairs": len(KNOWN_COMPS),
        "results": results,
    }


def run_all_evals(
    sf: pl.DataFrame, vecs: np.ndarray, arch_probs: np.ndarray, feature_cols: list[str]
) -> dict:
    hard_labels = sf["archetype_hard"].to_numpy()
    n_components = arch_probs.shape[1]
    return {
        "career_continuity": career_continuity_recall_at_k(sf, vecs),
        "position_predictability": position_predictability(
            sf, vecs, sf["position"].to_list() if "position" in sf.columns else [None] * sf.height
        ),
        "cluster_stability": cluster_stability(vecs, n_components, hard_labels),
        "comp_sanity": comp_sanity_check(sf, vecs),
    }
