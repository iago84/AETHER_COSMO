import sys
import types

from fastapi.testclient import TestClient

from aetherlab.apps.api.main import app


class FakeConn:
    pass


class FakeRedis:
    @staticmethod
    def from_url(url):
        return FakeConn()


class FakeJob:
    @classmethod
    def fetch(cls, job_id, connection=None):
        raise RuntimeError("fetch error")


class FakeQueue:
    def __init__(self, name, connection=None):
        self.name = name
        self.connection = connection

    def enqueue(self, target, payload):
        class J:
            def get_id(self):
                return "job-err"

        return J()


def test_retry_abort_errors(monkeypatch):
    fake_redis_module = types.SimpleNamespace(from_url=FakeRedis.from_url)
    fake_rq_module = types.SimpleNamespace(Queue=FakeQueue)
    fake_rq_job_module = types.SimpleNamespace(Job=FakeJob)
    monkeypatch.setitem(sys.modules, "redis", fake_redis_module)
    monkeypatch.setitem(sys.modules, "rq", fake_rq_module)
    monkeypatch.setitem(sys.modules, "rq.job", fake_rq_job_module)
    monkeypatch.setenv("REDIS_URL", "redis://fake/0")

    client = TestClient(app)
    rp = client.post("/projects", json={"name": "Proyecto Err", "description": "Test"})
    pid = rp.json()["id"]
    re = client.post("/experiments", json={"project_id": pid, "name": "Exp Err"})
    eid = re.json()["id"]

    rs = client.post("/simulate/async", json={"experiment_id": eid})
    run_id = rs.json()["run_id"]

    rretry = client.post(f"/runs/{run_id}/retry")
    assert rretry.status_code in (200, 500, 400)

    rabort = client.post(f"/runs/{run_id}/abort")
    assert rabort.status_code in (200, 500, 400)
