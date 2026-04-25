import pytest


@pytest.fixture
def temp_db_path(tmp_path, monkeypatch):
    db_path = tmp_path / "hub.db"
    monkeypatch.setenv("HUB_DB_PATH", str(db_path))
    monkeypatch.setenv("HUB_HOST", "127.0.0.1")
    monkeypatch.setenv("HUB_PORT", "8000")
    monkeypatch.setenv("HUB_LOG_LEVEL", "INFO")
    return db_path
