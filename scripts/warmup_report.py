import argparse
import json
import os
import sys
import time
import subprocess
from pathlib import Path
import urllib.request
import urllib.error

from scripts.report_html import build_report


def _post_json(url: str, payload: dict, timeout: int = 15) -> dict:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def _get_json(url: str, timeout: int = 15) -> dict:
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.loads(r.read().decode())


def wait_for_health(base: str, timeout_s: int = 30, interval: float = 0.5) -> bool:
    start = time.time()
    while time.time() - start < timeout_s:
        try:
            d = _get_json(f"{base}/health", timeout=5)
            if d.get("status") == "ok":
                return True
        except Exception:
            pass
        time.sleep(interval)
    return False


def ensure_project_and_experiment(base: str, project_name: str, experiment_name: str) -> tuple[int, int]:
    try:
        p = _post_json(f"{base}/projects", {"name": project_name, "description": "Warmup"})
        pid = int(p["id"])
    except Exception:
        rows = _get_json(f"{base}/projects")
        pid = int(rows[0]["id"]) if rows else 1
    e = _post_json(f"{base}/experiments", {"project_id": pid, "name": experiment_name})
    return pid, int(e["id"])


def simulate_and_report(base: str, experiment_id: int, outfile: str, crop: int) -> str:
    payload = {
        "experiment_id": experiment_id,
        "steps": 60,
        "dt": 0.05,
        "lam": 0.5,
        "diff": 0.2,
        "noise": 0.0,
        "boundary": "absorbing",
        "source_kind": "gaussian_pulse",
        "cx": 64,
        "cy": 64,
        "sigma": 8.0,
        "duration": 20,
        "amplitude": 1.0,
        "save_series": True,
        "series_stride": 10,
    }
    r = _post_json(f"{base}/simulate/simple", payload)
    run_id = int(r["run_id"])
    try:
        _get_json(f"{base}/runs/{run_id}/refresh")
    except Exception:
        pass
    html = build_report(base, run_id, crop)
    Path(outfile).write_text(html, encoding="utf-8")
    return outfile


def launch_api(host: str, port: int) -> subprocess.Popen:
    cmd = [sys.executable, "-m", "uvicorn", "aetherlab.apps.api.main:app", "--host", host, "--port", str(port)]
    env = os.environ.copy()
    return subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)


def main():
    ap = argparse.ArgumentParser(description="Warmup: lanzar API, crear demo y exportar reporte HTML")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--no-launch", action="store_true", help="No lanzar API si ya está corriendo")
    ap.add_argument("--project", default="Demo")
    ap.add_argument("--experiment", default="Exp1")
    ap.add_argument("--outfile", default=None)
    ap.add_argument("--crop", type=int, default=96)
    ap.add_argument("--keep-server", action="store_true", help="Mantener el servidor al finalizar")
    args = ap.parse_args()

    base = f"http://{args.host}:{args.port}"
    proc = None
    try:
        if not args.no_launch:
            proc = launch_api(args.host, args.port)
            if not wait_for_health(base, timeout_s=40):
                raise SystemExit("API no respondió en /health. Aborta.")
        else:
            if not wait_for_health(base, timeout_s=3):
                raise SystemExit("API no disponible y --no-launch activo.")
        _, exp_id = ensure_project_and_experiment(base, args.project, args.experiment)
        out = args.outfile or f"report_warmup_{int(time.time())}.html"
        path = simulate_and_report(base, exp_id, out, args.crop)
        print(f"Reporte generado: {path}")
        print(f"Base API: {base}")
    finally:
        if proc and not args.keep_server:
            try:
                proc.terminate()
            except Exception:
                pass


if __name__ == "__main__":
    main()
