import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

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
