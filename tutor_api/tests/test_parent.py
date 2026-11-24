import sqlite3
from datetime import timedelta

from app import db, progress
from app.config import settings
from tests.conftest import ADMIN


def make_user(client, username, role="student", password="password123"):
    r = client.post("/auth/register", headers=ADMIN,
                    json={"username": username, "password": password, "role": role})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def login(client, username, password="password123"):
    r = client.post("/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def link(client, parent, student):
    return client.post("/admin/links", headers=ADMIN,
                       json={"parent_username": parent, "student_username": student})


def local_ts(day, hour=12):
    """UTC timestamp string for `hour` o'clock *local* time on `day` (avoids midnight edge cases)."""
    utc = hour - settings.tz_offset_hours
    return f"{day.isoformat()} {utc:02d}:00:00"


# ---------- accounts and roles ----------
def test_login_and_me_report_the_role(client):
    make_user(client, "mama", "parent")
    r = client.post("/auth/login", json={"username": "mama", "password": "password123"})
    assert r.json()["role"] == "parent"
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    assert client.get("/me", headers=h).json()["role"] == "parent"


def test_default_role_is_student(client, auth):
    assert client.get("/me", headers=auth).json()["role"] == "student"


def test_invalid_role_rejected(client):
    r = client.post("/auth/register", headers=ADMIN,
                    json={"username": "x" * 5, "password": "password123", "role": "admin"})
    assert r.status_code == 422


def test_parent_cannot_use_student_endpoints(client):
    make_user(client, "mama", "parent")
    h = login(client, "mama")
    assert client.post("/chat", json={"message": "hi"}, headers=h).status_code == 403
    assert client.get("/history", headers=h).status_code == 403


def test_student_cannot_use_parent_endpoints(client, auth):
    assert client.get("/parent/children", headers=auth).status_code == 403
    me = client.get("/me", headers=auth).json()["id"]
    assert client.get(f"/parent/children/{me}/summary", headers=auth).status_code == 403


def test_parent_endpoints_need_login(client):
    assert client.get("/parent/children").status_code == 401


# ---------- linking ----------
def test_linking_requires_admin_key(client):
    make_user(client, "mama", "parent")
    make_user(client, "thandi")
    r = client.post("/admin/links", json={"parent_username": "mama", "student_username": "thandi"})
    assert r.status_code == 403


def test_linking_validates_names_and_roles(client):
    make_user(client, "mama", "parent")
    make_user(client, "thandi")
    make_user(client, "other_parent", "parent")
    assert link(client, "mama", "nobody").status_code == 404
    assert link(client, "thandi", "mama").status_code == 400          # swapped roles
    assert link(client, "mama", "other_parent").status_code == 400    # child must be a student
    assert link(client, "mama", "thandi").status_code == 201
    assert link(client, "mama", "thandi").status_code == 201          # repeating is harmless


def test_parent_sees_only_their_children(client):
    make_user(client, "mama", "parent")
    make_user(client, "thandi")
    make_user(client, "sipho")
    make_user(client, "stranger")
    link(client, "mama", "thandi")
    link(client, "mama", "sipho")
    kids = client.get("/parent/children", headers=login(client, "mama")).json()["children"]
    assert [k["username"] for k in kids] == ["sipho", "thandi"]


# ---------- privacy between families ----------
def test_parent_cannot_view_a_child_linked_to_someone_else(client):
    make_user(client, "mama", "parent")
    make_user(client, "papa", "parent")
    thandi = make_user(client, "thandi")
    link(client, "mama", "thandi")
    h = login(client, "papa")
    for path in ("summary", "activity", "conversations"):
        assert client.get(f"/parent/children/{thandi}/{path}", headers=h).status_code == 404


def test_nonexistent_child_looks_the_same_as_unlinked(client):
    make_user(client, "mama", "parent")
    h = login(client, "mama")
    assert client.get("/parent/children/9999/summary", headers=h).status_code == 404


# ---------- the numbers ----------
def test_summary_after_chatting(client):
    make_user(client, "mama", "parent")
    tid = make_user(client, "thandi")
    link(client, "mama", "thandi")
    s = login(client, "thandi")
    for q in ["What is 2+2?", "Explain fractions", "What is a noun?"]:
        client.post("/chat", json={"message": q}, headers=s)

    r = client.get(f"/parent/children/{tid}/summary", headers=login(client, "mama"))
    assert r.status_code == 200
    body = r.json()
    assert body["child"] == {"id": tid, "username": "thandi"}
    assert body["questions_total"] == 3          # answers are not counted, only questions
    assert body["questions_in_period"] == 3
    assert body["active_days_in_period"] == 1
    assert body["current_streak_days"] == 1
    assert body["last_active"].endswith("Z")
    assert [q["question"] for q in body["recent_questions"]] == [
        "What is a noun?", "Explain fractions", "What is 2+2?"]


def test_summary_for_a_child_who_has_not_started(client):
    make_user(client, "mama", "parent")
    tid = make_user(client, "thandi")
    link(client, "mama", "thandi")
    body = client.get(f"/parent/children/{tid}/summary", headers=login(client, "mama")).json()
    assert body["questions_total"] == 0
    assert body["current_streak_days"] == 0
    assert body["last_active"] is None and body["recent_questions"] == []


def test_activity_is_zero_filled_and_counts_per_day(client):
    make_user(client, "mama", "parent")
    tid = make_user(client, "thandi")
    link(client, "mama", "thandi")
    today = progress.local_today()
    db.add_message(tid, "user", "a", local_ts(today - timedelta(days=2)))
    db.add_message(tid, "user", "b", local_ts(today - timedelta(days=2), 15))
    db.add_message(tid, "assistant", "ignored", local_ts(today - timedelta(days=2)))
    db.add_message(tid, "user", "c", local_ts(today))

    r = client.get(f"/parent/children/{tid}/activity?days=5", headers=login(client, "mama"))
    days = r.json()["days"]
    assert len(days) == 5
    assert days[-1] == {"date": today.isoformat(), "questions": 1}
    assert days[-3]["questions"] == 2
    assert [d["questions"] for d in days] == [0, 0, 2, 0, 1]
    assert [d["date"] for d in days] == sorted(d["date"] for d in days)   # oldest first


def test_streak_over_several_days(client):
    make_user(client, "mama", "parent")
    tid = make_user(client, "thandi")
    link(client, "mama", "thandi")
    today = progress.local_today()
    for back in (0, 1, 2, 4):       # gap on day 3 ends the streak at 3
        db.add_message(tid, "user", "q", local_ts(today - timedelta(days=back)))
    body = client.get(f"/parent/children/{tid}/summary?days=7", headers=login(client, "mama")).json()
    assert body["current_streak_days"] == 3
    assert body["active_days_in_period"] == 4


def test_days_parameter_is_validated(client):
    make_user(client, "mama", "parent")
    tid = make_user(client, "thandi")
    link(client, "mama", "thandi")
    h = login(client, "mama")
    assert client.get(f"/parent/children/{tid}/summary?days=0", headers=h).status_code == 422
    assert client.get(f"/parent/children/{tid}/activity?days=500", headers=h).status_code == 422


def test_compute_streak_rules():
    d = progress.date(2026, 10, 26)
    ds = lambda *back: [(d - timedelta(days=b)).isoformat() for b in back]
    assert progress.compute_streak([], d) == 0
    assert progress.compute_streak(ds(0, 1, 2), d) == 3
    assert progress.compute_streak(ds(1, 2), d) == 2      # nothing yet today: streak still alive
    assert progress.compute_streak(ds(2, 3), d) == 0      # a full day missed: streak over
    assert progress.compute_streak(ds(0, 2), d) == 1


# ---------- conversation privacy switch ----------
def test_conversations_visible_to_linked_parent(client):
    make_user(client, "mama", "parent")
    tid = make_user(client, "thandi")
    link(client, "mama", "thandi")
    client.post("/chat", json={"message": "hello tutor"}, headers=login(client, "thandi"))
    r = client.get(f"/parent/children/{tid}/conversations", headers=login(client, "mama"))
    assert r.status_code == 200
    assert [m["role"] for m in r.json()["messages"]] == ["user", "assistant"]


def test_parent_sees_counts_only_when_content_sharing_is_off(client, monkeypatch):
    monkeypatch.setattr(settings, "parent_sees_chats", False)
    make_user(client, "mama", "parent")
    tid = make_user(client, "thandi")
    link(client, "mama", "thandi")
    client.post("/chat", json={"message": "private question"}, headers=login(client, "thandi"))
    h = login(client, "mama")
    assert client.get(f"/parent/children/{tid}/conversations", headers=h).status_code == 403
    body = client.get(f"/parent/children/{tid}/summary", headers=h).json()
    assert body["questions_total"] == 1
    assert "recent_questions" not in body
    assert "private question" not in client.get(f"/parent/children/{tid}/activity", headers=h).text


# ---------- upgrading an existing database ----------
def test_old_database_is_upgraded_and_keeps_its_students(tmp_path, monkeypatch):
    path = str(tmp_path / "old.db")
    con = sqlite3.connect(path)
    con.executescript("""
        CREATE TABLE users (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL,
            password_hash BLOB NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE messages (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
            role TEXT NOT NULL, content TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
        INSERT INTO users (username, password_hash) VALUES ('oldstudent', x'00');
        INSERT INTO messages (user_id, role, content) VALUES (1, 'user', 'earlier question');
    """)
    con.commit()
    con.close()

    monkeypatch.setattr(settings, "db_path", path)
    db.init_db()
    db.init_db()   # running it twice must be harmless
    user = db.get_user_by_name("oldstudent")
    assert user["role"] == "student"
    assert db.question_totals(user["id"])["total"] == 1
    pid = db.create_user("newparent", b"x", "parent")
    db.link_parent(pid, user["id"])
    assert db.is_linked(pid, user["id"])
