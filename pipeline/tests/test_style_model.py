import numpy as np

from hub.style import model


def _make_clustered_data(rng, n_per_cluster=40, n_features=6):
    centers = rng.uniform(-8, 8, size=(3, n_features))
    parts = [c + rng.normal(scale=0.3, size=(n_per_cluster, n_features)) for c in centers]
    return np.vstack(parts)


def test_fit_pca_reaches_variance_target():
    rng = np.random.default_rng(0)
    # Highly correlated features so a couple of components explain most variance.
    base = rng.normal(size=(200, 3))
    noise = rng.normal(scale=0.05, size=(200, 6))
    X = np.hstack([base, base]) + noise
    pca = model.fit_pca(X, variance_target=0.90)
    assert pca.explained_variance_ratio_.sum() >= 0.90
    assert pca.n_components_ <= X.shape[1]


def test_choose_gmm_components_returns_bic_for_every_k():
    rng = np.random.default_rng(1)
    X = _make_clustered_data(rng)
    gmm, bics = model.choose_gmm_components(X, k_range=range(2, 6))
    assert set(bics.keys()) == {2, 3, 4, 5}
    assert gmm.bic(X) == min(bics.values())


def test_fit_umap_produces_2d_layout_preserving_cluster_separation():
    rng = np.random.default_rng(2)
    X = _make_clustered_data(rng, n_per_cluster=30)
    reducer = model.fit_umap(X)
    layout = reducer.transform(X)
    assert layout.shape == (90, 2)
    # Points from the first synthetic cluster should sit closer to each other
    # than to points from the third (well-separated) cluster.
    from scipy.spatial.distance import cdist

    within = cdist(layout[:30], layout[:30]).mean()
    across = cdist(layout[:30], layout[60:90]).mean()
    assert within < across
