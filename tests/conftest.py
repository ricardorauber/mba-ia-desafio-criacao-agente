import pytest


@pytest.fixture(autouse=True)
def data_dir(tmp_path, monkeypatch):
    """Every test gets its own runtime data directory."""
    monkeypatch.setenv("AURORA_DATA_DIR", str(tmp_path / "var"))
    return tmp_path / "var"
