import numpy as np

from aetherlab.packages.aether_sim.metrics import compute_metrics
from aetherlab.packages.aether_sim.simulator2d import Simulator2D
from aetherlab.packages.aether_sim.sources import gaussian_pulse


def test_simulator2d_smoke():
    sim = Simulator2D(nx=16, ny=16, steps=3, dt=0.05, lam=0.5, diff=0.2, noise=0.0, seed=42)
    sim.set_source(lambda x, y, t: gaussian_pulse(x, y, t, 8, 8, sigma=3.0, duration=2, amplitude=1.0))
    sim.run()
    m = compute_metrics(sim.u)
    assert "energy" in m and np.isfinite(m["energy"]) and m["energy"] >= 0.0
    assert "variance" in m and np.isfinite(m["variance"]) and m["variance"] >= 0.0
