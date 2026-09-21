"""PCA style vectors, Gaussian-mixture archetypes, and a UMAP 2D layout for
the player style map (docs/player-style-map-spec.md's "Model" section).
"""

from __future__ import annotations

import numpy as np
import umap
from sklearn.decomposition import PCA
from sklearn.mixture import GaussianMixture


def fit_pca(feature_matrix: np.ndarray, variance_target: float = 0.90) -> PCA:
    """Keeps enough components to explain `variance_target` of the variance
    (spec expects 10-15 components at 90%).
    """
    pca = PCA(n_components=variance_target, svd_solver="full", random_state=42)
    pca.fit(feature_matrix)
    return pca


def choose_gmm_components(
    style_vectors: np.ndarray, k_range: range = range(6, 15)
) -> tuple[GaussianMixture, dict[int, float]]:
    """Fits a GaussianMixture for each k in `k_range` and picks the one with
    the lowest BIC (spec: "choose the number of components using BIC plus
    judgment (likely 8-12)"). Returns the winning model and every k's BIC so
    the choice is inspectable/loggable, not just asserted.
    """
    bics: dict[int, float] = {}
    best_model: GaussianMixture | None = None
    best_bic = float("inf")
    for k in k_range:
        model = GaussianMixture(n_components=k, covariance_type="full", random_state=42, n_init=3)
        model.fit(style_vectors)
        bic = model.bic(style_vectors)
        bics[k] = bic
        if bic < best_bic:
            best_bic = bic
            best_model = model
    assert best_model is not None
    return best_model, bics


def fit_umap(style_vectors: np.ndarray) -> umap.UMAP:
    """Spec's starting parameters: n_neighbors=30, min_dist=0.3, Euclidean,
    fixed seed, so the layout is reproducible run to run.
    """
    reducer = umap.UMAP(
        n_neighbors=30,
        min_dist=0.3,
        metric="euclidean",
        random_state=42,
    )
    reducer.fit(style_vectors)
    return reducer
