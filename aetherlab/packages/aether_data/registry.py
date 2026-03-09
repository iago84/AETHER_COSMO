from typing import Callable, Dict

REGISTRY: Dict[str, Dict] = {}


def register(name: str, loader: Callable[..., object], description: str | None = None) -> None:
    REGISTRY[name] = {"loader": loader, "description": description or ""}


def get(name: str) -> Dict:
    return REGISTRY[name]


def list_datasets() -> list[str]:
    return sorted(REGISTRY.keys())


# Built-in stubs (documented, implement later)
def _planck_loader(*args, **kwargs):
    raise NotImplementedError("Planck/CMB adapter pendiente de implementación")


def _gwosc_loader(*args, **kwargs):
    raise NotImplementedError("GWOSC/LIGO adapter pendiente de implementación")


def _sdss_loader(*args, **kwargs):
    raise NotImplementedError("SDSS adapter pendiente de implementación")


register("planck", _planck_loader, "Planck / CMB maps")
register("gwosc", _gwosc_loader, "GWOSC / LIGO-Virgo-KAGRA")
register("sdss", _sdss_loader, "Sloan Digital Sky Survey")
