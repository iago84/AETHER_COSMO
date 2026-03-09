import json
import os
from pathlib import Path

import numpy as np
import redis
from rq import Connection, Queue, Worker

from aetherlab.packages.aether_core.db import SessionLocal
from aetherlab.packages.aether_core.models_db import SimulationRun
from aetherlab.packages.aether_sim.metrics import compute_metrics
from aetherlab.packages.aether_sim.simulator2d import Simulator2D
from aetherlab.packages.aether_sim.sources import (
    gaussian_pulse,
    lorentzian,
    periodic_gaussian,
    stochastic,
    top_hat,
)
from aetherlab.packages.aether_viz.plots import show_field


def run_sim_job(payload: dict) -> dict:
    db = SessionLocal()
    try:
        run_id = int(payload["run_id"])
        run = db.get(SimulationRun, run_id)
        if run is None:
            return {"error": "run not found"}
        run.status = "running"
        db.commit()
        sim = Simulator2D(
            nx=int(payload.get("nx", 128)),
            ny=int(payload.get("ny", 128)),
            steps=int(payload.get("steps", 100)),
            dt=float(payload.get("dt", 0.05)),
            lam=float(payload.get("lam", 0.5)),
            diff=float(payload.get("diff", 0.2)),
            noise=float(payload.get("noise", 0.0)),
            seed=123,
            boundary=str(payload.get("boundary", "periodic")),
        )
        sk = str(payload.get("source_kind", "gaussian_pulse"))
        cx = float(payload.get("cx", 64))
        cy = float(payload.get("cy", 64))
        sigma = float(payload.get("sigma", 8.0))
        duration = int(payload.get("duration", 20))
        amp = float(payload.get("amplitude", 1.0))
        freq = float(payload.get("frequency", 1.0))
        radius = float(payload.get("radius", 8.0))
        gamma = float(payload.get("gamma", 8.0))
        save_series = bool(payload.get("save_series", False))
        series_stride = int(payload.get("series_stride", 10))
        if sk == "gaussian_pulse":
            sim.set_source(
                lambda x, y, t: gaussian_pulse(x, y, t, cx, cy, sigma=sigma, duration=duration, amplitude=amp)
            )
        elif sk == "periodic":
            sim.set_source(
                lambda x, y, t: periodic_gaussian(x, y, t, cx, cy, sigma=sigma, amplitude=amp, dt=sim.dt, freq=freq)
            )
        elif sk == "stochastic":
            sim.set_source(lambda x, y, t: stochastic(x, y, t, amplitude=amp))
        elif sk == "top_hat":
            sim.set_source(lambda x, y, t: top_hat(x, y, t, cx, cy, radius=radius, amplitude=amp, duration=duration))
        elif sk == "lorentzian":
            sim.set_source(lambda x, y, t: lorentzian(x, y, t, cx, cy, gamma=gamma, amplitude=amp, duration=duration))
        frames = []
        if save_series:

            def cb(t, u):
                if t % max(1, series_stride) == 0:
                    frames.append(u.copy())

            sim.run(callback=cb)
        else:
            sim.run()
        root = Path(__file__).resolve().parents[1]
        out_dir = root / "aetherlab" / "data" / "outputs"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"snapshot_run_{run_id}.png"
        fig, _ = show_field(sim.u)
        fig.savefig(out_path.as_posix())
        metrics = compute_metrics(sim.u)
        with open(out_path.with_suffix(".json"), "w", encoding="utf-8") as f:
            json.dump(metrics, f)
        np.save(out_path.with_suffix(".npy").as_posix(), sim.u.astype(np.float32))
        if save_series and frames:
            np.savez_compressed(out_path.with_suffix(".npz").as_posix(), frames=np.array(frames, dtype=np.float32))
        run.snapshot_path = out_path.as_posix()
        run.status = "finished"
        db.commit()
        return {"run_id": run_id, "snapshot": run.snapshot_path}
    finally:
        db.close()


if __name__ == "__main__":
    url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    conn = redis.from_url(url)
    with Connection(conn):
        w = Worker([Queue("aetherlab")])
        w.work()
