import numpy as np


def laplacian(u: np.ndarray) -> np.ndarray:
    return np.roll(u, 1, 0) + np.roll(u, -1, 0) + np.roll(u, 1, 1) + np.roll(u, -1, 1) - 4.0 * u


def update(
    u: np.ndarray,
    source: np.ndarray,
    lam: float,
    diff: float,
    dt: float,
    noise: float = 0.0,
    rng: np.random.Generator | None = None,
) -> np.ndarray:
    n = laplacian(u)
    if rng is None:
        rng = np.random.default_rng()
    eta = noise * rng.standard_normal(size=u.shape) if noise > 0.0 else 0.0
    return u + dt * (source - lam * u + diff * n) + eta
