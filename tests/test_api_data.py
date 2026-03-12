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


def test_smoke_sim_compare_exports():
    with TestClient(app) as client:
        pr = client.post("/projects", json={"name": "T", "description": None})
        assert pr.status_code == 200
        pid = pr.json()["id"]
        ex = client.post("/experiments", json={"project_id": pid, "name": "E"})
        assert ex.status_code == 200
        eid = ex.json()["id"]
        payload = {
            "experiment_id": eid,
            "nx": 16,
            "ny": 16,
            "steps": 6,
            "dt": 0.05,
            "lam": 0.5,
            "diff": 0.2,
            "noise": 0.0,
            "seed": 123,
            "boundary": "periodic",
            "source_kind": "gaussian_pulse",
            "cx": 8,
            "cy": 8,
            "sigma": 4.0,
            "duration": 3,
            "amplitude": 1.0,
            "save_series": True,
            "series_stride": 1,
        }
        r1 = client.post("/simulate/simple", json=payload)
        assert r1.status_code == 200
        run1 = r1.json()["run_id"]
        r2 = client.post("/simulate/simple", json={**payload, "seed": 124})
        assert r2.status_code == 200
        run2 = r2.json()["run_id"]

        rr = client.get(f"/compare/run-run?run_a={run1}&run_b={run2}")
        assert rr.status_code == 200
        m = rr.json()["metrics"]
        assert "mse" in m and "ssim" in m and "nrmse" in m and "spectrum_l2" in m

        png = client.get(f"/figures/{run1}/snapshot")
        assert png.status_code == 200 and len(png.content) > 10
        svg = client.get(f"/figures/{run1}/snapshot.svg")
        assert svg.status_code == 200 and (b"<svg" in svg.content[:400])
        pdf = client.get(f"/figures/{run1}/snapshot.pdf")
        assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"

        csv_r = client.get(f"/figures/{run1}/series-metrics.csv")
        assert csv_r.status_code == 200 and b"index,energy,mean,variance,spatial_corr" in csv_r.content[:80]
        html = client.get(f"/reports/run/{run1}/html?crop=32")
        assert html.status_code == 200 and "Reporte Run" in html.text

        csvg = client.get(f"/compare/run-run/figure.svg?run_a={run1}&run_b={run2}")
        assert csvg.status_code == 200 and (b"<svg" in csvg.content[:400])
        cpdf = client.get(f"/compare/run-run/figure.pdf?run_a={run1}&run_b={run2}")
        assert cpdf.status_code == 200 and cpdf.content[:4] == b"%PDF"

        sweep = client.post(
            "/sweeps/grid",
            json={
                "experiment_id": eid,
                "base": {**payload, "seed": None, "steps": 3, "save_series": False},
                "grid": {"lam": [0.1, 0.2]},
                "max_runs": 5,
                "seed_base": 1000,
            },
        )
        assert sweep.status_code == 200
        run_ids = sweep.json()["run_ids"]
        assert len(run_ids) == 2
        st = client.get(f"/runs/{run_ids[0]}")
        assert st.status_code == 200 and st.json()["status"] in ("queued", "running", "finished", "failed")
