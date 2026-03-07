from typing import Callable, Optional, Literal
import numpy as np
from aetherlab.packages.aether_physics.numerics import update

class Simulator2D:
    def __init__(self, nx: int = 128, ny: int = 128, dt: float = 0.01, steps: int = 1000, lam: float = 1.0, diff: float = 0.1, noise: float = 0.0, seed: int | None = None, boundary: Literal["periodic","fixed","absorbing"] = "periodic"):
        self.nx = nx
        self.ny = ny
        self.dt = dt
        self.steps = steps
        self.lam = lam
        self.diff = diff
        self.noise = noise
        self.boundary = boundary
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
        if self.boundary in ("fixed","absorbing"):
            # Dirichlet-like boundary as approximation
            self.u[0, :] = 0.0
            self.u[-1, :] = 0.0
            self.u[:, 0] = 0.0
            self.u[:, -1] = 0.0
            if self.boundary == "absorbing":
                # Light damping near borders
                w = 3
                self.u[:w, :] *= 0.5
                self.u[-w:, :] *= 0.5
                self.u[:, :w] *= 0.5
                self.u[:, -w:] *= 0.5
        return self.u

    def run(self, callback: Optional[Callable[[int, np.ndarray], None]] = None) -> None:
        for t in range(self.steps):
            u = self.step(t)
            if callback is not None:
                callback(t, u)
