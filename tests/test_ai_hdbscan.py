import json
import numpy as np
import pytest

try:
    import hdbscan  # noqa: F401
except Exception:
    pytest.skip("hdbscan not installed", allow_module_level=True)

from fastapi.testclient import TestClient

from aetherlab.apps.api.main import app


def test_hdbscan_endpoint():
    client = TestClient(app)
    a = np.random.randn(50, 2) * 0.2 + np.array([0, 0])
    b = np.random.randn(50, 2) * 0.2 + np.array([2, 2])
    X = np.vstack([a, b]).tolist()
    payload = {"X": X, "min_cluster_size": 5}
    r = client.post("/ai/hdbscan", data=json.dumps(payload))
    assert r.status_code == 200
    o = r.json()
    assert "labels" in o
