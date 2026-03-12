from typing import Literal

import numpy as np
from sklearn.cluster import DBSCAN
from sklearn.ensemble import IsolationForest


def fit_isolation_forest(
    X: np.ndarray,
    *,
    random_state: int = 0,
    n_estimators: int = 200,
    contamination: str = "auto",
) -> tuple[IsolationForest, np.ndarray]:
    clf = IsolationForest(n_estimators=n_estimators, contamination=contamination, random_state=random_state)
    clf.fit(X)
    s = -clf.score_samples(X)
    s = (s - s.min()) / (s.max() - s.min() + 1e-12)
    return clf, s.astype(np.float32)


def isolation_forest_score(X: np.ndarray, random_state: int = 0) -> np.ndarray:
    _, s = fit_isolation_forest(X, random_state=random_state)
    return s


def fit_mean_dist_model(X: np.ndarray) -> tuple[dict, np.ndarray]:
    X = np.asarray(X, dtype=np.float32)
    mu = X.mean(axis=0, keepdims=True)
    e = np.linalg.norm(X - mu, axis=1)
    e = (e - e.min()) / (e.max() - e.min() + 1e-12)
    model = {"mu": mu.astype(np.float32)}
    return model, e.astype(np.float32)


def pca_outlier_score(X: np.ndarray, n_components: int = 2) -> np.ndarray:
    _, s = fit_mean_dist_model(X)
    return s


def dbscan_labels(
    X: np.ndarray, eps: float = 0.5, min_samples: int = 5, metric: Literal["euclidean", "cosine"] = "euclidean"
) -> np.ndarray:
    lab = DBSCAN(eps=eps, min_samples=min_samples, metric=metric).fit_predict(X)
    return lab.astype(np.int32)
