import argparse
import base64
import io
import json
import urllib.request
import urllib.error
from pathlib import Path
import numpy as np
from matplotlib.figure import Figure


def _get(base: str, path: str, binary: bool = False, timeout: int = 15):
    url = f"{base.rstrip('/')}/{path.lstrip('/')}"
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return r.read() if binary else r.read().decode()


def _png_from_spectrum(k, ps) -> bytes:
    fig = Figure(figsize=(5, 3), dpi=120)
    ax = fig.add_subplot(111)
    ax.plot(k, ps, label="Espectro radial")
    ax.set_xlabel("k"); ax.set_ylabel("potencia"); ax.grid(True); ax.legend()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight")
    return buf.getvalue()


def _png_from_autocorr(ac2d: np.ndarray) -> bytes:
    fig = Figure(figsize=(4, 4), dpi=120)
    ax = fig.add_subplot(111)
    im = ax.imshow(ac2d, cmap="viridis", origin="lower")
    fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight")
    return buf.getvalue()


def _png_from_energy(series_metrics: list[dict]) -> bytes:
    e = np.array([m.get("energy", np.nan) for m in series_metrics], dtype=np.float32)
    fig = Figure(figsize=(5, 3), dpi=120)
    ax = fig.add_subplot(111)
    ax.plot(np.arange(len(e)), e, label="Energía")
    ax.set_xlabel("frame"); ax.set_ylabel("energía"); ax.grid(True); ax.legend()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight")
    return buf.getvalue()


def _b64img(png_bytes: bytes) -> str:
    return "data:image/png;base64," + base64.b64encode(png_bytes).decode()


def build_report(base: str, run_id: int, crop: int) -> str:
    # Snapshot
    try:
        snapshot_bytes = _get(base, f"/figures/{run_id}/snapshot", binary=True)
        snapshot_b64 = _b64img(snapshot_bytes)
    except Exception:
        snapshot_b64 = ""
    # Spectrum
    try:
        spec_json = json.loads(_get(base, f"/figures/{run_id}/spectrum"))
        k = np.array(spec_json.get("k", []), dtype=np.float32)
        ps = np.array(spec_json.get("ps", []), dtype=np.float32)
    except Exception:
        k = np.array([], dtype=np.float32)
        ps = np.array([], dtype=np.float32)
    spectrum_b64 = _b64img(_png_from_spectrum(k, ps)) if k.size else ""
    # Autocorr
    try:
        ac_json = json.loads(_get(base, f"/figures/{run_id}/autocorr?crop={int(crop)}"))
        ac = np.array(ac_json.get("autocorr", []), dtype=np.float32)
    except Exception:
        ac = np.array([], dtype=np.float32)
    autocorr_b64 = _b64img(_png_from_autocorr(ac)) if ac.size else ""
    # Series metrics
    try:
        series = json.loads(_get(base, f"/figures/{run_id}/series-metrics"))
    except Exception:
        series = {"length": 0, "series": []}
    energy_b64 = ""
    if int(series.get("length", 0)) > 0 and isinstance(series.get("series"), list):
        energy_b64 = _b64img(_png_from_energy(series["series"]))
    # Compose HTML
    html = f"""
<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8" />
  <title>AETHERLAB Reporte Run {run_id}</title>
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
      <h2>Autocorrelación 2D (recorte)</h2>
      {'<img src="'+autocorr_b64+'" alt="autocorr" />' if autocorr_b64 else '<p>Autocorr no disponible</p>'}
    </div>
  </div>
</body>
</html>
"""
    return html


def main():
    ap = argparse.ArgumentParser(description="Generar reporte HTML para un run")
    ap.add_argument("--base", default="http://127.0.0.1:8000", help="Base URL del API")
    ap.add_argument("--run-id", type=int, required=True, help="ID del run")
    ap.add_argument("--crop", type=int, default=96, help="Recorte para autocorrelación 2D")
    ap.add_argument("--outfile", default=None, help="Ruta del HTML de salida")
    args = ap.parse_args()
    try:
        html = build_report(args.base, args.run_id, args.crop)
    except urllib.error.URLError as e:
        raise SystemExit(f"No se pudo conectar al API en {args.base}. ¿Está ejecutándose? Detalle: {e}")
    out = args.outfile or f"report_run_{args.run_id}.html"
    Path(out).write_text(html, encoding="utf-8")
    print(f"Reporte guardado en {out}")


if __name__ == "__main__":
    main()
