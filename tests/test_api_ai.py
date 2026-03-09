import os

from fastapi.testclient import TestClient

os.environ["AETHERLAB_DB_URL"] = "sqlite+pysqlite:///:memory:"
from aetherlab.apps.api.main import app


def test_outlier_score_isoforest():
    with TestClient(app) as client:
        X = [[0.0, 0.0], [0.1, -0.1], [8.0, 7.9], [8.2, 8.1]]
        r = client.post("/ai/outlier-score", json={"method": "isoforest", "X": X})
        assert r.status_code == 200
        s = r.json()["scores"]
        assert len(s) == len(X)
        # Los outliers deben estar entre los últimos dos puntos
        top1 = max(range(len(s)), key=lambda i: s[i])
        assert top1 in (2, 3)


def test_dbscan_labels():
    with TestClient(app) as client:
        X = [[0.0, 0.0], [0.1, 0.0], [8.0, 8.0], [8.1, 8.0]]
        r = client.post("/ai/dbscan", json={"X": X, "eps": 0.5, "min_samples": 2})
        assert r.status_code == 200
        labels = r.json()["labels"]
        assert len(labels) == len(X)
