import hashlib
import json
import base64
import io
import os
import time
from pathlib import Path
from typing import Literal

import numpy as np
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query, Response
from fastapi.exceptions import RequestValidationError
from matplotlib.figure import Figure
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.responses import FileResponse, JSONResponse

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
from aetherlab.packages.aether_data.etl import (
    ensure_tree,
    load_array,
    process_map_to_features,
    process_strain_to_features,
)
from aetherlab.packages.aether_ai.baseline import dbscan_labels, isolation_forest_score, pca_outlier_score
from aetherlab.packages.aether_sim.metrics import autocorr2d, compute_metrics, corrcoef2d, power_spectrum_radial
from aetherlab.packages.aether_sim.simulator2d import Simulator2D
from aetherlab.packages.aether_sim.sources import (
    gaussian_pulse,
    lorentzian,
    periodic_gaussian,
    stochastic,
    top_hat,
)
from aetherlab.packages.aether_viz.plots import show_field
from aetherlab.packages.aether_report.builder import build_run_html

from .db import get_session

app = FastAPI(title="AETHERLAB API", version="0.1.0")
_API_KEY = os.environ.get("AETHERLAB_API_KEY")


@app.middleware("http")
async def api_key_middleware(request, call_next):
    if _API_KEY and request.method in ("POST", "PUT", "DELETE"):
        if request.headers.get("X-API-Key") != _API_KEY:
            return JSONResponse(status_code=401, content={"detail": "unauthorized"})
    return await call_next(request)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={"detail": "validation_error", "errors": exc.errors()},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request, exc: Exception):
    return JSONResponse(status_code=500, content={"detail": "internal_error"})


@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=ENGINE)
    ensure_schema()
    try:
        from apscheduler.schedulers.background import BackgroundScheduler  # noqa: WPS433
        s = BackgroundScheduler()
        days = int(os.environ.get("AETHERLAB_CLEANUP_DAYS", "30"))
        s.add_job(lambda: data_cleanup(days), trigger="cron", hour=3, minute=0)
        s.start()
        app.state.scheduler = s  # type: ignore[attr-defined]
    except Exception:
        pass

@app.on_event("shutdown")
def on_shutdown():
    s = getattr(app.state, "scheduler", None)  # type: ignore[attr-defined]
    if s is not None:
        try:
            s.shutdown(wait=False)
        except Exception:
            pass


@app.get("/health")
def health():
    return {"status": "ok"}


class ProjectIn(BaseModel):
    name: str
    description: str | None = None


@app.post("/projects")
def create_project(payload: ProjectIn, db: Session = Depends(get_session)):
    existing = db.execute(select(Project).where(Project.name == payload.name)).scalars().first()
    if existing is not None:
        return {"id": existing.id, "name": existing.name}
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
    nx: int = Field(default=128, ge=8, le=2048)
    ny: int = Field(default=128, ge=8, le=2048)
    steps: int = Field(default=100, ge=1, le=200000)
    dt: float = Field(default=0.05, gt=0.0, le=1.0)
    lam: float = Field(default=0.5, ge=0.0, le=10.0)
    diff: float = Field(default=0.2, ge=0.0, le=10.0)
    noise: float = Field(default=0.0, ge=0.0, le=10.0)
    seed: int | None = Field(default=None, ge=0, le=2_147_483_647)
    boundary: Literal["periodic", "fixed", "absorbing"] = "periodic"
    source_kind: Literal["gaussian_pulse", "periodic", "stochastic", "top_hat", "lorentzian"] = "gaussian_pulse"
    cx: int = Field(default=64, ge=0, le=4096)
    cy: int = Field(default=64, ge=0, le=4096)
    sigma: float = Field(default=8.0, gt=0.0, le=10_000.0)
    duration: int = Field(default=20, ge=1, le=1_000_000)
    amplitude: float = Field(default=1.0, ge=0.0, le=10_000.0)
    frequency: float | None = Field(default=None, gt=0.0, le=10_000.0)
    radius: float | None = Field(default=None, gt=0.0, le=10_000.0)
    gamma: float | None = Field(default=None, gt=0.0, le=10_000.0)
    save_series: bool = False
    series_stride: int = Field(default=10, ge=1, le=100000)


def _validate_sim_stability(payload: SimpleSimRequest):
    if payload.dt * payload.diff > 1.0:
        raise HTTPException(status_code=400, detail="unstable params: dt*diff too large")
    if payload.dt * payload.lam > 1.0:
        raise HTTPException(status_code=400, detail="unstable params: dt*lam too large")
    if payload.noise > 0.0 and payload.dt * payload.noise > 1.0:
        raise HTTPException(status_code=400, detail="unstable params: dt*noise too large")
    if payload.cx >= payload.nx or payload.cy >= payload.ny:
        raise HTTPException(status_code=400, detail="source center out of bounds")


@app.post("/simulate/simple")
def simulate_simple(payload: SimpleSimRequest, db: Session = Depends(get_session)):
    _validate_sim_stability(payload)
    sim = Simulator2D(
        nx=payload.nx,
        ny=payload.ny,
        steps=payload.steps,
        dt=payload.dt,
        lam=payload.lam,
        diff=payload.diff,
        noise=payload.noise,
        seed=payload.seed or 123,
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
    run = SimulationRun(
        experiment_id=payload.experiment_id,
        status="finished",
        snapshot_path=out_path.as_posix(),
        seed=payload.seed,
        config_json=json.dumps(payload.model_dump(), ensure_ascii=False),
    )
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
            "seed": getattr(r, "seed", None),
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
        "seed": getattr(obj, "seed", None),
        "config": json.loads(obj.config_json) if getattr(obj, "config_json", None) else None,
    }


class AsyncSimRequest(SimpleSimRequest):
    pass


def _background_simulation(run_id: int, payload: AsyncSimRequest):
    db = SessionLocal()
    try:
        run = db.get(SimulationRun, run_id)
        if run is None:
            return
        try:
            _validate_sim_stability(payload)
        except HTTPException:
            run.status = "failed"
            db.commit()
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
            seed=payload.seed or 123,
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
    _validate_sim_stability(payload)
    use_rq = bool(os.environ.get("REDIS_URL"))
    run = SimulationRun(
        experiment_id=payload.experiment_id,
        status="queued",
        snapshot_path=None,
        seed=payload.seed,
        config_json=json.dumps(payload.model_dump(), ensure_ascii=False),
    )
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

@app.get("/figures/{run_id}/series.mp4")
def series_mp4(run_id: int, db: Session = Depends(get_session)):
    obj = db.get(SimulationRun, run_id)
    if obj is None or not obj.snapshot_path:
        raise HTTPException(status_code=404, detail="snapshot not found")
    npz = Path(obj.snapshot_path).with_suffix(".npz")
    if not npz.exists():
        raise HTTPException(status_code=404, detail="series not found")
    import matplotlib.pyplot as plt  # noqa: WPS433
    import matplotlib.animation as animation  # noqa: WPS433
    z = np.load(npz.as_posix())
    frames = z["frames"]
    fig = plt.Figure(figsize=(5, 4), dpi=120)
    ax = fig.add_subplot(111)
    im = ax.imshow(frames[0], cmap="viridis", origin="lower")
    ax.set_title(f"Run {run_id} - serie")
    def update(i):
        im.set_data(frames[i])
        return [im]
    ani = animation.FuncAnimation(fig, update, frames=int(frames.shape[0]), interval=100, blit=True)
    root = Path(__file__).resolve().parents[3]
    out_dir = root / "aetherlab" / "data" / "outputs"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"series_{run_id}.mp4"
    if not out_path.exists():
        try:
            writer = animation.FFMpegWriter(fps=10)
            ani.save(out_path.as_posix(), writer=writer)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"ffmpeg not available: {e}")
    existing = (
        db.execute(
            select(Artifact).where(
                Artifact.run_id == run_id,
                Artifact.kind == "series_mp4",
                Artifact.path == out_path.as_posix(),
            )
        )
        .scalars()
        .first()
    )
    if existing is None:
        db.add(
            Artifact(
                run_id=run_id,
                experiment_id=obj.experiment_id,
                kind="series_mp4",
                path=out_path.as_posix(),
            )
        )
        db.commit()
    return FileResponse(out_path)

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


@app.get("/figures/{run_id}/series-metrics.csv")
def download_series_metrics_csv(run_id: int, db: Session = Depends(get_session)):
    obj = db.get(SimulationRun, run_id)
    if obj is None or not obj.snapshot_path:
        raise HTTPException(status_code=404, detail="snapshot not found")
    p = Path(obj.snapshot_path).with_suffix(".npz")
    if not p.exists():
        raise HTTPException(status_code=404, detail="series not found")
    z = np.load(p.as_posix())
    frames = z["frames"]
    series = [compute_metrics(fr) for fr in frames]
    root = Path(__file__).resolve().parents[3]
    out_dir = root / "aetherlab" / "data" / "outputs"
    out_dir.mkdir(parents=True, exist_ok=True)
    body = io.StringIO()
    body.write("index,energy,mean,variance,spatial_corr\n")
    for i, m in enumerate(series):
        body.write(f"{i},{m['energy']},{m['mean']},{m['variance']},{m['spatial_corr']}\n")
    csv_bytes = body.getvalue().encode("utf-8")
    h = hashlib.sha256(csv_bytes).hexdigest()[:12]
    out_path = out_dir / f"series_metrics_{run_id}_{h}.csv"
    if not out_path.exists():
        out_path.write_bytes(csv_bytes)
    existing = (
        db.execute(
            select(Artifact).where(
                Artifact.run_id == run_id,
                Artifact.kind == "series_metrics_csv",
                Artifact.path == out_path.as_posix(),
            )
        )
        .scalars()
        .first()
    )
    if existing is None:
        db.add(
            Artifact(
                run_id=run_id,
                experiment_id=obj.experiment_id,
                kind="series_metrics_csv",
                path=out_path.as_posix(),
            )
        )
        db.commit()
    return FileResponse(out_path, media_type="text/csv", filename=out_path.name)


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


def _validate_matrix_payload(X: np.ndarray) -> np.ndarray:
    if X.ndim != 2:
        raise HTTPException(status_code=400, detail="X must be 2D")
    if X.shape[0] > 200000 or X.shape[1] > 2048 or X.size > 2000000:
        raise HTTPException(status_code=413, detail="X too large")
    return X


@app.post("/ai/outlier-score")
def ai_outlier_score(payload: OutlierScoreRequest):
    X = _validate_matrix_payload(np.asarray(payload.X, dtype=np.float32))
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
    X = _validate_matrix_payload(np.asarray(payload.X, dtype=np.float32))
    labels = dbscan_labels(X, eps=payload.eps, min_samples=payload.min_samples, metric=payload.metric)  # type: ignore[arg-type]
    return {"labels": labels.tolist()}

class HdbscanRequest(BaseModel):
    X: list[list[float]]
    min_cluster_size: int = 5
    min_samples: int | None = None
    metric: str = "euclidean"

@app.post("/ai/hdbscan")
def ai_hdbscan(payload: HdbscanRequest):
    X = _validate_matrix_payload(np.asarray(payload.X, dtype=np.float32))
    import hdbscan  # noqa: WPS433
    algo = hdbscan.HDBSCAN(
        min_cluster_size=payload.min_cluster_size,
        min_samples=payload.min_samples,
        metric=payload.metric,
    )
    labels = algo.fit_predict(X)
    probs = getattr(algo, "probabilities_", None)
    return {"labels": labels.tolist(), "probabilities": probs.tolist() if probs is not None else None}

class HdbscanTreeRequest(BaseModel):
    X: list[list[float]]
    min_cluster_size: int = 5
    min_samples: int | None = None
    metric: str = "euclidean"

@app.post("/ai/hdbscan-tree")
def ai_hdbscan_tree(payload: HdbscanTreeRequest):
    import hdbscan  # noqa: WPS433
    X = np.asarray(payload.X, dtype=np.float32)
    algo = hdbscan.HDBSCAN(
        min_cluster_size=payload.min_cluster_size,
        min_samples=payload.min_samples,
        metric=payload.metric,
    )
    algo.fit(X)
    df = algo.condensed_tree_.to_pandas()
    edges = []
    for _, row in df.iterrows():
        edges.append(
            {
                "parent": int(row["parent"]),
                "child": int(row["child"]),
                "lambda": float(row["lambda_val"]),
                "size": int(row["child_size"]),
            }
        )
    return {"edges": edges}
class PcaPlotRequest(BaseModel):
    X: list[list[float]]
    n_components: int = 2

@app.post("/ai/pca-plot")
def ai_pca_plot(payload: PcaPlotRequest):
    from sklearn.decomposition import PCA  # noqa: WPS433
    import matplotlib.pyplot as plt  # noqa: WPS433
    X = np.asarray(payload.X, dtype=np.float32)
    pca = PCA(n_components=min(payload.n_components, X.shape[1]))
    Y = pca.fit_transform(X)
    fig = plt.Figure(figsize=(4, 3), dpi=120)
    ax = fig.add_subplot(111)
    ax.scatter(Y[:, 0], Y[:, 1], s=10, alpha=0.7)
    ax.set_xlabel("PC1")
    ax.set_ylabel("PC2")
    ax.grid(True)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight")
    img_b64 = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
    return {"image": img_b64}

class DatasetIn(BaseModel):
    name: str
    path: str
    description: str | None = None


def _sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk_size)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def _dataset_meta(path: Path) -> dict:
    p = path.resolve()
    st = p.stat()
    return {
        "origin_path": p.as_posix(),
        "size_bytes": int(st.st_size),
        "mtime_ns": int(st.st_mtime_ns),
        "sha256": _sha256_file(p),
    }


def _dataset_next_version(name: str, sha256: str, db: Session) -> int:
    rows = db.execute(select(Dataset).where(Dataset.name == name).order_by(Dataset.id.asc())).scalars().all()
    versions: list[int] = []
    for r in rows:
        if not r.description:
            continue
        try:
            d = json.loads(r.description)
        except Exception:
            continue
        if isinstance(d, dict) and d.get("sha256") == sha256:
            try:
                versions.append(int(d.get("version", 1)))
            except Exception:
                versions.append(1)
    return (max(versions) + 1) if versions else 1


@app.post("/datasets")
def create_dataset(payload: DatasetIn, db: Session = Depends(get_session)):
    try:
        meta = _dataset_meta(Path(payload.path))
        meta["version"] = _dataset_next_version(payload.name, meta["sha256"], db)
        desc = payload.description or json.dumps(meta, ensure_ascii=False)
    except Exception:
        desc = payload.description
        meta = None
    obj = Dataset(name=payload.name, path=payload.path, description=desc)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return {"id": obj.id, "name": obj.name, "path": obj.path, "meta": meta}


@app.get("/datasets")
def list_datasets_db(db: Session = Depends(get_session)):
    rows = db.execute(select(Dataset)).scalars().all()
    return [{"id": d.id, "name": d.name, "path": d.path, "description": d.description} for d in rows]


@app.get("/datasets/{dataset_id}/meta")
def dataset_meta(dataset_id: int, db: Session = Depends(get_session)):
    ds = db.get(Dataset, dataset_id)
    if ds is None:
        raise HTTPException(status_code=404, detail="dataset not found")
    try:
        meta = _dataset_meta(Path(ds.path))
    except Exception:
        meta = None
    stored = None
    if ds.description:
        try:
            stored = json.loads(ds.description)
        except Exception:
            stored = ds.description
    return {"id": ds.id, "name": ds.name, "path": ds.path, "meta": meta, "stored": stored}


class EtlDatasetRequest(BaseModel):
    dataset_id: int
    normalize: str | None = "zscore"
    qc: bool = True


@app.post("/etl/dataset")
def etl_dataset(payload: EtlDatasetRequest, db: Session = Depends(get_session)):
    ds = db.get(Dataset, payload.dataset_id)
    if ds is None:
        raise HTTPException(status_code=404, detail="dataset not found")
    p = Path(ds.path)
    root = Path(__file__).resolve().parents[3]
    try:
        arr = load_array(p)
        if arr.ndim == 2:
            out = process_map_to_features(p, root, normalize=payload.normalize, qc=payload.qc)
        else:
            out = process_strain_to_features(p, root, normalize=payload.normalize, qc=payload.qc)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"etl failed: {e}")
    qc_path = out.with_suffix(".qc.json")
    qc_data = None
    if payload.qc and qc_path.exists():
        try:
            qc_data = json.loads(qc_path.read_text(encoding="utf-8"))
        except Exception:
            qc_data = None
    art_feat = Artifact(run_id=None, dataset_id=ds.id, kind="etl_features", path=out.as_posix())
    db.add(art_feat)
    db.commit()
    db.refresh(art_feat)
    art_qc = None
    if payload.qc and qc_path.exists():
        art_qc = Artifact(run_id=None, dataset_id=ds.id, kind="etl_qc", path=qc_path.as_posix())
        db.add(art_qc)
        db.commit()
        db.refresh(art_qc)
    return {
        "dataset_id": ds.id,
        "features_path": out.as_posix(),
        "qc_path": qc_path.as_posix() if payload.qc else None,
        "qc": qc_data,
        "artifact_features_id": art_feat.id,
        "artifact_qc_id": art_qc.id if art_qc is not None else None,
    }


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
                "metrics": json.loads(m.metrics_json) if m.metrics_json else None,
        }
        for m in rows
    ]


@app.get("/models/{model_run_id}")
def get_model_run(model_run_id: int, db: Session = Depends(get_session)):
    obj = db.get(ModelRun, model_run_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="model run not found")
    params = None
    metrics = None
    if obj.params_json:
        try:
            params = json.loads(obj.params_json)
        except Exception:
            params = obj.params_json
    if obj.metrics_json:
        try:
            metrics = json.loads(obj.metrics_json)
        except Exception:
            metrics = obj.metrics_json
    return {
        "id": obj.id,
        "experiment_id": obj.experiment_id,
        "model_name": obj.model_name,
        "status": obj.status,
        "params": params,
        "metrics": metrics,
        "created_at": str(obj.created_at),
    }


@app.get("/artifacts")
def list_artifacts(
    run_id: int | None = None,
    dataset_id: int | None = None,
    experiment_id: int | None = None,
    db: Session = Depends(get_session),
):
    stmt = select(Artifact).order_by(Artifact.id.desc())
    if run_id is not None:
        stmt = stmt.where(Artifact.run_id == run_id)
    if dataset_id is not None:
        stmt = stmt.where(Artifact.dataset_id == dataset_id)
    if experiment_id is not None:
        stmt = stmt.where(Artifact.experiment_id == experiment_id)
    rows = db.execute(stmt).scalars().all()
    return [
        {
            "id": a.id,
            "run_id": a.run_id,
            "dataset_id": a.dataset_id,
            "experiment_id": getattr(a, "experiment_id", None),
            "kind": a.kind,
            "path": a.path,
            "created_at": str(a.created_at),
        }
        for a in rows
    ]


@app.get("/artifacts/{artifact_id}")
def get_artifact(artifact_id: int, db: Session = Depends(get_session)):
    a = db.get(Artifact, artifact_id)
    if a is None:
        raise HTTPException(status_code=404, detail="artifact not found")
    return {
        "id": a.id,
        "run_id": a.run_id,
        "dataset_id": a.dataset_id,
        "experiment_id": getattr(a, "experiment_id", None),
        "kind": a.kind,
        "path": a.path,
        "created_at": str(a.created_at),
    }


def _safe_download_path(p: Path) -> Path:
    root = Path(__file__).resolve().parents[3]
    base = (root / "aetherlab" / "data").resolve()
    pp = p.resolve()
    try:
        pp.relative_to(base)
    except Exception:
        raise HTTPException(status_code=404, detail="file not found")
    if not pp.exists():
        raise HTTPException(status_code=404, detail="file not found")
    return pp


@app.get("/artifacts/{artifact_id}/download")
def download_artifact(artifact_id: int, db: Session = Depends(get_session)):
    a = db.get(Artifact, artifact_id)
    if a is None:
        raise HTTPException(status_code=404, detail="artifact not found")
    p = _safe_download_path(Path(a.path))
    return FileResponse(p)


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
    score_stats = {
        "n": int(s.size),
        "mean": float(np.mean(s)),
        "std": float(np.std(s)),
        "min": float(np.min(s)),
        "max": float(np.max(s)),
        "path": out_path.as_posix(),
    }
    mr = ModelRun(
        experiment_id=obj.experiment_id,
        model_name=payload.method,
        params_json=json.dumps({}),
        status="finished",
        metrics_json=json.dumps(score_stats),
    )
    db.add(mr)
    db.commit()
    db.refresh(mr)
    art = Artifact(run_id=obj.id, kind="ai_scores", path=out_path.as_posix())
    db.add(art)
    db.commit()
    return {"path": out_path.as_posix(), "model_run_id": mr.id, "artifact_path": art.path}


class AiRunOnRunSeriesRequest(BaseModel):
    run_id: int
    method: str = "isoforest"
    window: int = Field(default=1, ge=1, le=1000)


@app.post("/ai/run-on-run-series")
def ai_run_on_run_series(payload: AiRunOnRunSeriesRequest, db: Session = Depends(get_session)):
    obj = db.get(SimulationRun, payload.run_id)
    if obj is None or not obj.snapshot_path:
        raise HTTPException(status_code=404, detail="run not found")
    snap = Path(obj.snapshot_path)
    npz = snap.with_suffix(".npz")
    if not npz.exists():
        raise HTTPException(status_code=400, detail="series not found; run with save_series=true")
    try:
        z = np.load(npz.as_posix())
        frames = z["frames"]
    except Exception:
        raise HTTPException(status_code=400, detail="invalid series file")
    metrics_list = [compute_metrics(fr) for fr in frames]
    feats = np.asarray(
        [[m["energy"], m["mean"], m["variance"], m["spatial_corr"]] for m in metrics_list],
        dtype=np.float32,
    )
    index_offset = 0
    if payload.window > 1 and feats.shape[0] >= payload.window:
        k = payload.window
        c = np.cumsum(feats, axis=0)
        wsum = c[k - 1 :] - np.concatenate([np.zeros((1, feats.shape[1]), dtype=np.float32), c[:-k]], axis=0)
        feats = wsum / float(k)
        index_offset = k - 1
    if payload.method == "isoforest":
        s = isolation_forest_score(feats)
    elif payload.method == "mean_dist":
        s = pca_outlier_score(feats)
    else:
        raise HTTPException(status_code=400, detail="unknown method")
    root = Path(__file__).resolve().parents[3]
    out_dir = root / "aetherlab" / "data" / "outputs"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = int(time.time())
    out_path = out_dir / f"ai_series_{obj.id}_{stamp}.csv"
    with open(out_path.as_posix(), "w", encoding="utf-8") as f:
        f.write("index,score,energy,mean,variance,spatial_corr\n")
        for i, (score, m) in enumerate(zip(s.tolist(), metrics_list[index_offset:], strict=False)):
            f.write(
                f"{i + index_offset},{score},{m['energy']},{m['mean']},{m['variance']},{m['spatial_corr']}\n"
            )
    score_stats = {
        "n": int(s.size),
        "mean": float(np.mean(s)),
        "std": float(np.std(s)),
        "min": float(np.min(s)),
        "max": float(np.max(s)),
        "window": int(payload.window),
        "path": out_path.as_posix(),
    }
    mr = ModelRun(
        experiment_id=obj.experiment_id,
        model_name=f"{payload.method}_series",
        params_json=json.dumps({"window": int(payload.window)}, ensure_ascii=False),
        status="finished",
        metrics_json=json.dumps(score_stats),
    )
    db.add(mr)
    db.commit()
    db.refresh(mr)
    art = Artifact(run_id=obj.id, experiment_id=obj.experiment_id, kind="ai_series_scores", path=out_path.as_posix())
    db.add(art)
    db.commit()
    return {
        "path": out_path.as_posix(),
        "model_run_id": mr.id,
        "artifact_id": art.id,
        "artifact_path": art.path,
    }


class AiRunOnDatasetRequest(BaseModel):
    dataset_id: int
    method: str = "isoforest"
    normalize: str | None = "zscore"
    qc: bool = True


@app.post("/ai/run-on-dataset")
def ai_run_on_dataset(payload: AiRunOnDatasetRequest, db: Session = Depends(get_session)):
    ds = db.get(Dataset, payload.dataset_id)
    if ds is None:
        raise HTTPException(status_code=404, detail="dataset not found")
    p = Path(ds.path)
    root = Path(__file__).resolve().parents[3]
    try:
        arr = load_array(p)
        if arr.ndim == 2:
            features = process_map_to_features(p, root, normalize=payload.normalize, qc=payload.qc)
        else:
            features = process_strain_to_features(p, root, normalize=payload.normalize, qc=payload.qc)
        z = np.load(features.as_posix())
        X = z["features"].reshape(-1, 1)
        qc_path = features.with_suffix(".qc.json")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"etl failed: {e}")
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
    score_stats = {
        "n": int(s.size),
        "mean": float(np.mean(s)),
        "std": float(np.std(s)),
        "min": float(np.min(s)),
        "max": float(np.max(s)),
        "path": out_path.as_posix(),
        "features_path": features.as_posix(),
        "qc_path": qc_path.as_posix() if payload.qc else None,
    }
    link = db.execute(select(ExperimentDataset).where(ExperimentDataset.dataset_id == ds.id)).scalars().first()
    if link is not None:
        mr = ModelRun(
            experiment_id=link.experiment_id,
            model_name=payload.method,
            params_json=json.dumps({"dataset_id": ds.id, "normalize": payload.normalize}),
            status="finished",
            metrics_json=json.dumps(score_stats),
        )
        db.add(mr)
        db.commit()
        db.refresh(mr)
        art_feat = Artifact(run_id=None, dataset_id=ds.id, kind="etl_features", path=features.as_posix())
        db.add(art_feat)
        db.commit()
        db.refresh(art_feat)
        art_qc = None
        if payload.qc and qc_path.exists():
            art_qc = Artifact(run_id=None, dataset_id=ds.id, kind="etl_qc", path=qc_path.as_posix())
            db.add(art_qc)
            db.commit()
            db.refresh(art_qc)
        art = Artifact(run_id=None, dataset_id=ds.id, kind="ai_scores", path=out_path.as_posix())
        db.add(art)
        db.commit()
        return {
            "path": out_path.as_posix(),
            "features_path": features.as_posix(),
            "qc_path": qc_path.as_posix() if payload.qc else None,
            "model_run_id": mr.id,
            "artifact_path": art.path,
            "artifact_features_id": art_feat.id,
            "artifact_qc_id": art_qc.id if art_qc is not None else None,
        }
    return {
        "path": out_path.as_posix(),
        "features_path": features.as_posix(),
        "qc_path": qc_path.as_posix() if payload.qc else None,
    }


@app.get("/ai/download")
def ai_download(path: str):
    p = _safe_download_path(Path(path))
    return FileResponse(p)


@app.get("/reports/run/{run_id}/html")
def report_run_html(run_id: int, crop: int = Query(default=64, ge=8, le=512), db: Session = Depends(get_session)):
    obj = db.get(SimulationRun, run_id)
    if obj is None or not obj.snapshot_path:
        raise HTTPException(status_code=404, detail="run not found")
    snap = Path(obj.snapshot_path)
    if not snap.exists():
        raise HTTPException(status_code=404, detail="snapshot not found")
    snap_b = snap.read_bytes()
    try:
        u = _load_field_for_run(obj)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="field not found")
    k, ps = power_spectrum_radial(u)
    ac = autocorr2d(u, normalize=True)
    h, w = ac.shape
    c0 = h // 2
    c1 = w // 2
    half = min(crop // 2, c0, c1)
    cut = ac[c0 - half : c0 + half, c1 - half : c1 + half]
    series_metrics = None
    npz = snap.with_suffix(".npz")
    if npz.exists():
        try:
            z = np.load(npz.as_posix())
            frames = z["frames"]
            series_metrics = [compute_metrics(fr) for fr in frames]
        except Exception:
            series_metrics = None
    html = build_run_html(
        run_id,
        snapshot_png=snap_b,
        spectrum=(k, ps),
        autocorr=cut,
        series_metrics=series_metrics,
        title=f"Reporte Run {run_id}",
    )
    root = Path(__file__).resolve().parents[3]
    out_dir = root / "aetherlab" / "data" / "outputs"
    out_dir.mkdir(parents=True, exist_ok=True)
    h = hashlib.sha256(html.encode("utf-8")).hexdigest()[:12]
    out_path = out_dir / f"report_run_{run_id}_{h}.html"
    if not out_path.exists():
        out_path.write_text(html, encoding="utf-8")
    existing = (
        db.execute(
            select(Artifact).where(
                Artifact.run_id == run_id,
                Artifact.kind == "report_html_run",
                Artifact.path == out_path.as_posix(),
            )
        )
        .scalars()
        .first()
    )
    if existing is None:
        db.add(
            Artifact(
                run_id=run_id,
                experiment_id=obj.experiment_id,
                kind="report_html_run",
                path=out_path.as_posix(),
            )
        )
        db.commit()
    return Response(content=html, media_type="text/html")

@app.get("/reports/experiment/{exp_id}/html")
def report_experiment_html(exp_id: int, db: Session = Depends(get_session)):
    exp = db.get(Experiment, exp_id)
    if exp is None:
        raise HTTPException(status_code=404, detail="experiment not found")
    rows = db.execute(select(SimulationRun).where(SimulationRun.experiment_id == exp_id)).scalars().all()
    cards = []
    agg = {"mean": [], "std": []}
    for r in rows:
        if not r.snapshot_path:
            continue
        p = Path(r.snapshot_path)
        if not p.exists():
            continue
        snap_b64 = "data:image/png;base64," + base64.b64encode(p.read_bytes()).decode()
        arts = db.execute(select(Artifact).where(Artifact.run_id == r.id)).scalars().all()
        links = "".join([f"<li><a href='/artifacts/{a.id}/download'>{a.kind}</a></li>" for a in arts])
        try:
            u = _load_field_for_run(r)
            m = float(np.mean(u))
            s = float(np.std(u))
            agg["mean"].append(m)
            agg["std"].append(s)
            stats = f"<div>mean={m:.3f} std={s:.3f}</div>"
        except Exception:
            stats = "<div>sin métricas</div>"
        cards.append(
            f"<div class='card'><h3>Run {r.id} ({r.status})</h3>"
            f"<img src='{snap_b64}'/><ul>{links or '<li>Sin artefactos</li>'}</ul>{stats}</div>"
        )
    mrs = db.execute(select(ModelRun).where(ModelRun.experiment_id == exp_id)).scalars().all()
    models = "".join([f"<li>{m.model_name}: {m.status}</li>" for m in mrs]) or "<li>Sin modelos</li>"
    if agg["mean"]:
        exp_stats = f"<li>mean_avg={np.mean(agg['mean']):.3f}</li><li>std_avg={np.mean(agg['std']):.3f}</li>"
    else:
        exp_stats = "<li>sin métricas</li>"
    html = (
        "<!doctype html><html lang='es'><head><meta charset='utf-8'>"
        f"<title>Reporte Experimento {exp_id}</title>"
        "<style>body{font-family:Arial;margin:20px}.grid{display:grid;"
        "grid-template-columns:repeat(3,1fr);gap:16px}.card{border:1px solid #ccc;"
        "padding:10px;border-radius:8px}img{max-width:100%}ul{margin-top:8px}</style></head><body>"
        f"<h1>Reporte de Experimento {exp.name}</h1>"
        f"<h2>Modelos</h2><ul>{models}</ul>"
        f"<h2>Mini-métricas</h2><ul>{exp_stats}</ul>"
        f"<h2>Runs</h2><div class='grid'>{''.join(cards) if cards else '<p>Sin snapshots</p>'}</div>"
        "</body></html>"
    )
    root = Path(__file__).resolve().parents[3]
    out_dir = root / "aetherlab" / "data" / "outputs"
    out_dir.mkdir(parents=True, exist_ok=True)
    h = hashlib.sha256(html.encode("utf-8")).hexdigest()[:12]
    out_path = out_dir / f"report_experiment_{exp_id}_{h}.html"
    if not out_path.exists():
        out_path.write_text(html, encoding="utf-8")
    existing = (
        db.execute(
            select(Artifact).where(
                Artifact.experiment_id == exp_id,
                Artifact.kind == "report_html_experiment",
                Artifact.path == out_path.as_posix(),
            )
        )
        .scalars()
        .first()
    )
    if existing is None:
        db.add(
            Artifact(
                run_id=None,
                dataset_id=None,
                experiment_id=exp_id,
                kind="report_html_experiment",
                path=out_path.as_posix(),
            )
        )
        db.commit()
    return Response(content=html, media_type="text/html")


def _as_2d(arr: np.ndarray) -> np.ndarray:
    a = np.asarray(arr)
    if a.ndim == 2:
        return a.astype(np.float32)
    raise ValueError("expected 2D array")


def _align_2d(a: np.ndarray, b: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    a2 = _as_2d(a)
    b2 = _as_2d(b)
    ha, wa = a2.shape
    hb, wb = b2.shape
    h = min(ha, hb)
    w = min(wa, wb)
    a0 = a2[(ha - h) // 2 : (ha - h) // 2 + h, (wa - w) // 2 : (wa - w) // 2 + w]
    b0 = b2[(hb - h) // 2 : (hb - h) // 2 + h, (wb - w) // 2 : (wb - w) // 2 + w]
    return a0, b0


def _compare_fields(a: np.ndarray, b: np.ndarray) -> dict:
    a0, b0 = _align_2d(a, b)
    d = a0 - b0
    mse = float(np.mean(d**2))
    mae = float(np.mean(np.abs(d)))
    corr = float(corrcoef2d(a0, b0))
    k1, ps1 = power_spectrum_radial(a0)
    k2, ps2 = power_spectrum_radial(b0)
    n = int(min(len(ps1), len(ps2)))
    if n > 0:
        p1 = ps1[:n] / (float(np.sum(ps1[:n])) + 1e-12)
        p2 = ps2[:n] / (float(np.sum(ps2[:n])) + 1e-12)
        ps_l2 = float(np.linalg.norm(p1 - p2))
    else:
        ps_l2 = float("nan")
    return {
        "shape_a": list(a0.shape),
        "shape_b": list(b0.shape),
        "mse": mse,
        "mae": mae,
        "corr": corr,
        "spectrum_l2": ps_l2,
        "a_stats": {"mean": float(np.mean(a0)), "std": float(np.std(a0))},
        "b_stats": {"mean": float(np.mean(b0)), "std": float(np.std(b0))},
    }


def _compare_figure_png(a: np.ndarray, b: np.ndarray, title: str) -> bytes:
    a0, b0 = _align_2d(a, b)
    d = a0 - b0
    fig = Figure(figsize=(10, 3.6), dpi=140)
    ax1 = fig.add_subplot(1, 3, 1)
    ax2 = fig.add_subplot(1, 3, 2)
    ax3 = fig.add_subplot(1, 3, 3)
    ax1.set_title("A")
    ax2.set_title("B")
    ax3.set_title("A-B")
    im1 = ax1.imshow(a0, cmap="viridis", origin="lower")
    im2 = ax2.imshow(b0, cmap="viridis", origin="lower")
    im3 = ax3.imshow(d, cmap="coolwarm", origin="lower")
    for ax in (ax1, ax2, ax3):
        ax.set_xticks([])
        ax.set_yticks([])
    fig.suptitle(title)
    fig.colorbar(im1, ax=ax1, fraction=0.046, pad=0.04)
    fig.colorbar(im2, ax=ax2, fraction=0.046, pad=0.04)
    fig.colorbar(im3, ax=ax3, fraction=0.046, pad=0.04)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight")
    return buf.getvalue()


def _safe_data_path(p: Path) -> Path:
    root = Path(__file__).resolve().parents[3]
    base = root / "aetherlab" / "data"
    pp = p.resolve()
    if not pp.exists() or not pp.as_posix().startswith(base.resolve().as_posix()):
        raise HTTPException(status_code=404, detail="file not found")
    return pp


def _load_dataset_array(path: Path) -> np.ndarray:
    if path.suffix == ".npy":
        return np.load(path.as_posix())
    if path.suffix == ".npz":
        z = np.load(path.as_posix())
        key = "map" if "map" in z.files else z.files[0]
        return z[key]
    if path.suffix == ".csv":
        import pandas as pd  # noqa: WPS433

        df = pd.read_csv(path.as_posix())
        num = df.select_dtypes(include=["number"])
        return num.to_numpy()
    if path.suffix == ".parquet":
        import pandas as pd  # noqa: WPS433

        df = pd.read_parquet(path.as_posix())
        num = df.select_dtypes(include=["number"])
        return num.to_numpy()
    import h5py  # noqa: WPS433

    with h5py.File(path.as_posix(), "r") as f:
        key = "map" if "map" in f.keys() else list(f.keys())[0]
        return np.asarray(f[key][()])


@app.get("/compare/run-run")
def compare_run_run(run_a: int, run_b: int, db: Session = Depends(get_session)):
    a = db.get(SimulationRun, run_a)
    b = db.get(SimulationRun, run_b)
    if a is None or b is None or not a.snapshot_path or not b.snapshot_path:
        raise HTTPException(status_code=404, detail="run not found")
    ua = _load_field_for_run(a)
    ub = _load_field_for_run(b)
    return {"run_a": run_a, "run_b": run_b, "metrics": _compare_fields(ua, ub)}


@app.get("/compare/run-run/figure.png")
def compare_run_run_figure(run_a: int, run_b: int, db: Session = Depends(get_session)):
    a = db.get(SimulationRun, run_a)
    b = db.get(SimulationRun, run_b)
    if a is None or b is None or not a.snapshot_path or not b.snapshot_path:
        raise HTTPException(status_code=404, detail="run not found")
    ua = _load_field_for_run(a)
    ub = _load_field_for_run(b)
    png = _compare_figure_png(ua, ub, title=f"Run {run_a} vs Run {run_b}")
    root = Path(__file__).resolve().parents[3]
    out_dir = root / "aetherlab" / "data" / "outputs"
    out_dir.mkdir(parents=True, exist_ok=True)
    h = hashlib.sha256(png).hexdigest()[:12]
    out_path = out_dir / f"compare_run_run_{run_a}_{run_b}_{h}.png"
    if not out_path.exists():
        out_path.write_bytes(png)
    existing = (
        db.execute(
            select(Artifact).where(
                Artifact.run_id == run_a,
                Artifact.kind == "compare_run_run_png",
                Artifact.path == out_path.as_posix(),
            )
        )
        .scalars()
        .first()
    )
    if existing is None:
        db.add(
            Artifact(
                run_id=run_a,
                experiment_id=a.experiment_id,
                kind="compare_run_run_png",
                path=out_path.as_posix(),
            )
        )
        db.commit()
    return Response(content=png, media_type="image/png")


@app.get("/compare/run-dataset")
def compare_run_dataset(run_id: int, dataset_id: int, db: Session = Depends(get_session)):
    r = db.get(SimulationRun, run_id)
    ds = db.get(Dataset, dataset_id)
    if r is None or not r.snapshot_path:
        raise HTTPException(status_code=404, detail="run not found")
    if ds is None:
        raise HTTPException(status_code=404, detail="dataset not found")
    ua = _load_field_for_run(r)
    p = _safe_data_path(Path(ds.path))
    arr = _load_dataset_array(p)
    return {"run_id": run_id, "dataset_id": dataset_id, "metrics": _compare_fields(ua, arr)}


@app.get("/compare/run-dataset/figure.png")
def compare_run_dataset_figure(run_id: int, dataset_id: int, db: Session = Depends(get_session)):
    r = db.get(SimulationRun, run_id)
    ds = db.get(Dataset, dataset_id)
    if r is None or not r.snapshot_path:
        raise HTTPException(status_code=404, detail="run not found")
    if ds is None:
        raise HTTPException(status_code=404, detail="dataset not found")
    ua = _load_field_for_run(r)
    p = _safe_data_path(Path(ds.path))
    arr = _load_dataset_array(p)
    png = _compare_figure_png(ua, arr, title=f"Run {run_id} vs Dataset {dataset_id}")
    root = Path(__file__).resolve().parents[3]
    out_dir = root / "aetherlab" / "data" / "outputs"
    out_dir.mkdir(parents=True, exist_ok=True)
    h = hashlib.sha256(png).hexdigest()[:12]
    out_path = out_dir / f"compare_run_dataset_{run_id}_{dataset_id}_{h}.png"
    if not out_path.exists():
        out_path.write_bytes(png)
    existing = (
        db.execute(
            select(Artifact).where(
                Artifact.run_id == run_id,
                Artifact.dataset_id == dataset_id,
                Artifact.kind == "compare_run_dataset_png",
                Artifact.path == out_path.as_posix(),
            )
        )
        .scalars()
        .first()
    )
    if existing is None:
        db.add(
            Artifact(
                run_id=run_id,
                dataset_id=dataset_id,
                experiment_id=r.experiment_id,
                kind="compare_run_dataset_png",
                path=out_path.as_posix(),
            )
        )
        db.commit()
    return Response(content=png, media_type="image/png")

@app.post("/data/cleanup")
def data_cleanup(days: int = 30):
    root = Path(__file__).resolve().parents[3]
    base = root / "aetherlab" / "data"
    targets = [base / "outputs", base / "features"]
    now = time.time()
    removed = []
    for t in targets:
        if not t.exists():
            continue
        for p in t.glob("*"):
            try:
                age = now - p.stat().st_mtime
                if age > days * 86400:
                    p.unlink()
                    removed.append(p.as_posix())
            except Exception:
                continue
    return {"removed": removed, "days": days}
