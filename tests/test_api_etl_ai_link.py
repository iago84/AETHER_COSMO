import os
from pathlib import Path

import numpy as np
from fastapi.testclient import TestClient

os.environ["AETHERLAB_DB_URL"] = "sqlite+pysqlite:///:memory:"
from aetherlab.apps.api.main import app


def test_link_dataset_to_experiment_and_list(tmp_path: Path):
    with TestClient(app) as client:
        rp = client.post("/projects", json={"name": "P-ETL"})
        pid = rp.json()["id"]
        re = client.post("/experiments", json={"project_id": pid, "name": "E-ETL"})
        eid = re.json()["id"]
        p = tmp_path / "map.npy"
        np.save(p.as_posix(), np.random.default_rng(0).normal(size=(8, 8)).astype(np.float32))
        rd = client.post("/datasets", json={"name": "planck-local", "path": p.as_posix()})
        did = rd.json()["id"]
        rl = client.post(f"/experiments/{eid}/datasets/link?dataset_id={did}")
        assert rl.status_code == 200
        rlist = client.get(f"/experiments/{eid}/datasets")
        assert rlist.status_code == 200
        links = rlist.json()
        assert any(x["dataset_id"] == did for x in links)


def test_ai_run_on_run_and_download(tmp_path: Path):
    with TestClient(app) as client:
        rp = client.post("/projects", json={"name": "P-AI-Run"})
        pid = rp.json()["id"]
        re = client.post("/experiments", json={"project_id": pid, "name": "E-AI-Run"})
        eid = re.json()["id"]
        payload = {
            "experiment_id": eid,
            "nx": 16,
            "ny": 16,
            "steps": 5,
            "dt": 0.05,
            "lam": 0.5,
            "diff": 0.2,
            "noise": 0.0,
            "boundary": "periodic",
            "source_kind": "gaussian_pulse",
            "cx": 8,
            "cy": 8,
            "sigma": 3.0,
            "duration": 3,
            "amplitude": 1.0,
            "save_series": False,
        }
        rs = client.post("/simulate/simple", json=payload)
        run_id = rs.json()["run_id"]
        r = client.post("/ai/run-on-run", json={"run_id": run_id, "method": "isoforest"})
        assert r.status_code == 200
        path = r.json()["path"]
        d = client.get(f"/ai/download?path={path}")
        assert d.status_code == 200
        alist = client.get("/artifacts", params={"run_id": run_id})
        assert alist.status_code == 200
        a0 = alist.json()[0]
        dl = client.get(f"/artifacts/{a0['id']}/download")
        assert dl.status_code == 200


def test_ai_run_on_dataset_and_download(tmp_path: Path):
    with TestClient(app) as client:
        rp = client.post("/projects", json={"name": "P-AI-DS"})
        pid = rp.json()["id"]
        re = client.post("/experiments", json={"project_id": pid, "name": "E-AI-DS"})
        eid = re.json()["id"]
        p = tmp_path / "map.npy"
        np.save(p.as_posix(), np.random.default_rng(0).normal(size=(8, 8)).astype(np.float32))
        rd = client.post("/datasets", json={"name": "planck-local", "path": p.as_posix()})
        did = rd.json()["id"]
        rl = client.post(f"/experiments/{eid}/datasets/link?dataset_id={did}")
        assert rl.status_code == 200
        r = client.post("/ai/run-on-dataset", json={"dataset_id": did, "method": "mean_dist"})
        assert r.status_code == 200
        path = r.json()["path"]
        d = client.get(f"/ai/download?path={path}")
        assert d.status_code == 200
        alist = client.get("/artifacts", params={"dataset_id": did})
        assert alist.status_code == 200
        a0 = alist.json()[0]
        dl = client.get(f"/artifacts/{a0['id']}/download")
        assert dl.status_code == 200


def test_etl_dataset_endpoint(tmp_path: Path):
    with TestClient(app) as client:
        rp = client.post("/projects", json={"name": "P-ETL-EP"})
        pid = rp.json()["id"]
        _ = client.post("/experiments", json={"project_id": pid, "name": "E-ETL-EP"})
        p = tmp_path / "map.npy"
        np.save(p.as_posix(), np.random.default_rng(0).normal(size=(8, 8)).astype(np.float32))
        rd = client.post("/datasets", json={"name": "planck-local", "path": p.as_posix()})
        did = rd.json()["id"]
        r = client.post("/etl/dataset", json={"dataset_id": did, "normalize": "minmax", "qc": True})
        assert r.status_code == 200
        o = r.json()
        assert Path(o["features_path"]).exists()
        assert Path(o["qc_path"]).exists()
        assert o["artifact_features_id"] is not None
