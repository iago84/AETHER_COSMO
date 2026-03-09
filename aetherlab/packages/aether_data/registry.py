from typing import Callable, Dict

import numpy as np

REGISTRY: Dict[str, Dict] = {}


def register(name: str, loader: Callable[..., dict], description: str | None = None) -> None:
    REGISTRY[name] = {"loader": loader, "description": description or ""}


def get(name: str) -> Dict:
    return REGISTRY[name]


def list_datasets() -> list[str]:
    return sorted(REGISTRY.keys())


def _summarize_array(arr: np.ndarray) -> dict:
    arr = np.asarray(arr)
    return {
        "shape": list(arr.shape),
        "dtype": str(arr.dtype),
        "min": float(np.min(arr)),
        "max": float(np.max(arr)),
        "mean": float(np.mean(arr)),
        "std": float(np.std(arr)),
    }


def _planck_loader(path: str) -> dict:
    if path.endswith(".npy"):
        data = np.load(path)
        return {"kind": "map", "summary": _summarize_array(data)}
    if path.endswith(".npz"):
        z = np.load(path)
        key = "map" if "map" in z.files else z.files[0]
        data = z[key]
        return {"kind": "map", "summary": _summarize_array(data)}
    try:
        import h5py

        with h5py.File(path, "r") as f:
            key = "map" if "map" in f.keys() else list(f.keys())[0]
            data = f[key][()]
            return {"kind": "map", "summary": _summarize_array(data)}
    except Exception as e:
        raise RuntimeError(f"Planck loader error: {e}")


def _gwosc_loader(path: str) -> dict:
    if path.endswith(".npy"):
        data = np.load(path)
        return {"kind": "strain", "summary": _summarize_array(data)}
    if path.endswith(".npz"):
        z = np.load(path)
        key = "strain" if "strain" in z.files else z.files[0]
        data = z[key]
        return {"kind": "strain", "summary": _summarize_array(data)}
    try:
        import h5py

        with h5py.File(path, "r") as f:
            # Common keys: 'strain' or first dataset found
            key = "strain" if "strain" in f.keys() else list(f.keys())[0]
            data = f[key][()]
            return {"kind": "strain", "summary": _summarize_array(data)}
    except Exception as e:
        raise RuntimeError(f"GWOSC loader error: {e}")


def _sdss_loader(path: str) -> dict:
    try:
        import pandas as pd

        df = pd.read_csv(path)
        cols = list(df.columns)
        head = df.head(5).to_dict(orient="records")
        return {"kind": "table", "columns": cols, "rows_preview": head, "rows": int(df.shape[0])}
    except Exception as e:
        raise RuntimeError(f"SDSS loader error: {e}")


register("planck", _planck_loader, "Planck / CMB maps")
register("gwosc", _gwosc_loader, "GWOSC / LIGO-Virgo-KAGRA")
register("sdss", _sdss_loader, "Sloan Digital Sky Survey")
