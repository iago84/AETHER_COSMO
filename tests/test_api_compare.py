import os
import time
from pathlib import Path

import numpy as np
from fastapi.testclient import TestClient

os.environ["AETHERLAB_DB_URL"] = "sqlite+pysqlite:///:memory:"
os.environ["MPLBACKEND"] = "Agg"
from aetherlab.apps.api.main import app


def _bootstrap_project_and_experiment(client: TestClient) -> tuple[int, int]:
    uniq = int(time.time() * 1000)
    rp = client.post("/projects", json={"name": f"Proyecto Cmp {uniq}", "description": "Test"})
    pid = rp.json()["id"]
    re = client.post("/experiments", json={"project_id": pid, "name": f"Exp Cmp {uniq}"})
    eid = re.json()["id"]
    return pid, eid


def test_compare_run_run_and_run_dataset():
    with TestClient(app) as client:
        _, eid = _bootstrap_project_and_experiment(client)
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
        assert rs.status_code == 200
        run_id = rs.json()["run_id"]

        rc = client.get("/compare/run-run", params={"run_a": run_id, "run_b": run_id})
        assert rc.status_code == 200
        metrics = rc.json()["metrics"]
        assert metrics["mse"] == 0.0
        assert metrics["mae"] == 0.0
        assert metrics["corr"] > 0.999

        rpng = client.get("/compare/run-run/figure.png", params={"run_a": run_id, "run_b": run_id})
        assert rpng.status_code == 200
        assert rpng.headers["content-type"].startswith("image/png")
        assert len(rpng.content) > 200

        rr = client.get(f"/runs/{run_id}")
        snap_path = Path(rr.json()["snapshot_path"])
        field = np.load(snap_path.with_suffix(".npy").as_posix())

        root = Path(__file__).resolve().parents[1]
        ds_path = (root / "aetherlab" / "data" / "outputs" / f"dataset_{run_id}.npy").resolve()
        ds_path.parent.mkdir(parents=True, exist_ok=True)
        np.save(ds_path.as_posix(), field.astype(np.float32))

        rds = client.post(
            "/datasets",
            json={"name": f"DS {run_id}", "path": ds_path.as_posix(), "description": "test"},
        )
        assert rds.status_code == 200
        dataset_id = rds.json()["id"]

        rcd = client.get("/compare/run-dataset", params={"run_id": run_id, "dataset_id": dataset_id})
        assert rcd.status_code == 200
        md = rcd.json()["metrics"]
        assert md["mse"] == 0.0
        assert md["mae"] == 0.0
        assert md["corr"] > 0.999

        rpng2 = client.get("/compare/run-dataset/figure.png", params={"run_id": run_id, "dataset_id": dataset_id})
        assert rpng2.status_code == 200
        assert rpng2.headers["content-type"].startswith("image/png")
        assert len(rpng2.content) > 200

