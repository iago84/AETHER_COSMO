import numpy as np

def corrcoef2d(a: np.ndarray, b: np.ndarray) -> float:
    a0 = a - a.mean()
    b0 = b - b.mean()
    sa = a0.std()
    sb = b0.std()
    if sa == 0.0 or sb == 0.0:
        return 0.0
    return float((a0 * b0).mean() / (sa * sb))

def compute_metrics(u: np.ndarray) -> dict:
    energy = float(np.mean(u ** 2))
    mean = float(np.mean(u))
    var = float(np.var(u))
    cx = corrcoef2d(u, np.roll(u, 1, axis=1))
    cy = corrcoef2d(u, np.roll(u, 1, axis=0))
    spatial_corr = float((cx + cy) / 2.0)
    return {
        "energy": energy,
        "mean": mean,
        "variance": var,
        "spatial_corr": spatial_corr,
    }

def autocorr2d(u: np.ndarray, normalize: bool = True) -> np.ndarray:
    u0 = u - np.mean(u)
    F = np.fft.fft2(u0)
    ac = np.fft.ifft2(np.abs(F) ** 2).real
    ac = np.fft.fftshift(ac)
    if normalize:
        denom = (u.size * np.var(u)) if np.var(u) > 0 else u.size
        ac = ac / denom
    return ac.astype(np.float32)

def radial_profile(data: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    ny, nx = data.shape
    y = np.arange(ny) - ny // 2
    x = np.arange(nx) - nx // 2
    X, Y = np.meshgrid(x, y)
    r = np.sqrt(X**2 + Y**2)
    r_int = r.astype(np.int32)
    r_max = r_int.max()
    sums = np.bincount(r_int.ravel(), weights=data.ravel(), minlength=r_max + 1)
    counts = np.bincount(r_int.ravel(), minlength=r_max + 1)
    valid = counts > 0
    k = np.arange(r_max + 1)[valid].astype(np.float32)
    prof = (sums[valid] / counts[valid]).astype(np.float32)
    return k, prof

def power_spectrum_radial(u: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    F = np.fft.fft2(u)
    ps = np.fft.fftshift(np.abs(F) ** 2)
    return radial_profile(ps)
