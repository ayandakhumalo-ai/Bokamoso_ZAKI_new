import pytest
from fastapi.testclient import TestClient

from app import security
from app.config import settings
from app.main import app, get_llm

ADMIN = {"X-Admin-Key": settings.admin_key}


async def fake_llm(messages):
    """Stands in for Ollama: streams a canned reply and echoes the last question."""
    last = messages[-1]["content"]
    for piece in ["Sure. ", "You asked: ", last]:
        yield piece


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "db_path", str(tmp_path / "test.db"))
    security.reset_rate_limits()
    app.dependency_overrides[get_llm] = lambda: fake_llm
    with TestClient(app) as c:  # runs lifespan -> creates tables in the temp DB
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def auth(client):
    """Registers a student and returns an Authorization header."""
    client.post("/auth/register", headers=ADMIN, json={"username": "thandi", "password": "password123"})
    token = client.post("/auth/login", json={"username": "thandi", "password": "password123"}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
