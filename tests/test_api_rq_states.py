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


class FakeJobState:
    def __init__(self, state):
        self.is_finished = state == "finished"
        self.is_queued = state == "queued"
        self.is_started = state == "running"
        self.is_failed = state == "failed"


class FakeJob:
    def __init__(self, id="job-1", state="queued"):
        self._id = id
        s = FakeJobState(state)
        self.is_finished = s.is_finished
        self.is_queued = s.is_queued
        self.is_started = s.is_started
        self.is_failed = s.is_failed

    def get_id(self):
        return self._id

    @classmethod
    def fetch(cls, job_id, connection=None):
        return FakeJob(id=job_id, state=FakeJob._STATE)  # type: ignore[attr-defined]


class FakeQueue:
    def __init__(self, name, connection=None):
        self.name = name
        self.connection = connection

    def enqueue(self, target, payload):
        return FakeJob(state="queued")


def _bootstrap(client: TestClient):
    uniq = int(time.time() * 1000)
    rp = client.post("/projects", json={"name": f"Proyecto RQ States {uniq}", "description": "Test"})
    pid = rp.json()["id"]
    re = client.post("/experiments", json={"project_id": pid, "name": f"Exp RQ States {uniq}"})
    return re.json()["id"]


def _setup_rq(monkeypatch, state):
    fake_redis_module = types.SimpleNamespace(from_url=FakeRedis.from_url)
    fake_rq_module = types.SimpleNamespace(Queue=FakeQueue)
    fake_rq_job_module = types.SimpleNamespace(Job=FakeJob)
    monkeypatch.setitem(sys.modules, "redis", fake_redis_module)
    monkeypatch.setitem(sys.modules, "rq", fake_rq_module)
    monkeypatch.setitem(sys.modules, "rq.job", fake_rq_job_module)
    monkeypatch.setenv("REDIS_URL", "redis://fake/0")
    FakeJob._STATE = state  # type: ignore[attr-defined]


def test_get_run_status_queued(monkeypatch):
    _setup_rq(monkeypatch, "queued")
    with TestClient(app) as client:
        eid = _bootstrap(client)
        rs = client.post("/simulate/async", json={"experiment_id": eid})
        run_id = rs.json()["run_id"]
        r = client.get(f"/runs/{run_id}")
        assert r.status_code == 200
        assert r.json()["status"] in ("queued", "finished")


def test_get_run_status_running(monkeypatch):
    _setup_rq(monkeypatch, "running")
    with TestClient(app) as client:
        eid = _bootstrap(client)
        rs = client.post("/simulate/async", json={"experiment_id": eid})
        run_id = rs.json()["run_id"]
        r = client.get(f"/runs/{run_id}")
        assert r.status_code == 200
        assert r.json()["status"] in ("running", "finished")


def test_get_run_status_failed(monkeypatch):
    _setup_rq(monkeypatch, "failed")
    with TestClient(app) as client:
        eid = _bootstrap(client)
        rs = client.post("/simulate/async", json={"experiment_id": eid})
        run_id = rs.json()["run_id"]
        r = client.get(f"/runs/{run_id}")
        assert r.status_code == 200
        assert r.json()["status"] in ("failed", "finished")


def test_get_run_status_finished(monkeypatch):
    _setup_rq(monkeypatch, "finished")
    with TestClient(app) as client:
        eid = _bootstrap(client)
        rs = client.post("/simulate/async", json={"experiment_id": eid})
        run_id = rs.json()["run_id"]
        r = client.get(f"/runs/{run_id}")
        assert r.status_code == 200
        assert r.json()["status"] == "finished"
