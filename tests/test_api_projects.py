import os, time
os.environ["AETHERLAB_DB_URL"] = "sqlite+pysqlite:///:memory:"
from fastapi.testclient import TestClient
from aetherlab.apps.api.main import app


def test_projects_and_experiments_flow():
    with TestClient(app) as client:
        uniq = int(time.time() * 1000)
        r = client.post("/projects", json={"name": f"Proyecto Test {uniq}", "description": "Desc"})
        assert r.status_code == 200
        pid = r.json()["id"]
        r = client.get("/projects")
        assert r.status_code == 200
        assert any(p["id"] == pid for p in r.json())
        r = client.post("/experiments", json={"project_id": pid, "name": f"Exp {uniq}"})
        assert r.status_code == 200
        eid = r.json()["id"]
        assert isinstance(eid, int)
        r = client.get("/experiments", params={"project_id": pid})
        assert r.status_code == 200
        assert any(e["id"] == eid for e in r.json())
