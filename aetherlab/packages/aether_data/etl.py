import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd


def ensure_tree(root: Path) -> dict:
    raw = root / "aetherlab" / "data" / "raw"
    processed = root / "aetherlab" / "data" / "processed"
    features = root / "aetherlab" / "data" / "features"
    for d in (raw, processed, features):
        d.mkdir(parents=True, exist_ok=True)
    return {"raw": raw, "processed": processed, "features": features}


def _hash_path(p: Path) -> str:
    h = hashlib.sha256()
    h.update(p.as_posix().encode())
    try:
        h.update(str(p.stat().st_mtime_ns).encode())
    except Exception:
        pass
    return h.hexdigest()[:12]


def qc_report(arr: np.ndarray) -> dict:
    a = np.asarray(arr)
    finite = np.isfinite(a)
    finite_count = int(np.sum(finite))
    size = int(a.size)
    if finite_count == 0:
        return {
            "shape": list(a.shape),
            "dtype": str(a.dtype),
            "size": size,
            "finite_frac": 0.0,
            "nan_count": int(np.sum(np.isnan(a))),
            "inf_count": int(np.sum(np.isinf(a))),
        }
    af = a[finite].astype(np.float64)
    return {
        "shape": list(a.shape),
        "dtype": str(a.dtype),
        "size": size,
        "finite_frac": float(finite_count / max(1, size)),
        "nan_count": int(np.sum(np.isnan(a))),
        "inf_count": int(np.sum(np.isinf(a))),
        "min": float(np.min(af)),
        "max": float(np.max(af)),
        "mean": float(np.mean(af)),
        "std": float(np.std(af)),
        "p25": float(np.percentile(af, 25)),
        "p50": float(np.percentile(af, 50)),
        "p75": float(np.percentile(af, 75)),
    }


def normalize_array(arr: np.ndarray, method: str | None) -> np.ndarray:
    a = np.asarray(arr, dtype=np.float32)
    if method is None or method == "none":
        return a
    finite = np.isfinite(a)
    if not np.any(finite):
        return np.zeros_like(a, dtype=np.float32)
    af = a[finite].astype(np.float32)
    eps = np.float32(1e-8)
    if method == "zscore":
        mu = np.mean(af)
        sd = np.std(af)
        return (np.nan_to_num(a, nan=float(mu), posinf=float(mu), neginf=float(mu)) - mu) / (sd + eps)
    if method == "minmax":
        lo = np.min(af)
        hi = np.max(af)
        return (np.nan_to_num(a, nan=float(lo), posinf=float(hi), neginf=float(lo)) - lo) / (hi - lo + eps)
    if method == "robust":
        med = np.median(af)
        q25 = np.percentile(af, 25)
        q75 = np.percentile(af, 75)
        iqr = np.float32(q75 - q25)
        return (np.nan_to_num(a, nan=float(med), posinf=float(med), neginf=float(med)) - med) / (iqr + eps)
    raise ValueError(f"invalid normalize method: {method}")


def load_array(path: Path) -> np.ndarray:
    return _load_array(path)


def process_map_to_features(path: Path, root: Path, normalize: str | None = None, qc: bool = True) -> Path:
    tree = ensure_tree(root)
    arr0 = _load_array(path)
    arr = normalize_array(arr0, normalize)
    if arr.ndim != 2:
        raise ValueError("map must be 2D")
    row_mean = arr.mean(axis=1)
    col_mean = arr.mean(axis=0)
    row_std = arr.std(axis=1)
    col_std = arr.std(axis=0)
    stats = np.array(
        [
            float(np.mean(arr)),
            float(np.std(arr)),
            float(np.min(arr)),
            float(np.max(arr)),
            float(np.mean(np.abs(arr))),
        ],
        dtype=np.float32,
    )
    feats = np.concatenate(
        [
            stats,
            row_mean.astype(np.float32),
            col_mean.astype(np.float32),
            row_std.astype(np.float32),
            col_std.astype(np.float32),
        ]
    )
    out = tree["features"] / f"map_{_hash_path(path)}.npz"
    np.savez_compressed(out.as_posix(), features=feats.astype(np.float32))
    if qc:
        qc_path = out.with_suffix(".qc.json")
        qc_path.write_text(json.dumps(qc_report(arr0), ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def process_strain_to_features(path: Path, root: Path, normalize: str | None = None, qc: bool = True) -> Path:
    tree = ensure_tree(root)
    arr0 = _load_array(path).reshape(-1)
    arr = normalize_array(arr0, normalize).reshape(-1)
    n = max(1, len(arr) // 256)
    chunks = arr[: n * 256].reshape(n, 256)
    chunk_mean = chunks.mean(axis=1).astype(np.float32)
    chunk_std = chunks.std(axis=1).astype(np.float32)
    fft = np.abs(np.fft.rfft(arr[: n * 256].reshape(n, 256), axis=1)).astype(np.float32)
    fft_small = fft[:, :16].reshape(-1)
    feats = np.concatenate([chunk_mean, chunk_std, fft_small], axis=0).astype(np.float32)
    out = tree["features"] / f"strain_{_hash_path(path)}.npz"
    np.savez_compressed(out.as_posix(), features=feats)
    if qc:
        qc_path = out.with_suffix(".qc.json")
        qc_path.write_text(json.dumps(qc_report(arr0), ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def _load_array(path: Path) -> np.ndarray:
    if path.suffix == ".npy":
        return np.load(path.as_posix())
    if path.suffix == ".npz":
        z = np.load(path.as_posix())
        key = z.files[0]
        return z[key]
    if path.suffix == ".csv":
        df = pd.read_csv(path.as_posix())
        num = df.select_dtypes(include=["number"])
        return num.to_numpy()
    if path.suffix == ".parquet":
        df = pd.read_parquet(path.as_posix())
        num = df.select_dtypes(include=["number"])
        return num.to_numpy()
    try:
        import h5py

        with h5py.File(path.as_posix(), "r") as f:
            key = list(f.keys())[0]
            data = f[key][()]
            return np.asarray(data)
    except Exception as e:
        raise RuntimeError(str(e))
