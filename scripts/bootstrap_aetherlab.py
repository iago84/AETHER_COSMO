import argparse
import sys
from pathlib import Path
from textwrap import dedent


def write(path: Path, content: str, overwrite: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not overwrite:
        return
    path.write_text(content, encoding="utf-8")


def ensure_pkg(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    init_file = path / "__init__.py"
    if not init_file.exists():
        init_file.write_text("", encoding="utf-8")


def files_for_mvp(base: Path) -> dict[Path, str]:
    result: dict[Path, str] = {}
    ensure_pkg(base / "packages" / "aether_core")
    ensure_pkg(base / "packages" / "aether_physics")
    ensure_pkg(base / "packages" / "aether_sim")
    ensure_pkg(base / "packages" / "aether_viz")
    (base / "apps" / "api").mkdir(parents=True, exist_ok=True)
    (base / "apps" / "desktop").mkdir(parents=True, exist_ok=True)
    (base / "data" / "outputs").mkdir(parents=True, exist_ok=True)
    (base / "tests").mkdir(parents=True, exist_ok=True)
    result[base / "packages" / "aether_core" / "schemas.py"] = dedent(
        """
        from typing import Optional, Literal, List, Dict
        from pydantic import BaseModel, Field

        class SimulationConfig(BaseModel):
            dt: float = 0.01
            steps: int = 1000
            nx: int = 128
            ny: int = 128
            boundary: Literal["periodic", "fixed", "absorbing"] = "periodic"
            seed: Optional[int] = None

        class EventConfig(BaseModel):
            kind: Literal["supernova", "black_hole_merger", "pulse", "stochastic", "periodic", "dataset"] = "pulse"
            intensity: float = 1.0
            x: float = 0.5
            y: float = 0.5
            duration: float = 1.0
            frequency: Optional[float] = None

        class AetherFieldConfig(BaseModel):
            lambda_: float = Field(1.0, alias="lambda")
            diffusion: float = 0.1
            noise: float = 0.0

        class DatasetConfig(BaseModel):
            name: str
            path: str
            meta: Dict[str, str] = {}

        class ExperimentConfig(BaseModel):
            project: str
            name: str
            tags: List[str] = []

        class TrainingConfig(BaseModel):
            method: Literal["iforest", "pca", "dbscan", "autoencoder", "cae", "transformer"] = "iforest"
            params: Dict[str, float] = {}

        class ReportConfig(BaseModel):
            title: str = "AETHERLAB Report"
            include_figures: bool = True
        """.strip()
    )
    result[base / "packages" / "aether_core" / "models_db.py"] = dedent(
        """
        from typing import Optional
        from sqlalchemy.orm import declarative_base, relationship, Mapped, mapped_column
        from sqlalchemy import String, Integer, ForeignKey, DateTime, func, Text

        Base = declarative_base()

        class Project(Base):
            __tablename__ = "projects"
            id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
            name: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
            description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
            created_at: Mapped = mapped_column(DateTime(timezone=True), server_default=func.now())
            experiments: Mapped[list["Experiment"]] = relationship(back_populates="project", cascade="all, delete-orphan")

        class Experiment(Base):
            __tablename__ = "experiments"
            id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
            project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False)
            name: Mapped[str] = mapped_column(String(200), nullable=False)
            created_at: Mapped = mapped_column(DateTime(timezone=True), server_default=func.now())
            project: Mapped["Project"] = relationship(back_populates="experiments")
            runs: Mapped[list["SimulationRun"]] = relationship(back_populates="experiment", cascade="all, delete-orphan")

        class SimulationRun(Base):
            __tablename__ = "simulation_runs"
            id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
            experiment_id: Mapped[int] = mapped_column(ForeignKey("experiments.id"), nullable=False)
            status: Mapped[str] = mapped_column(String(50), default="created")
            created_at: Mapped = mapped_column(DateTime(timezone=True), server_default=func.now())
            snapshot_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
            experiment: Mapped["Experiment"] = relationship(back_populates="runs")
        """.strip()
    )
    result[base / "packages" / "aether_core" / "db.py"] = dedent(
        """
        from pathlib import Path
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        def default_sqlite_url(root: str | None = None) -> str:
            if root is None:
                root = str(Path(__file__).resolve().parents[3])
            db_path = Path(root) / "aetherlab" / "data" / "outputs" / "aetherlab.db"
            db_path.parent.mkdir(parents=True, exist_ok=True)
            return f"sqlite+pysqlite:///{db_path.as_posix()}"

        ENGINE = create_engine(default_sqlite_url(), future=True)
        SessionLocal = sessionmaker(bind=ENGINE, autoflush=False, autocommit=False, future=True)
        """.strip()
    )
    result[base / "packages" / "aether_physics" / "numerics.py"] = dedent(
        """
        import numpy as np

        def laplacian(u: np.ndarray) -> np.ndarray:
            return np.roll(u, 1, 0) + np.roll(u, -1, 0) + np.roll(u, 1, 1) + np.roll(u, -1, 1) - 4.0 * u

        def update(u: np.ndarray, source: np.ndarray, lam: float, diff: float, dt: float, noise: float = 0.0, rng: np.random.Generator | None = None) -> np.ndarray:
            n = laplacian(u)
            if rng is None:
                rng = np.random.default_rng()
            eta = noise * rng.standard_normal(size=u.shape) if noise > 0.0 else 0.0
            return u + dt * (source - lam * u + diff * n) + eta
        """.strip()
    )
    result[base / "packages" / "aether_sim" / "sources.py"] = dedent(
        """
        import numpy as np

        def gaussian_pulse(x: np.ndarray, y: np.ndarray, t: int, cx: float, cy: float, sigma: float, duration: int, amplitude: float = 1.0) -> np.ndarray:
            g = np.exp(-(((x - cx) ** 2 + (y - cy) ** 2) / (2.0 * sigma ** 2)))
            return amplitude * g if t < duration else np.zeros_like(g)
        """.strip()
    )
    result[base / "packages" / "aether_sim" / "simulator2d.py"] = dedent(
        """
        from typing import Callable, Optional
        import numpy as np
        from aether_physics.numerics import update

        class Simulator2D:
            def __init__(self, nx: int = 128, ny: int = 128, dt: float = 0.01, steps: int = 1000, lam: float = 1.0, diff: float = 0.1, noise: float = 0.0, seed: int | None = None):
                self.nx = nx
                self.ny = ny
                self.dt = dt
                self.steps = steps
                self.lam = lam
                self.diff = diff
                self.noise = noise
                self.rng = np.random.default_rng(seed)
                self.u = np.zeros((ny, nx), dtype=np.float32)
                self.source = np.zeros_like(self.u, dtype=np.float32)
                self.source_func: Optional[Callable[[np.ndarray, np.ndarray, int], np.ndarray]] = None

            def set_source(self, func: Callable[[np.ndarray, np.ndarray, int], np.ndarray]) -> None:
                self.source_func = func

            def step(self, t: int) -> np.ndarray:
                if self.source_func is not None:
                    y, x = np.mgrid[0 : self.ny, 0 : self.nx]
                    self.source[:] = self.source_func(x, y, t)
                self.u = update(self.u, self.source, self.lam, self.diff, self.dt, self.noise, self.rng)
                return self.u

            def run(self, callback: Optional[Callable[[int, np.ndarray], None]] = None) -> None:
                for t in range(self.steps):
                    u = self.step(t)
                    if callback is not None:
                        callback(t, u)
        """.strip()
    )
    result[base / "packages" / "aether_viz" / "plots.py"] = dedent(
        """
        import numpy as np
        import matplotlib.pyplot as plt

        def show_field(u: np.ndarray):
            fig, ax = plt.subplots()
            im = ax.imshow(u, cmap="viridis", origin="lower")
            fig.colorbar(im, ax=ax)
            ax.set_xlabel("x")
            ax.set_ylabel("y")
            ax.set_title("Aether field")
            return fig, ax
        """.strip()
    )
    result[base / "apps" / "api" / "db.py"] = dedent(
        """
        from aether_core.db import SessionLocal
        from sqlalchemy.orm import Session
        from contextlib import contextmanager

        @contextmanager
        def get_session() -> Session:
            db = SessionLocal()
            try:
                yield db
            finally:
                db.close()
        """.strip()
    )
    result[base / "apps" / "api" / "main.py"] = dedent(
        """
        from fastapi import FastAPI, Depends
        from pydantic import BaseModel
        from sqlalchemy.orm import Session
        from .db import get_session
        from aether_core.models_db import Base, Project, Experiment
        from aether_core.db import ENGINE

        app = FastAPI(title="AETHERLAB API", version="0.1.0")

        @app.on_event("startup")
        def on_startup():
            Base.metadata.create_all(bind=ENGINE)

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

        @app.post("/simulations")
        def create_simulation():
            return {"id": "sim-1"}

        @app.post("/simulations/{sim_id}/run")
        def run_simulation(sim_id: str):
            return {"sim_id": sim_id, "status": "queued"}

        @app.get("/simulations/{sim_id}/status")
        def status(sim_id: str):
            return {"sim_id": sim_id, "state": "unknown"}
        """.strip()
    )
    result[base / "apps" / "desktop" / "main.py"] = dedent(
        """
        import sys
        from PyQt6.QtWidgets import QApplication, QMainWindow

        def main():
            app = QApplication(sys.argv)
            w = QMainWindow()
            w.setWindowTitle("AETHERLAB")
            w.resize(1024, 720)
            w.show()
            sys.exit(app.exec())

        if __name__ == "__main__":
            main()
        """.strip()
    )
    result[base.parent / "requirements.txt"] = dedent(
        """
        fastapi
        uvicorn
        pydantic
        SQLAlchemy>=2.0
        numpy
        matplotlib
        PyQt6
        """.strip()
    )
    result[base.parent / "scripts" / "init_db.py"] = dedent(
        """
        from aetherlab.packages.aether_core.models_db import Base
        from aetherlab.packages.aether_core.db import ENGINE

        if __name__ == "__main__":
            Base.metadata.create_all(bind=ENGINE)
            print("OK")
        """.strip()
    )
    result[base.parent / "scripts" / "run_sim_example.py"] = dedent(
        """
        from pathlib import Path
        import numpy as np
        from aetherlab.packages.aether_sim.simulator2d import Simulator2D
        from aetherlab.packages.aether_sim.sources import gaussian_pulse
        from aetherlab.packages.aether_viz.plots import show_field

        root = Path(__file__).resolve().parents[1]
        out = root / "aetherlab" / "data" / "outputs" / "snapshot.png"

        sim = Simulator2D(nx=128, ny=128, steps=100, dt=0.05, lam=0.5, diff=0.2, noise=0.0, seed=123)
        cx, cy = 64, 64
        sim.set_source(lambda x, y, t: gaussian_pulse(x, y, t, cx, cy, sigma=8.0, duration=20, amplitude=1.0))
        sim.run()
        fig, _ = show_field(sim.u)
        fig.savefig(out.as_posix())
        print(out.as_posix())
        """.strip()
    )
    return result


def files_for_full(base: Path) -> dict[Path, str]:
    result = files_for_mvp(base)
    ensure_pkg(base / "packages" / "aether_data")
    ensure_pkg(base / "packages" / "aether_ai")
    ensure_pkg(base / "packages" / "aether_report")
    (base / "apps" / "web").mkdir(parents=True, exist_ok=True)
    (base / "infra" / "docker").mkdir(parents=True, exist_ok=True)
    (base / "infra" / "ci").mkdir(parents=True, exist_ok=True)
    (base / "data" / "raw").mkdir(parents=True, exist_ok=True)
    (base / "data" / "processed").mkdir(parents=True, exist_ok=True)
    (base / "data" / "features").mkdir(parents=True, exist_ok=True)
    (base / "notebooks").mkdir(parents=True, exist_ok=True)
    result[base / "packages" / "aether_data" / "registry.py"] = "REGISTRY: dict[str, dict] = {}\n"
    result[base / "packages" / "aether_ai" / "baseline.py"] = "def score(x):\n    return 0.0\n"
    result[base / "packages" / "aether_report" / "builder.py"] = "def build_report(path: str):\n    return path\n"
    return result


def build(mode: str, root: Path, overwrite: bool) -> None:
    base = root / "aetherlab"
    files = files_for_full(base) if mode == "full" else files_for_mvp(base)
    for p, content in files.items():
        write(p, content + ("\n" if not content.endswith("\n") else ""), overwrite=overwrite)
    packages_root = base / "packages"
    for pkg in [
        "aether_core",
        "aether_physics",
        "aether_sim",
        "aether_viz",
        "aether_data",
        "aether_ai",
        "aether_report",
    ]:
        pkg_path = packages_root / pkg
        if pkg_path.exists():
            ensure_pkg(pkg_path)
    print(f"Estructura generada en: {base}")
    print("Archivos creados o preservados:")
    for p in sorted(files.keys()):
        rel = p.relative_to(root)
        print(f"- {rel}")
    print("Hecho")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="bootstrap_aetherlab", add_help=True)
    parser.add_argument("--mode", choices=["mvp", "full"], default="mvp")
    parser.add_argument("--root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    build(args.mode, root, args.overwrite)
    return 0


if __name__ == "__main__":
    sys.exit(main())
