import json
import os
import time
from pathlib import Path

import numpy as np
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.responses import FileResponse

from aetherlab.packages.aether_core.db import ENGINE, SessionLocal, ensure_schema
from aetherlab.packages.aether_core.models_db import (
    Base,
    Dataset,
    Experiment,
    ExperimentDataset,
    ModelRun,
    Project,
    Artifact,
    SimulationRun,
)
from aetherlab.packages.aether_data.registry import get as get_dataset, list_datasets
from aetherlab.packages.aether_data.etl import ensure_tree, process_map_to_features, process_strain_to_features
from aetherlab.packages.aether_ai.baseline import dbscan_labels, isolation_forest_score, pca_outlier_score
from aetherlab.packages.aether_sim.metrics import autocorr2d, compute_metrics, power_spectrum_radial
from aetherlab.packages.aether_sim.simulator2d import Simulator2D
from aetherlab.packages.aether_sim.sources import (
    gaussian_pulse,
    lorentzian,
    periodic_gaussian,
    stochastic,
    top_hat,
)
from aetherlab.packages.aether_viz.plots import show_field

from .db import get_session

app = FastAPI(title="AETHERLAB API", version="0.1.0")


@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=ENGINE)
    ensure_schema()


@app.get("/health")
def health():
    return {"status": "ok"}


class ProjectIn(BaseModel):
    name: str
    description: str | None = None


@app.post("/projects")
def create_project(payload: ProjectIn, db: Session = Depends(get_session)):
    obj = Project(name=payload.name, description=payload.description)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return {"id": obj.id, "name": obj.name}


@app.get("/projects")
def list_projects(db: Session = Depends(get_session)):
    rows = db.execute(select(Project)).scalars().all()
    return [{"id": o.id, "name": o.name, "description": o.description} for o in rows]


class ExperimentIn(BaseModel):
    project_id: int
    name: str


@app.post("/experiments")
def create_experiment(payload: ExperimentIn, db: Session = Depends(get_session)):
    obj = Experiment(project_id=payload.project_id, name=payload.name)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return {"id": obj.id, "name": obj.name, "project_id": obj.project_id}


@app.get("/experiments")
def list_experiments(project_id: int | None = None, db: Session = Depends(get_session)):
    stmt = select(Experiment)
    if project_id is not None:
        stmt = stmt.where(Experiment.project_id == project_id)
    rows = db.execute(stmt).scalars().all()
    return [{"id": o.id, "name": o.name, "project_id": o.project_id} for o in rows]


@app.post("/simulations")
def create_simulation():
    return {"id": "sim-1"}


@app.post("/simulations/{sim_id}/run")
def run_simulation(sim_id: str):
    return {"sim_id": sim_id, "status": "queued"}


@app.get("/simulations/{sim_id}/status")
def status(sim_id: str):
    return {"sim_id": sim_id, "state": "unknown"}


class SimpleSimRequest(BaseModel):
    experiment_id: int
    nx: int = 128
    ny: int = 128
    steps: int = 100
    dt: float = 0.05
    lam: float = 0.5
    diff: float = 0.2
    noise: float = 0.0
    boundary: str = "periodic"  # periodic | fixed | absorbing
    source_kind: str = "gaussian_pulse"  # gaussian_pulse | periodic | stochastic | top_hat | lorentzian
    cx: int = 64
    cy: int = 64
    sigma: float = 8.0
    duration: int = 20
    amplitude: float = 1.0
    frequency: float | None = None
    radius: float | None = None
    gamma: float | None = None
    save_series: bool = False
    series_stride: int = 10


@app.post("/simulate/simple")
def simulate_simple(payload: SimpleSimRequest, db: Session = Depends(get_session)):
    sim = Simulator2D(
        nx=payload.nx,
        ny=payload.ny,
        steps=payload.steps,
        dt=payload.dt,
        lam=payload.lam,
        diff=payload.diff,
        noise=payload.noise,
        seed=123,
        boundary=payload.boundary,
    )  # type: ignore[arg-type]
    if payload.source_kind == "gaussian_pulse":
        sim.set_source(
            lambda x, y, t: gaussian_pulse(
                x,
                y,
                t,
                payload.cx,
                payload.cy,
                sigma=payload.sigma,
                duration=payload.duration,
                amplitude=payload.amplitude,
            )
        )
    elif payload.source_kind == "periodic":
        f = payload.frequency or 1.0
        sim.set_source(
            lambda x, y, t: periodic_gaussian(
                x, y, t, payload.cx, payload.cy, sigma=payload.sigma, amplitude=payload.amplitude, dt=payload.dt, freq=f
            )
        )
    elif payload.source_kind == "stochastic":
        sim.set_source(lambda x, y, t: stochastic(x, y, t, amplitude=payload.amplitude))
    elif payload.source_kind == "top_hat":
        r = payload.radius or 8.0
        sim.set_source(
            lambda x, y, t: top_hat(
                x, y, t, payload.cx, payload.cy, radius=r, amplitude=payload.amplitude, duration=payload.duration
            )
        )
    elif payload.source_kind == "lorentzian":
        g = payload.gamma or 8.0
        sim.set_source(
            lambda x, y, t: lorentzian(
                x, y, t, payload.cx, payload.cy, gamma=g, amplitude=payload.amplitude, duration=payload.duration
            )
        )
    else:
        sim.set_source(lambda x, y, t: np.zeros_like(x, dtype=np.float32))
    frames = []
    if payload.save_series:

        def cb(t, u):
            if t % max(1, payload.series_stride) == 0:
                frames.append(u.copy())

        sim.run(callback=cb)
    else:
        sim.run()
    root = Path(__file__).resolve().parents[3]
    out_dir = root / "aetherlab" / "data" / "outputs"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = int(time.time())
    out_path = out_dir / f"snapshot_{stamp}.png"
    fig, _ = show_field(sim.u)
    fig.savefig(out_path.as_posix())
    np.save(out_path.with_suffix(".npy").as_posix(), sim.u.astype(np.float32))
    metrics = compute_metrics(sim.u)
    with open(out_path.with_suffix(".json"), "w", encoding="utf-8") as f:
        json.dump(metrics, f)
    if payload.save_series and frames:
        series_path = out_path.with_suffix(".npz")
        np.savez_compressed(series_path.as_posix(), frames=np.array(frames, dtype=np.float32))
    run = SimulationRun(experiment_id=payload.experiment_id, status="finished", snapshot_path=out_path.as_posix())
    db.add(run)
    db.commit()
    db.refresh(run)
    return {"run_id": run.id, "snapshot": run.snapshot_path}


@app.get("/runs")
def list_runs(
    experiment_id: int | None = None,
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_session),
):
    stmt = select(SimulationRun).order_by(SimulationRun.id.desc())
    if experiment_id is not None:
        stmt = stmt.where(SimulationRun.experiment_id == experiment_id)
    rows = db.execute(stmt).scalars().all()[:limit]
    return [
        {
            "id": r.id,
            "experiment_id": r.experiment_id,
            "status": r.status,
            "snapshot_path": r.snapshot_path,
            "created_at": str(r.created_at),
        }
        for r in rows
    ]


@app.get("/runs/{run_id}")
def get_run(run_id: int, db: Session = Depends(get_session)):
    obj = db.get(SimulationRun, run_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="run not found")
    status = obj.status
    backend = "background"
    job_id = getattr(obj, "job_id", None)
    if os.environ.get("REDIS_URL") and job_id and status != "finished":
        try:
            import redis
            from rq.job import Job

            url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
            conn = redis.from_url(url)
            job = Job.fetch(job_id, connection=conn)
            backend = "rq"
            if job.is_finished:
                status = "finished"
            elif job.is_queued:
                status = "queued"
            elif job.is_started:
                status = "running"
            elif job.is_failed:
                status = "failed"
        except Exception:
            pass
    return {
        "id": obj.id,
        "experiment_id": obj.experiment_id,
        "status": status,
        "snapshot_path": obj.snapshot_path,
        "created_at": str(obj.created_at),
        "backend": backend,
        "job_id": job_id,
    }


class AsyncSimRequest(SimpleSimRequest):
    pass


def _background_simulation(run_id: int, payload: AsyncSimRequest):
    db = SessionLocal()
    try:
        run = db.get(SimulationRun, run_id)
        if run is None:
            return
        run.status = "running"
        db.commit()
        sim = Simulator2D(
            nx=payload.nx,
            ny=payload.ny,
            steps=payload.steps,
            dt=payload.dt,
            lam=payload.lam,
            diff=payload.diff,
            noise=payload.noise,
            seed=123,
            boundary=payload.boundary,
        )  # type: ignore[arg-type]
        if payload.source_kind == "gaussian_pulse":
            sim.set_source(
                lambda x, y, t: gaussian_pulse(
                    x,
                    y,
                    t,
                    payload.cx,
                    payload.cy,
                    sigma=payload.sigma,
                    duration=payload.duration,
                    amplitude=payload.amplitude,
                )
            )
        elif payload.source_kind == "periodic":
            f = payload.frequency or 1.0
            sim.set_source(
                lambda x, y, t: periodic_gaussian(
                    x,
                    y,
                    t,
                    payload.cx,
                    payload.cy,
                    sigma=payload.sigma,
                    amplitude=payload.amplitude,
                    dt=payload.dt,
                    freq=f,
                )
            )
        elif payload.source_kind == "stochastic":
            sim.set_source(lambda x, y, t: stochastic(x, y, t, amplitude=payload.amplitude))
        elif payload.source_kind == "top_hat":
            r = payload.radius or 8.0
            sim.set_source(
                lambda x, y, t: top_hat(
                    x, y, t, payload.cx, payload.cy, radius=r, amplitude=payload.amplitude, duration=payload.duration
                )
            )
        elif payload.source_kind == "lorentzian":
            g = payload.gamma or 8.0
            sim.set_source(
                lambda x, y, t: lorentzian(
                    x, y, t, payload.cx, payload.cy, gamma=g, amplitude=payload.amplitude, duration=payload.duration
                )
            )
        else:
            sim.set_source(lambda x, y, t: np.zeros_like(x, dtype=np.float32))
        frames = []
        if payload.save_series:

            def cb(t, u):
                if t % max(1, payload.series_stride) == 0:
                    frames.append(u.copy())

            sim.run(callback=cb)
        else:
            sim.run()
        root = Path(__file__).resolve().parents[3]
        out_dir = root / "aetherlab" / "data" / "outputs"
        out_dir.mkdir(parents=True, exist_ok=True)
        stamp = int(time.time())
        out_path = out_dir / f"snapshot_{stamp}.png"
        fig, _ = show_field(sim.u)
        fig.savefig(out_path.as_posix())
        np.save(out_path.with_suffix(".npy").as_posix(), sim.u.astype(np.float32))
        metrics = compute_metrics(sim.u)
        with open(out_path.with_suffix(".json"), "w", encoding="utf-8") as f:
            json.dump(metrics, f)
        if payload.save_series and frames:
            series_path = out_path.with_suffix(".npz")
            np.savez_compressed(series_path.as_posix(), frames=np.array(frames, dtype=np.float32))
        run.snapshot_path = out_path.as_posix()
        run.status = "finished"
        db.commit()
    finally:
        db.close()


@app.post("/simulate/async")
def simulate_async(payload: AsyncSimRequest, background: BackgroundTasks, db: Session = Depends(get_session)):
    use_rq = bool(os.environ.get("REDIS_URL"))
    run = SimulationRun(experiment_id=payload.experiment_id, status="queued", snapshot_path=None)
    db.add(run)
    db.commit()
    db.refresh(run)
    if use_rq:
        try:
            import redis
            from rq import Queue

            url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
            conn = redis.from_url(url)
            q = Queue("aetherlab", connection=conn)
            job = q.enqueue("scripts.rq_worker.run_sim_job", {"run_id": run.id, **payload.model_dump()})
            run.job_id = job.get_id()
            db.commit()
            return {"run_id": run.id, "status": "queued", "backend": "rq", "job_id": run.job_id}
        except Exception:
            background.add_task(_background_simulation, run.id, payload)
            return {"run_id": run.id, "status": "queued", "backend": "background"}
    else:
        background.add_task(_background_simulation, run.id, payload)
        return {"run_id": run.id, "status": "queued", "backend": "background"}


@app.post("/runs/{run_id}/abort")
def abort_run(run_id: int, db: Session = Depends(get_session)):
    obj = db.get(SimulationRun, run_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="run not found")
    if not obj.job_id or not os.environ.get("REDIS_URL"):
        raise HTTPException(status_code=400, detail="abort only available for RQ jobs")
    try:
        import redis
        from rq.job import Job

        url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
        conn = redis.from_url(url)
        job = Job.fetch(obj.job_id, connection=conn)
        job.cancel()
        obj.status = "cancelled"
        db.commit()
        return {"run_id": run_id, "status": obj.status}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/runs/{run_id}/retry")
def retry_run(run_id: int, db: Session = Depends(get_session)):
    obj = db.get(SimulationRun, run_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="run not found")
    if not obj.job_id or not os.environ.get("REDIS_URL"):
        raise HTTPException(status_code=400, detail="retry only available for RQ jobs")
    try:
        import redis
        from rq.job import Job

        url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
        conn = redis.from_url(url)
        job = Job.fetch(obj.job_id, connection=conn)
        if job.is_failed:
            job.requeue()
            obj.status = "queued"
            db.commit()
        return {"run_id": run_id, "status": obj.status}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/runs/{run_id}/cleanup")
def cleanup_run_outputs(run_id: int, db: Session = Depends(get_session)):
    obj = db.get(SimulationRun, run_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="run not found")
    if obj.snapshot_path:
        p = Path(obj.snapshot_path)
        for ext in (".png", ".json", ".npy", ".npz"):
            q = p.with_suffix(ext)
            if q.exists():
                try:
                    q.unlink()
                except Exception:
                    pass
        obj.snapshot_path = None
        obj.status = obj.status if obj.status not in ("finished", "failed", "cancelled") else "cleaned"
        db.commit()
    return {"run_id": run_id, "status": obj.status, "snapshot_path": obj.snapshot_path}


@app.get("/figures/{run_id}/snapshot")
def download_snapshot(run_id: int, db: Session = Depends(get_session)):
    obj = db.get(SimulationRun, run_id)
    if obj is None or not obj.snapshot_path:
        raise HTTPException(status_code=404, detail="snapshot not found")
    p = Path(obj.snapshot_path)
    if not p.exists():
        raise HTTPException(status_code=404, detail="file not found")
    return FileResponse(p)


@app.get("/figures/{run_id}/metrics")
def get_metrics(run_id: int, db: Session = Depends(get_session)):
    obj = db.get(SimulationRun, run_id)
    if obj is None or not obj.snapshot_path:
        raise HTTPException(status_code=404, detail="snapshot not found")
    p = Path(obj.snapshot_path).with_suffix(".json")
    if not p.exists():
        raise HTTPException(status_code=404, detail="metrics not found")
    with open(p, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data


@app.get("/figures/{run_id}/series")
def download_series(run_id: int, db: Session = Depends(get_session)):
    obj = db.get(SimulationRun, run_id)
    if obj is None or not obj.snapshot_path:
        raise HTTPException(status_code=404, detail="snapshot not found")
    p = Path(obj.snapshot_path).with_suffix(".npz")
    if not p.exists():
        raise HTTPException(status_code=404, detail="series not found")
    return FileResponse(p)


@app.get("/figures/{run_id}/field")
def download_field(run_id: int, db: Session = Depends(get_session)):
    obj = db.get(SimulationRun, run_id)
    if obj is None or not obj.snapshot_path:
        raise HTTPException(status_code=404, detail="snapshot not found")
    p = Path(obj.snapshot_path).with_suffix(".npy")
    if not p.exists():
        raise HTTPException(status_code=404, detail="field not found")
    return FileResponse(p)


@app.get("/figures/{run_id}/series-metrics")
def download_series_metrics(run_id: int, db: Session = Depends(get_session)):
    obj = db.get(SimulationRun, run_id)
    if obj is None or not obj.snapshot_path:
        raise HTTPException(status_code=404, detail="snapshot not found")
    p = Path(obj.snapshot_path).with_suffix(".npz")
    if not p.exists():
        raise HTTPException(status_code=404, detail="series not found")
    z = np.load(p.as_posix())
    frames = z["frames"]
    series = [compute_metrics(fr) for fr in frames]
    return {"length": len(series), "series": series}


def _load_field_for_run(obj: SimulationRun) -> np.ndarray:
    p = Path(obj.snapshot_path)
    npz = p.with_suffix(".npz")
    if npz.exists():
        z = np.load(npz.as_posix())
        frames = z["frames"]
        return frames[-1]
    npy = p.with_suffix(".npy")
    if npy.exists():
        return np.load(npy.as_posix())
    raise FileNotFoundError("no numeric field found")


@app.get("/figures/{run_id}/spectrum")
def get_spectrum(run_id: int, db: Session = Depends(get_session)):
    obj = db.get(SimulationRun, run_id)
    if obj is None or not obj.snapshot_path:
        raise HTTPException(status_code=404, detail="snapshot not found")
    try:
        u = _load_field_for_run(obj)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="field not found")
    k, ps = power_spectrum_radial(u)
    return {"k": k.tolist(), "ps": ps.tolist()}


@app.get("/figures/{run_id}/spectrum-roi")
def get_spectrum_roi(
    run_id: int,
    x0: int = Query(ge=0),
    y0: int = Query(ge=0),
    w: int = Query(gt=0),
    h: int = Query(gt=0),
    db: Session = Depends(get_session),
):
    obj = db.get(SimulationRun, run_id)
    if obj is None or not obj.snapshot_path:
        raise HTTPException(status_code=404, detail="snapshot not found")
    try:
        u = _load_field_for_run(obj)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="field not found")
    H, W = u.shape
    x1 = min(max(x0, 0), W)
    y1 = min(max(y0, 0), H)
    x2 = min(x1 + w, W)
    y2 = min(y1 + h, H)
    if x2 <= x1 or y2 <= y1:
        raise HTTPException(status_code=400, detail="invalid roi")
    roi = u[y1:y2, x1:x2]
    k, ps = power_spectrum_radial(roi)
    return {"x0": x1, "y0": y1, "w": int(x2 - x1), "h": int(y2 - y1), "k": k.tolist(), "ps": ps.tolist()}


@app.get("/figures/{run_id}/autocorr")
def get_autocorr(run_id: int, crop: int = Query(default=64, ge=8, le=512), db: Session = Depends(get_session)):
    obj = db.get(SimulationRun, run_id)
    if obj is None or not obj.snapshot_path:
        raise HTTPException(status_code=404, detail="snapshot not found")
    try:
        u = _load_field_for_run(obj)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="field not found")
    ac = autocorr2d(u, normalize=True)
    h, w = ac.shape
    c0 = h // 2
    c1 = w // 2
    half = min(crop // 2, c0, c1)
    cut = ac[c0 - half : c0 + half, c1 - half : c1 + half]
    return {"crop": crop, "autocorr": cut.tolist()}


@app.get("/figures/{run_id}/autocorr-roi")
def get_autocorr_roi(
    run_id: int,
    x0: int = Query(ge=0),
    y0: int = Query(ge=0),
    w: int = Query(gt=0),
    h: int = Query(gt=0),
    db: Session = Depends(get_session),
):
    obj = db.get(SimulationRun, run_id)
    if obj is None or not obj.snapshot_path:
        raise HTTPException(status_code=404, detail="snapshot not found")
    try:
        u = _load_field_for_run(obj)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="field not found")
    H, W = u.shape
    x1 = min(max(x0, 0), W)
    y1 = min(max(y0, 0), H)
    x2 = min(x1 + w, W)
    y2 = min(y1 + h, H)
    if x2 <= x1 or y2 <= y1:
        raise HTTPException(status_code=400, detail="invalid roi")
    roi = u[y1:y2, x1:x2]
    ac = autocorr2d(roi, normalize=True)
    return {"x0": x1, "y0": y1, "w": int(x2 - x1), "h": int(y2 - y1), "autocorr": ac.tolist()}


@app.post("/runs/{run_id}/refresh")
def refresh_run(run_id: int, db: Session = Depends(get_session)):
    obj = db.get(SimulationRun, run_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="run not found")
    if obj.snapshot_path:
        p = Path(obj.snapshot_path)
        if p.exists():
            if obj.status != "finished":
                obj.status = "finished"
                db.commit()
                db.refresh(obj)
            return {"run_id": run_id, "status": obj.status}
    # Fallback: keep queued/running
    return {"run_id": run_id, "status": obj.status or "queued"}


class DataLoadRequest(BaseModel):
    name: str
    path: str


@app.get("/data/datasets")
def data_list():
    return {"datasets": list_datasets()}


@app.post("/data/load")
def data_load(payload: DataLoadRequest):
    try:
        entry = get_dataset(payload.name)
    except KeyError:
        raise HTTPException(status_code=404, detail="dataset not registered")
    loader = entry["loader"]
    try:
        info = loader(payload.path)
        return {"name": payload.name, "info": info}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class OutlierScoreRequest(BaseModel):
    method: str = "isoforest"  # isoforest | mean_dist
    X: list[list[float]]
    random_state: int | None = 0


@app.post("/ai/outlier-score")
def ai_outlier_score(payload: OutlierScoreRequest):
    X = np.asarray(payload.X, dtype=np.float32)
    if payload.method == "isoforest":
        s = isolation_forest_score(X, random_state=payload.random_state or 0)
    elif payload.method == "mean_dist":
        s = pca_outlier_score(X)
    else:
        raise HTTPException(status_code=400, detail="unknown method")
    return {"scores": s.tolist()}


class DbscanRequest(BaseModel):
    X: list[list[float]]
    eps: float = 0.5
    min_samples: int = 5
    metric: str = "euclidean"


@app.post("/ai/dbscan")
def ai_dbscan(payload: DbscanRequest):
    X = np.asarray(payload.X, dtype=np.float32)
    labels = dbscan_labels(X, eps=payload.eps, min_samples=payload.min_samples, metric=payload.metric)  # type: ignore[arg-type]
    return {"labels": labels.tolist()}


class DatasetIn(BaseModel):
    name: str
    path: str
    description: str | None = None


@app.post("/datasets")
def create_dataset(payload: DatasetIn, db: Session = Depends(get_session)):
    obj = Dataset(name=payload.name, path=payload.path, description=payload.description)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return {"id": obj.id, "name": obj.name, "path": obj.path}


@app.get("/datasets")
def list_datasets_db(db: Session = Depends(get_session)):
    rows = db.execute(select(Dataset)).scalars().all()
    return [{"id": d.id, "name": d.name, "path": d.path, "description": d.description} for d in rows]


class ModelRunIn(BaseModel):
    experiment_id: int
    model_name: str
    params: dict | None = None


@app.post("/models")
def create_model_run(payload: ModelRunIn, db: Session = Depends(get_session)):
    obj = ModelRun(
        experiment_id=payload.experiment_id,
        model_name=payload.model_name,
        params_json=json.dumps(payload.params or {}),
        status="created",
    )
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return {"id": obj.id, "model_name": obj.model_name, "experiment_id": obj.experiment_id}


@app.get("/models")
def list_model_runs(experiment_id: int | None = None, db: Session = Depends(get_session)):
    stmt = select(ModelRun).order_by(ModelRun.id.desc())
    if experiment_id is not None:
        stmt = stmt.where(ModelRun.experiment_id == experiment_id)
    rows = db.execute(stmt).scalars().all()
    return [
        {
            "id": m.id,
            "experiment_id": m.experiment_id,
            "model_name": m.model_name,
            "status": m.status,
        }
        for m in rows
    ]


@app.post("/experiments/{experiment_id}/datasets/link")
def link_dataset(experiment_id: int, dataset_id: int, db: Session = Depends(get_session)):
    exp = db.get(Experiment, experiment_id)
    ds = db.get(Dataset, dataset_id)
    if exp is None or ds is None:
        raise HTTPException(status_code=404, detail="experiment or dataset not found")
    link = ExperimentDataset(experiment_id=experiment_id, dataset_id=dataset_id)
    db.add(link)
    db.commit()
    db.refresh(link)
    return {"id": link.id, "experiment_id": experiment_id, "dataset_id": dataset_id}


@app.get("/experiments/{experiment_id}/datasets")
def list_experiment_datasets(experiment_id: int, db: Session = Depends(get_session)):
    rows = db.execute(select(ExperimentDataset).where(ExperimentDataset.experiment_id == experiment_id)).scalars().all()
    return [{"id": r.id, "experiment_id": r.experiment_id, "dataset_id": r.dataset_id} for r in rows]


class AiRunOnRunRequest(BaseModel):
    run_id: int
    method: str = "isoforest"


@app.post("/ai/run-on-run")
def ai_run_on_run(payload: AiRunOnRunRequest, db: Session = Depends(get_session)):
    obj = db.get(SimulationRun, payload.run_id)
    if obj is None or not obj.snapshot_path:
        raise HTTPException(status_code=404, detail="run not found")
    try:
        u = _load_field_for_run(obj)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="field not found")
    X = u.reshape(-1, 1)
    if payload.method == "isoforest":
        s = isolation_forest_score(X)
    elif payload.method == "mean_dist":
        s = pca_outlier_score(X)
    else:
        raise HTTPException(status_code=400, detail="unknown method")
    root = Path(__file__).resolve().parents[3]
    out_dir = root / "aetherlab" / "data" / "outputs"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = int(time.time())
    out_path = out_dir / f"ai_run_{obj.id}_{stamp}.csv"
    with open(out_path.as_posix(), "w", encoding="utf-8") as f:
        for v in s.tolist():
            f.write(f"{v}\n")
    mr = ModelRun(
        experiment_id=obj.experiment_id,
        model_name=payload.method,
        params_json=json.dumps({}),
        status="finished",
    )
    db.add(mr)
    db.commit()
    db.refresh(mr)
    art = Artifact(run_id=obj.id, kind="ai_scores", path=out_path.as_posix())
    db.add(art)
    db.commit()
    return {"path": out_path.as_posix(), "model_run_id": mr.id, "artifact_path": art.path}


class AiRunOnDatasetRequest(BaseModel):
    dataset_id: int
    method: str = "isoforest"


@app.post("/ai/run-on-dataset")
def ai_run_on_dataset(payload: AiRunOnDatasetRequest, db: Session = Depends(get_session)):
    ds = db.get(Dataset, payload.dataset_id)
    if ds is None:
        raise HTTPException(status_code=404, detail="dataset not found")
    p = Path(ds.path)
    root = Path(__file__).resolve().parents[3]
    try:
        # Attempt ETL to features
        if p.suffix in (".npy", ".npz"):
            features = process_map_to_features(p, root)
            z = np.load(features.as_posix())
            X = z["features"].reshape(-1, 1)
        else:
            features = process_strain_to_features(p, root)
            z = np.load(features.as_posix())
            X = z["features"].reshape(-1, 1)
    except Exception:
        raise HTTPException(status_code=500, detail="etl failed")
    if payload.method == "isoforest":
        s = isolation_forest_score(X)
    elif payload.method == "mean_dist":
        s = pca_outlier_score(X)
    else:
        raise HTTPException(status_code=400, detail="unknown method")
    out_dir = ensure_tree(root)["features"]
    stamp = int(time.time())
    out_path = out_dir / f"ai_ds_{ds.id}_{stamp}.csv"
    with open(out_path.as_posix(), "w", encoding="utf-8") as f:
        for v in s.tolist():
            f.write(f"{v}\n")
    link = db.execute(select(ExperimentDataset).where(ExperimentDataset.dataset_id == ds.id)).scalars().first()
    if link is not None:
        mr = ModelRun(
            experiment_id=link.experiment_id,
            model_name=payload.method,
            params_json=json.dumps({"dataset_id": ds.id}),
            status="finished",
        )
        db.add(mr)
        db.commit()
        db.refresh(mr)
        # Artifact only supports run_id; store path in model_run metrics_json
        mr.metrics_json = json.dumps({"scores_path": out_path.as_posix()})
        db.commit()
        return {"path": out_path.as_posix(), "model_run_id": mr.id}
    return {"path": out_path.as_posix()}


@app.get("/ai/download")
def ai_download(path: str):
    p = Path(path)
    root = Path(__file__).resolve().parents[3]
    base = root / "aetherlab" / "data"
    if not p.exists() or not p.as_posix().startswith(base.as_posix()):
        raise HTTPException(status_code=404, detail="file not found")
    return FileResponse(p)
