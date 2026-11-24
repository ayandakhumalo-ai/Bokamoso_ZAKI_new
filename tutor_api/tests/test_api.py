import time

import jwt

from app.config import settings
from tests.conftest import ADMIN


# ---- auth ----
def test_register_requires_admin_key(client):
    r = client.post("/auth/register", json={"username": "sipho", "password": "password123"})
    assert r.status_code == 403


def test_register_and_login(client):
    assert client.post("/auth/register", headers=ADMIN,
                       json={"username": "sipho", "password": "password123"}).status_code == 201
    r = client.post("/auth/login", json={"username": "sipho", "password": "password123"})
    assert r.status_code == 200 and r.json()["token_type"] == "bearer"


def test_duplicate_username_rejected(client):
    body = {"username": "sipho", "password": "password123"}
    client.post("/auth/register", headers=ADMIN, json=body)
    assert client.post("/auth/register", headers=ADMIN, json=body).status_code == 409


def test_wrong_password_and_unknown_user_look_the_same(client):
    client.post("/auth/register", headers=ADMIN, json={"username": "sipho", "password": "password123"})
    a = client.post("/auth/login", json={"username": "sipho", "password": "wrongpass1"})
    b = client.post("/auth/login", json={"username": "nobody", "password": "wrongpass1"})
    assert a.status_code == b.status_code == 401
    assert a.json() == b.json()


def test_short_password_rejected(client):
    r = client.post("/auth/register", headers=ADMIN, json={"username": "sipho", "password": "short"})
    assert r.status_code == 422


# ---- chat ----
def test_chat_requires_login(client):
    assert client.post("/chat", json={"message": "hi"}).status_code == 401


def test_chat_rejects_garbage_and_expired_tokens(client, auth):
    assert client.post("/chat", json={"message": "hi"},
                       headers={"Authorization": "Bearer nonsense"}).status_code == 401
    expired = jwt.encode({"sub": "1", "exp": int(time.time()) - 10}, settings.secret_key, algorithm="HS256")
    assert client.post("/chat", json={"message": "hi"},
                       headers={"Authorization": f"Bearer {expired}"}).status_code == 401


def test_chat_returns_reply(client, auth):
    r = client.post("/chat", json={"message": "What is 2+2?"}, headers=auth)
    assert r.status_code == 200
    assert r.json()["reply"] == "Sure. You asked: What is 2+2?"


def test_chat_streams(client, auth):
    with client.stream("POST", "/chat", json={"message": "hello", "stream": True}, headers=auth) as r:
        chunks = list(r.iter_text())
    assert "".join(chunks) == "Sure. You asked: hello"


def test_empty_message_rejected(client, auth):
    assert client.post("/chat", json={"message": ""}, headers=auth).status_code == 422


# ---- history ----
def test_history_is_saved_in_order(client, auth):
    client.post("/chat", json={"message": "first"}, headers=auth)
    client.post("/chat", json={"message": "second"}, headers=auth)
    msgs = client.get("/history", headers=auth).json()["messages"]
    assert [m["role"] for m in msgs] == ["user", "assistant", "user", "assistant"]
    assert msgs[0]["content"] == "first" and msgs[2]["content"] == "second"


def test_students_cannot_see_each_others_history(client, auth):
    client.post("/chat", json={"message": "private question"}, headers=auth)
    client.post("/auth/register", headers=ADMIN, json={"username": "other", "password": "password123"})
    tok = client.post("/auth/login", json={"username": "other", "password": "password123"}).json()["access_token"]
    other = client.get("/history", headers={"Authorization": f"Bearer {tok}"}).json()["messages"]
    assert other == []


def test_model_receives_system_prompt_and_prior_turns(client, auth):
    from app.main import app, get_llm
    seen = {}

    async def spy(messages):
        seen["messages"] = messages
        yield "ok"

    client.post("/chat", json={"message": "first"}, headers=auth)
    app.dependency_overrides[get_llm] = lambda: spy
    client.post("/chat", json={"message": "second"}, headers=auth)
    roles = [m["role"] for m in seen["messages"]]
    assert roles == ["system", "user", "assistant", "user"]


# ---- limits & failures ----
def test_rate_limit(client, auth, monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_per_min", 3)
    codes = [client.post("/chat", json={"message": "hi"}, headers=auth).status_code for _ in range(5)]
    assert codes == [200, 200, 200, 429, 429]


def test_ollama_down_returns_503(client, auth):
    import httpx
    from app.main import app, get_llm

    async def broken(messages):
        raise httpx.ConnectError("ollama is not running")
        yield  # pragma: no cover

    app.dependency_overrides[get_llm] = lambda: broken
    r = client.post("/chat", json={"message": "hi"}, headers=auth)
    assert r.status_code == 503


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200 and r.json()["api"] == "ok"
