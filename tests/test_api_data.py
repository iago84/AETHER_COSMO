import os
from pathlib import Path

import numpy as np
from fastapi.testclient import TestClient

os.environ["AETHERLAB_DB_URL"] = "sqlite+pysqlite:///:memory:"
from aetherlab.apps.api.main import app


def test_list_datasets():
    with TestClient(app) as client:
        r = client.get("/data/datasets")
        assert r.status_code == 200
        names = r.json()["datasets"]
        assert "planck" in names and "gwosc" in names and "sdss" in names


def test_load_planck_npy(tmp_path: Path):
    arr = np.random.default_rng(0).normal(size=(8, 8)).astype(np.float32)
    p = tmp_path / "map.npy"
    np.save(p.as_posix(), arr)
    with TestClient(app) as client:
        r = client.post("/data/load", json={"name": "planck", "path": p.as_posix()})
        assert r.status_code == 200
        info = r.json()["info"]
        assert info["kind"] == "map"
        s = info["summary"]
        assert s["shape"] == [8, 8]
