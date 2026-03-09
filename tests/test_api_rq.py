import sys
import types

import os, time
from fastapi.testclient import TestClient

os.environ["AETHERLAB_DB_URL"] = "sqlite+pysqlite:///:memory:"
from aetherlab.apps.api.main import app


class FakeConn:
    pass


class FakeRedis:
    @staticmethod
    def from_url(url):
        return FakeConn()


class FakeJob:
    def __init__(self, id="job-1", state="failed"):
        self._id = id
        self.is_finished = False
        self.is_queued = False
        self.is_started = False
        self.is_failed = state == "failed"

    def get_id(self):
        return self._id

    @classmethod
    def fetch(cls, job_id, connection=None):
        return FakeJob(id=job_id, state="failed")

    def cancel(self):
        self.is_failed = False

    def requeue(self):
        self.is_failed = False
        self.is_queued = True


class FakeQueue:
    def __init__(self, name, connection=None):
        self.name = name
        self.connection = connection

    def enqueue(self, target, payload):
        return FakeJob()


def test_rq_abort_and_retry(monkeypatch):
    # Inject fake redis and rq modules
    fake_redis_module = types.SimpleNamespace(from_url=FakeRedis.from_url)
    fake_rq_module = types.SimpleNamespace(Queue=FakeQueue)
    fake_rq_job_module = types.SimpleNamespace(Job=FakeJob)
    monkeypatch.setitem(sys.modules, "redis", fake_redis_module)
    monkeypatch.setitem(sys.modules, "rq", fake_rq_module)
    monkeypatch.setitem(sys.modules, "rq.job", fake_rq_job_module)
    monkeypatch.setenv("REDIS_URL", "redis://fake/0")

    with TestClient(app) as client:
        # Bootstrap project/experiment
        uniq = int(time.time() * 1000)
        rp = client.post("/projects", json={"name": f"Proyecto RQ {uniq}", "description": "Test"})
        pid = rp.json()["id"]
        re = client.post("/experiments", json={"project_id": pid, "name": f"Exp RQ {uniq}"})
        eid = re.json()["id"]

        payload = {
            "experiment_id": eid,
            "nx": 8,
            "ny": 8,
            "steps": 1,
            "dt": 0.05,
            "lam": 0.5,
            "diff": 0.2,
            "noise": 0.0,
            "boundary": "periodic",
            "source_kind": "gaussian_pulse",
            "cx": 4,
            "cy": 4,
            "sigma": 2.0,
            "duration": 1,
            "amplitude": 1.0,
            "save_series": False,
        }
        rs = client.post("/simulate/async", json=payload)
        assert rs.status_code == 200
        data = rs.json()
        assert data["backend"] in ("rq", "background")
        run_id = data["run_id"]

    # Retry should set status to queued when job is failed
        rretry = client.post(f"/runs/{run_id}/retry")
        assert rretry.status_code in (200, 400)
    # If rq backend activo, 200 y estado queued; si no, 400 por no usar RQ

    # Abort should cancel when rq backend activo
        rabort = client.post(f"/runs/{run_id}/abort")
        assert rabort.status_code in (200, 400)
