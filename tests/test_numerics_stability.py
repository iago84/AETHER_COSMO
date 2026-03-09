import numpy as np

from aetherlab.packages.aether_sim.metrics import compute_metrics
from aetherlab.packages.aether_sim.simulator2d import Simulator2D
from aetherlab.packages.aether_sim.sources import gaussian_pulse


def test_energy_zero_source_stays_zero():
    sim = Simulator2D(nx=16, ny=16, steps=5, dt=0.05, lam=0.5, diff=0.2, noise=0.0, seed=0)
    sim.set_source(lambda x, y, t: np.zeros_like(x, dtype=np.float32))
    energies = []

    def cb(t, u):
        energies.append(compute_metrics(u)["energy"])

    sim.run(callback=cb)
    assert all(e == 0.0 for e in energies)


def test_energy_finite_under_gaussian_pulse():
    sim = Simulator2D(nx=16, ny=16, steps=10, dt=0.05, lam=0.5, diff=0.2, noise=0.0, seed=0)
    sim.set_source(lambda x, y, t: gaussian_pulse(x, y, t, 8, 8, sigma=3.0, duration=5, amplitude=1.0))
    energies = []

    def cb(t, u):
        e = compute_metrics(u)["energy"]
        energies.append(e)
        assert np.isfinite(e) and e >= 0.0 and e < 1e6

    sim.run(callback=cb)
    assert any(e > 0.0 for e in energies)
