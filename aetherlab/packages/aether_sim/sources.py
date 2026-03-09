import numpy as np


def gaussian_pulse(
    x: np.ndarray, y: np.ndarray, t: int, cx: float, cy: float, sigma: float, duration: int, amplitude: float = 1.0
) -> np.ndarray:
    g = np.exp(-(((x - cx) ** 2 + (y - cy) ** 2) / (2.0 * sigma**2)))
    return amplitude * g if t < duration else np.zeros_like(g)


def periodic_gaussian(
    x: np.ndarray, y: np.ndarray, t: int, cx: float, cy: float, sigma: float, amplitude: float, dt: float, freq: float
) -> np.ndarray:
    g = np.exp(-(((x - cx) ** 2 + (y - cy) ** 2) / (2.0 * sigma**2)))
    return amplitude * np.sin(2.0 * np.pi * freq * (t * dt)) * g


def stochastic(x: np.ndarray, y: np.ndarray, t: int, amplitude: float) -> np.ndarray:
    # Deterministic RNG from t to keep function pure w.r.t simulator RNG
    rng = np.random.default_rng(seed=t + 12345)
    return amplitude * rng.standard_normal(size=x.shape).astype(np.float32)


def top_hat(
    x: np.ndarray,
    y: np.ndarray,
    t: int,
    cx: float,
    cy: float,
    radius: float,
    amplitude: float = 1.0,
    duration: int | None = None,
) -> np.ndarray:
    r2 = (x - cx) ** 2 + (y - cy) ** 2
    mask = (r2 <= radius**2).astype(np.float32)
    if duration is not None and t >= duration:
        return np.zeros_like(mask)
    return amplitude * mask


def lorentzian(
    x: np.ndarray,
    y: np.ndarray,
    t: int,
    cx: float,
    cy: float,
    gamma: float,
    amplitude: float = 1.0,
    duration: int | None = None,
) -> np.ndarray:
    r2 = (x - cx) ** 2 + (y - cy) ** 2
    lorentz = amplitude / (1.0 + (r2 / (gamma**2)))
    if duration is not None and t >= duration:
        return np.zeros_like(lorentz)
    return lorentz
