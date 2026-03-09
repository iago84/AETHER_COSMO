from aetherlab.packages.aether_data.registry import get, list_datasets, register


def test_registry_register_and_list():
    register("dummy", lambda: {"ok": 1}, "Dummy dataset")
    names = list_datasets()
    assert "dummy" in names and "planck" in names and "gwosc" in names and "sdss" in names
    entry = get("dummy")
    assert "loader" in entry and callable(entry["loader"])
