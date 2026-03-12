import base64
import io
from typing import Any

import numpy as np
from matplotlib.figure import Figure


def _b64img(png_bytes: bytes) -> str:
    return "data:image/png;base64," + base64.b64encode(png_bytes).decode()


def _fig_png(fig: Figure) -> bytes:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight")
    return buf.getvalue()


def _png_from_spectrum(k: np.ndarray, ps: np.ndarray, logy: bool = False) -> bytes:
    fig = Figure(figsize=(5, 3), dpi=120)
    ax = fig.add_subplot(111)
    if logy:
        ax.semilogy(k, ps, label="Espectro radial")
    else:
        ax.plot(k, ps, label="Espectro radial")
    ax.set_xlabel("k")
    ax.set_ylabel("potencia")
    ax.grid(True)
    ax.legend()
    return _fig_png(fig)


def _png_from_autocorr(ac2d: np.ndarray) -> bytes:
    fig = Figure(figsize=(4, 4), dpi=120)
    ax = fig.add_subplot(111)
    im = ax.imshow(ac2d, cmap="viridis", origin="lower")
    fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    return _fig_png(fig)


def _png_from_energy(series_metrics: list[dict[str, Any]]) -> bytes:
    e = np.array([m.get("energy", np.nan) for m in series_metrics], dtype=np.float32)
    fig = Figure(figsize=(5, 3), dpi=120)
    ax = fig.add_subplot(111)
    ax.plot(np.arange(len(e)), e, label="Energía")
    ax.set_xlabel("frame")
    ax.set_ylabel("energía")
    ax.grid(True)
    ax.legend()
    return _fig_png(fig)


def build_run_html(
    run_id: int,
    snapshot_png: bytes | None,
    spectrum: tuple[np.ndarray, np.ndarray] | None,
    autocorr: np.ndarray | None,
    series_metrics: list[dict[str, Any]] | None = None,
    *,
    spectrum_logy: bool = False,
    title: str | None = None,
) -> str:
    snapshot_b64 = _b64img(snapshot_png) if snapshot_png else ""
    spectrum_b64 = ""
    autocorr_b64 = ""
    energy_b64 = ""

    if spectrum is not None:
        k, ps = spectrum
        if k.size and ps.size:
            spectrum_b64 = _b64img(_png_from_spectrum(k, ps, logy=spectrum_logy))

    if autocorr is not None and autocorr.size:
        autocorr_b64 = _b64img(_png_from_autocorr(autocorr))

    if series_metrics:
        energy_b64 = _b64img(_png_from_energy(series_metrics))

    t = title or f"AETHERLAB Reporte Run {run_id}"
    html = f"""
<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8" />
  <title>{t}</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 20px; }}
    .grid {{ display: grid; grid-template-columns: repeat(2, 1fr); gap: 20px; }}
    .card {{ border: 1px solid #ccc; padding: 12px; border-radius: 8px; }}
    img {{ max-width: 100%; height: auto; }}
    h2 {{ margin-top: 0; }}
  </style>
</head>
<body>
  <h1>Reporte de Run {run_id}</h1>
  <div class="grid">
    <div class="card">
      <h2>Snapshot</h2>
      {'<img src="'+snapshot_b64+'" alt="snapshot" />' if snapshot_b64 else '<p>Snapshot no disponible</p>'}
    </div>
    <div class="card">
      <h2>Energía vs tiempo</h2>
      {'<img src="'+energy_b64+'" alt="energia" />' if energy_b64 else '<p>Sin serie disponible</p>'}
    </div>
    <div class="card">
      <h2>Espectro radial</h2>
      {'<img src="'+spectrum_b64+'" alt="espectro" />' if spectrum_b64 else '<p>Espectro no disponible</p>'}
    </div>
    <div class="card">
      <h2>Autocorrelación 2D</h2>
      {'<img src="'+autocorr_b64+'" alt="autocorr" />' if autocorr_b64 else '<p>Autocorr no disponible</p>'}
    </div>
  </div>
</body>
</html>
"""
    return html
