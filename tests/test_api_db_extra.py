import os
import time
import uuid

from fastapi.testclient import TestClient

os.environ["AETHERLAB_DB_URL"] = "sqlite+pysqlite:///:memory:"
from aetherlab.apps.api.main import app


def test_datasets_crud():
    with TestClient(app) as client:
        r = client.post("/projects", json={"name": f"PRJ-{int(time.time())}"})
        assert r.status_code == 200
        r = client.post(
            "/datasets",
            json={"name": "planck-local", "path": "/tmp/map.fits", "description": "local test"},
        )
        assert r.status_code == 200
        d = r.json()
        assert "id" in d and d["name"] == "planck-local"
        r = client.get("/datasets")
        assert r.status_code == 200
        assert any(x["id"] == d["id"] for x in r.json())


def test_model_runs_list_and_filter():
    with TestClient(app) as client:
        # Create project and experiment
        uniq = f"PRJ-{int(time.time()*1000)}-{uuid.uuid4().hex[:6]}"
        r = client.post("/projects", json={"name": uniq, "description": "x"})
        pid = r.json()["id"]
        r = client.post("/experiments", json={"project_id": pid, "name": "EXP-A"})
        eid = r.json()["id"]
        # Create model runs
        for i in range(2):
            r = client.post("/models", json={"experiment_id": eid, "model_name": "isoforest", "params": {"seed": i}})
            assert r.status_code == 200
        r = client.get("/models")
        assert r.status_code == 200
        all_models = r.json()
        assert len(all_models) >= 2
        r = client.get(f"/models?experiment_id={eid}")
        assert r.status_code == 200
        only_eid = r.json()
        assert all(m["experiment_id"] == eid for m in only_eid)
