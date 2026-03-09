from typing import Literal

import numpy as np
from sklearn.cluster import DBSCAN
from sklearn.ensemble import IsolationForest


def isolation_forest_score(X: np.ndarray, random_state: int = 0) -> np.ndarray:
    clf = IsolationForest(n_estimators=200, contamination="auto", random_state=random_state)
    clf.fit(X)
    s = -clf.score_samples(X)
    s = (s - s.min()) / (s.max() - s.min() + 1e-12)
    return s.astype(np.float32)


def pca_outlier_score(X: np.ndarray, n_components: int = 2) -> np.ndarray:
    X = np.asarray(X, dtype=np.float32)
    mu = X.mean(axis=0, keepdims=True)
    e = np.linalg.norm(X - mu, axis=1)
    e = (e - e.min()) / (e.max() - e.min() + 1e-12)
    return e.astype(np.float32)


def dbscan_labels(
    X: np.ndarray, eps: float = 0.5, min_samples: int = 5, metric: Literal["euclidean", "cosine"] = "euclidean"
) -> np.ndarray:
    lab = DBSCAN(eps=eps, min_samples=min_samples, metric=metric).fit_predict(X)
    return lab.astype(np.int32)
