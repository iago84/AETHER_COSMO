import hashlib
from pathlib import Path

import numpy as np


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


def process_map_to_features(path: Path, root: Path) -> Path:
    tree = ensure_tree(root)
    arr = _load_array(path)
    feats = np.stack([arr.mean(axis=0), arr.mean(axis=1)], axis=0).astype(np.float32)
    out = tree["features"] / f"map_{_hash_path(path)}.npz"
    np.savez_compressed(out.as_posix(), features=feats)
    return out


def process_strain_to_features(path: Path, root: Path) -> Path:
    tree = ensure_tree(root)
    arr = _load_array(path).reshape(-1)
    n = max(1, len(arr) // 256)
    chunks = arr[: n * 256].reshape(n, 256)
    feats = chunks.mean(axis=1).astype(np.float32)
    out = tree["features"] / f"strain_{_hash_path(path)}.npz"
    np.savez_compressed(out.as_posix(), features=feats)
    return out


def _load_array(path: Path) -> np.ndarray:
    if path.suffix == ".npy":
        return np.load(path.as_posix())
    if path.suffix == ".npz":
        z = np.load(path.as_posix())
        key = z.files[0]
        return z[key]
    try:
        import h5py

        with h5py.File(path.as_posix(), "r") as f:
            key = list(f.keys())[0]
            data = f[key][()]
            return np.asarray(data)
    except Exception as e:
        raise RuntimeError(str(e))
