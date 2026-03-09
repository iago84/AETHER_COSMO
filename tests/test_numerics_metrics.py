import numpy as np

from aetherlab.packages.aether_sim.metrics import autocorr2d, compute_metrics, power_spectrum_radial


def test_autocorr_center_peak():
    u = np.zeros((16, 16), dtype=np.float32)
    u[8, 8] = 1.0
    ac = autocorr2d(u, normalize=True)
    c = ac[8, 8]
    assert np.isfinite(c)
    assert abs(c - 1.0) < 1e-3


def test_power_spectrum_constant_field():
    u = np.ones((16, 16), dtype=np.float32)
    k, ps = power_spectrum_radial(u)
    assert len(k) == len(ps) and len(ps) > 0
    assert ps[0] > 0.0
    if len(ps) > 1:
        assert float(np.max(ps[1:])) < ps[0] * 1e-3


def test_compute_metrics_zero_field():
    u = np.zeros((8, 8), dtype=np.float32)
    m = compute_metrics(u)
    assert m["energy"] == 0.0
    assert m["variance"] == 0.0
    assert "spatial_corr" in m
