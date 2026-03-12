import argparse
import urllib.error
import urllib.request
from pathlib import Path


def _get(base: str, path: str, binary: bool = False, timeout: int = 15):
    url = f"{base.rstrip('/')}/{path.lstrip('/')}"
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return r.read() if binary else r.read().decode()


def build_report(base: str, run_id: int, crop: int) -> str:
    return _get(base, f"/reports/run/{run_id}/html?crop={int(crop)}", binary=False, timeout=25)


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
