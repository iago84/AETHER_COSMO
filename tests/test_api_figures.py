import os
import time
from fastapi.testclient import TestClient

os.environ["AETHERLAB_DB_URL"] = "sqlite+pysqlite:///:memory:"
os.environ["MPLBACKEND"] = "Agg"
from aetherlab.apps.api.main import app


def _bootstrap_project_and_experiment(client: TestClient) -> tuple[int, int]:
    uniq = int(time.time() * 1000)
    rp = client.post("/projects", json={"name": f"Proyecto Fig {uniq}", "description": "Test"})
    pid = rp.json()["id"]
    re = client.post("/experiments", json={"project_id": pid, "name": f"Exp Figs {uniq}"})
    eid = re.json()["id"]
    return pid, eid


def test_figures_and_runs_endpoints():
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
            "save_series": True,
            "series_stride": 1,
        }
        rs = client.post("/simulate/simple", json=payload)
        assert rs.status_code == 200
        run_id = rs.json()["run_id"]

    # List and get run
        rlist = client.get("/runs", params={"experiment_id": eid})
        assert rlist.status_code == 200
        assert any(r["id"] == run_id for r in rlist.json())
        rget = client.get(f"/runs/{run_id}")
        assert rget.status_code == 200

    # Metrics
        rm = client.get(f"/figures/{run_id}/metrics")
        assert rm.status_code == 200
        assert "energy" in rm.json()

    # Field
        rf = client.get(f"/figures/{run_id}/field")
        assert rf.status_code == 200

    # Spectrum and autocorr
        rspec = client.get(f"/figures/{run_id}/spectrum")
        assert rspec.status_code == 200
        data = rspec.json()
        assert "k" in data and "ps" in data
        rac = client.get(f"/figures/{run_id}/autocorr", params={"crop": 16})
        assert rac.status_code == 200
        ac = rac.json()["autocorr"]
        assert isinstance(ac, list)

    # Series (exists because save_series=True)
        rseries = client.get(f"/figures/{run_id}/series")
        assert rseries.status_code == 200

    # Cleanup and refresh
        rclean = client.post(f"/runs/{run_id}/cleanup")
        assert rclean.status_code == 200
        rrefresh = client.post(f"/runs/{run_id}/refresh")
        assert rrefresh.status_code == 200
