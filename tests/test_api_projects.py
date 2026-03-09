from fastapi.testclient import TestClient

from aetherlab.apps.api.main import app


def test_projects_and_experiments_flow():
    client = TestClient(app)
    r = client.post("/projects", json={"name": "Proyecto Test", "description": "Desc"})
    assert r.status_code == 200
    pid = r.json()["id"]
    r = client.get("/projects")
    assert r.status_code == 200
    assert any(p["id"] == pid for p in r.json())
    r = client.post("/experiments", json={"project_id": pid, "name": "Exp 1"})
    assert r.status_code == 200
    eid = r.json()["id"]
    assert isinstance(eid, int)
    r = client.get("/experiments", params={"project_id": pid})
    assert r.status_code == 200
    assert any(e["id"] == eid for e in r.json())
