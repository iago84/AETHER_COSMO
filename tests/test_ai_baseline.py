import numpy as np

from aetherlab.packages.aether_ai.baseline import dbscan_labels, isolation_forest_score, pca_outlier_score


def test_isolation_forest_detects_outliers():
    rng = np.random.default_rng(0)
    X_in = rng.normal(0, 1, size=(100, 2)).astype(np.float32)
    X_out = rng.normal(8, 0.5, size=(5, 2)).astype(np.float32)
    X = np.vstack([X_in, X_out])
    s = isolation_forest_score(X)
    idx = np.argsort(s)[-5:]
    assert set(idx.tolist()) == set(range(100, 105))


def test_pca_outlier_score_marks_outliers_high():
    rng = np.random.default_rng(1)
    X_in = rng.normal(0, 1, size=(80, 3)).astype(np.float32)
    X_out = rng.normal(7, 0.2, size=(4, 3)).astype(np.float32)
    X = np.vstack([X_in, X_out])
    e = pca_outlier_score(X, n_components=2)
    idx = np.argsort(e)[-4:]
    assert set(idx.tolist()) == set(range(80, 84))


def test_dbscan_labels_shape():
    rng = np.random.default_rng(2)
    X = rng.normal(0, 1, size=(50, 2)).astype(np.float32)
    lab = dbscan_labels(X, eps=0.8, min_samples=4)
    assert lab.shape == (50,)
