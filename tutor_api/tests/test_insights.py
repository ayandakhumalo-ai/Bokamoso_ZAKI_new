from datetime import timedelta

import pytest

from app import catalog, db, progress
from scripts.seed_demo import seed_demo
from tests.test_parent import link, local_ts, login, make_user


@pytest.fixture
def family(client):
    """A parent linked to one student. Returns (student_id, parent_headers, student_headers)."""
    make_user(client, "mama", "parent")
    sid = make_user(client, "thandi")
    link(client, "mama", "thandi")
    return sid, login(client, "mama"), login(client, "thandi")


def ago(days, hour=12):
    return local_ts(progress.local_today() - timedelta(days=days), hour)


def practice(sid, topic, total, correct, days_ago, subject="Maths"):
    db.add_event(sid, "practice", topic, subject=subject, total=total, correct=correct,
                 created_at=ago(days_ago))


def by_topic(rows):
    return {r["topic"]: r for r in rows}


# ---------- the device reports activity ----------
def test_device_logs_game_learn_and_practice(client, family):
    sid, parent, student = family
    assert client.post("/activity/game", headers=student,
                       json={"game": "Tic Tac Toe", "duration_seconds": 300, "result": "win"}).status_code == 201
    assert client.post("/activity/learn", headers=student, json={"topic": "Prime Numbers"}).status_code == 201
    r = client.post("/activity/practice", headers=student,
                    json={"topic": "Prime Numbers", "total_questions": 5, "correct_answers": 4})
    assert r.status_code == 201 and r.json()["topic"] == "prime_numbers"       # names are tidied up

    games = client.get(f"/parent/children/{sid}/games", headers=parent).json()
    assert games["games"][0]["game"] == "tic_tac_toe" and games["games"][0]["name"] == "Tic Tac Toe"
    topics = by_topic(client.get(f"/parent/children/{sid}/topics", headers=parent).json()["topics"])
    assert topics["prime_numbers"]["practice_questions"] == 5
    assert topics["prime_numbers"]["lessons_viewed"] == 1
    assert topics["prime_numbers"]["subject"] == "Maths"      # taken from the catalog


def test_activity_endpoints_validate_input(client, family):
    _, parent, student = family
    bad_total = {"topic": "Fractions", "total_questions": 5, "correct_answers": 9}
    assert client.post("/activity/practice", headers=student, json=bad_total).status_code == 422
    assert client.post("/activity/practice", headers=student,
                       json={"topic": "Fractions", "total_questions": 0, "correct_answers": 0}).status_code == 422
    assert client.post("/activity/game", headers=student, json={"game": "!!!"}).status_code == 422
    assert client.post("/activity/game", headers=student,
                       json={"game": "Chess", "result": "cheated"}).status_code == 422


def test_only_students_can_report_activity(client, family):
    _, parent, _ = family
    body = {"game": "Chess"}
    assert client.post("/activity/game", headers=parent, json=body).status_code == 403
    assert client.post("/activity/game", json=body).status_code == 401


def test_unknown_topics_and_explicit_subject_are_kept(client, family):
    sid, parent, student = family
    client.post("/activity/practice", headers=student, json={
        "topic": "Ear Training", "subject": "music", "total_questions": 6, "correct_answers": 3})
    topics = client.get(f"/parent/children/{sid}/topics", headers=parent).json()
    row = topics["topics"][0]
    assert (row["name"], row["subject"]) == ("Ear Training", "Music")
    assert topics["subjects"][0]["subject"] == "Music"


# ---------- games ----------
def test_games_report(client, family):
    sid, parent, _ = family
    for day, dur, res in ((1, 600, "win"), (2, 900, "loss"), (3, 300, "win")):
        db.add_event(sid, "game", "chess", duration_sec=dur, result=res, created_at=ago(day))
    db.add_event(sid, "game", "zaki_racing", duration_sec=300, result="completed", created_at=ago(1, 18))
    for day in (2, 4):
        db.add_event(sid, "game", "hangman", created_at=ago(day))
    for day in (45, 50):                                           # previous period (days=30)
        db.add_event(sid, "game", "chess", created_at=ago(day))

    g = client.get(f"/parent/children/{sid}/games?days=30", headers=parent).json()
    assert g["total_sessions"] == 6
    assert g["sessions_previous_period"] == 2
    assert g["days_played"] == 4
    assert g["sessions_per_week"] == 1.4
    assert g["total_minutes"] == 35.0
    assert g["favourite_game"] == "Chess"
    chess = g["games"][0]
    assert (chess["sessions"], chess["wins"], chess["losses"], chess["minutes"]) == (3, 2, 1, 30.0)
    assert chess["share_percent"] == 50.0
    assert [x["game"] for x in g["games"]] == ["chess", "hangman", "zaki_racing"]   # most played first
    assert chess["last_played"].endswith("Z")


def test_games_report_when_nothing_played(client, family):
    sid, parent, _ = family
    g = client.get(f"/parent/children/{sid}/games", headers=parent).json()
    assert g["total_sessions"] == 0 and g["favourite_game"] is None and g["games"] == []


# ---------- topics: who is struggling ----------
def test_topic_statuses(client, family):
    sid, parent, _ = family
    practice(sid, "fractions", 10, 2, 3)        # 20%  -> struggling
    practice(sid, "area", 10, 9, 3)             # 90%  -> strong
    practice(sid, "hcf", 10, 6, 3)              # 60%  -> developing
    practice(sid, "decimals", 3, 3, 3)          # only 3 questions -> not enough data
    for _ in range(4):                          # keeps asking about percentages, never practised
        db.add_message(sid, "user", "What is a percentage?", ago(2))

    body = client.get(f"/parent/children/{sid}/topics?days=28", headers=parent).json()
    rows = by_topic(body["topics"])
    assert rows["fractions"]["status"] == "struggling" and rows["fractions"]["accuracy_percent"] == 20.0
    assert rows["area"]["status"] == "strong"
    assert rows["hcf"]["status"] == "developing"
    assert rows["decimals"]["status"] == "not_enough_data"
    assert rows["percentages"]["status"] == "asking_often" and rows["percentages"]["questions_asked"] == 4
    assert body["needs_help"] == ["Fractions"]
    assert body["asking_often"] == ["Percentages"]
    assert body["doing_well"] == ["Area"]
    assert body["has_practice_data"] is True
    order = [r["status"] for r in body["topics"]]
    assert order == sorted(order, key=lambda s: ["struggling", "asking_often", "developing", "strong",
                                                  "not_enough_data"].index(s))


def test_old_results_outside_the_period_are_ignored(client, family):
    sid, parent, _ = family
    practice(sid, "fractions", 10, 1, 100)
    body = client.get(f"/parent/children/{sid}/topics?days=28", headers=parent).json()
    assert body["topics"] == [] and body["has_practice_data"] is False


def test_subjects_are_summarised(client, family):
    sid, parent, _ = family
    practice(sid, "fractions", 10, 5, 2)
    practice(sid, "area", 10, 9, 2)
    practice(sid, "ear_training", 10, 8, 2, subject="Music")
    subjects = {s["subject"]: s for s in client.get(
        f"/parent/children/{sid}/topics", headers=parent).json()["subjects"]}
    assert subjects["Maths"]["accuracy_percent"] == 70.0 and subjects["Maths"]["practice_questions"] == 20
    assert subjects["Music"]["accuracy_percent"] == 80.0


# ---------- trends: improved / dropped ----------
def test_trends_improved_declined_stable_and_engagement(client, family):
    sid, parent, _ = family
    NOW, BEFORE = 3, 35                           # days ago, inside the two 28-day windows
    practice(sid, "hcf", 10, 4, BEFORE);  practice(sid, "hcf", 10, 9, NOW)           # 40 -> 90
    practice(sid, "lcm", 10, 8, BEFORE);  practice(sid, "lcm", 10, 5, NOW)           # 80 -> 50
    practice(sid, "area", 10, 7, BEFORE); practice(sid, "area", 10, 7, NOW)          # 70 -> 70
    practice(sid, "percentages", 10, 7, BEFORE); practice(sid, "percentages", 3, 3, NOW)  # too few now
    practice(sid, "decimals", 10, 8, BEFORE)                                          # stopped
    practice(sid, "pythagoras", 10, 7, NOW)                                           # new
    for _ in range(4):
        practice(sid, "fractions", 10, 5, BEFORE)                                     # 40 -> 10 activity
    practice(sid, "fractions", 10, 5, NOW)
    practice(sid, "perimeter", 10, 5, BEFORE)
    for _ in range(3):
        practice(sid, "perimeter", 10, 5, NOW)                                        # 10 -> 30 activity

    body = client.get(f"/parent/children/{sid}/trends?days=28", headers=parent).json()
    t = by_topic(body["topics"])
    assert (t["hcf"]["performance"], t["hcf"]["change_points"]) == ("improved", 50.0)
    assert (t["lcm"]["performance"], t["lcm"]["change_points"]) == ("declined", -30.0)
    assert t["area"]["performance"] == "stable" and t["area"]["change_points"] == 0.0
    assert t["percentages"]["performance"] == "insufficient_data" and t["percentages"]["change_points"] is None
    assert t["decimals"]["engagement"] == "stopped"
    assert t["pythagoras"]["engagement"] == "new"
    assert t["fractions"]["engagement"] == "less"
    assert t["perimeter"]["engagement"] == "more"
    assert t["area"]["engagement"] == "same"
    assert body["improved"] == ["HCF"]
    assert body["declined"] == ["LCM"]
    assert body["less_active"][0] == "Fractions" and "Decimals" in body["less_active"]
    maths = body["subjects"][0]
    assert maths["subject"] == "Maths" and maths["practice_questions_now"] > 0


def test_a_small_change_is_not_called_improvement(client, family):
    sid, parent, _ = family
    practice(sid, "hcf", 10, 6, 35); practice(sid, "hcf", 10, 7, 3)        # +10 exactly -> improved
    practice(sid, "lcm", 10, 6, 35); practice(sid, "lcm", 10, 6, 3)
    practice(sid, "area", 20, 12, 35); practice(sid, "area", 20, 13, 3)    # +5 -> stable
    t = by_topic(client.get(f"/parent/children/{sid}/trends", headers=parent).json()["topics"])
    assert t["hcf"]["performance"] == "improved"
    assert t["lcm"]["performance"] == "stable"
    assert t["area"]["performance"] == "stable"


# ---------- the one-call report ----------
def test_report_explains_in_plain_language(client, family):
    sid, parent, student = family
    practice(sid, "fractions", 10, 3, 3)
    practice(sid, "hcf", 10, 4, 20); practice(sid, "hcf", 10, 9, 3)
    db.add_event(sid, "game", "chess", duration_sec=600, result="win", created_at=ago(1))
    client.post("/chat", headers=student, json={"message": "How do I add fractions?"})

    r = client.get(f"/parent/children/{sid}/report?days=14", headers=parent)
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"child", "period_days", "insights", "summary", "games", "topics", "trends",
                         "headline", "suggestions", "insights_source"}      # the last three were added for Gemini
    assert body["insights_source"] == "templates"                          # no Gemini key in the tests
    text = " ".join(body["insights"])
    assert "asked 1 question" in text
    assert "Favourite: Chess" in text
    assert "Needs help with: Fractions (30% correct over 10 questions)" in text
    assert "Improved: HCF (+50 points)" in text


def test_report_is_honest_when_there_is_no_practice_data(client, family):
    sid, parent, _ = family
    body = client.get(f"/parent/children/{sid}/report", headers=parent).json()
    text = " ".join(body["insights"])
    assert "No practice results have been recorded" in text
    assert "has not asked Zaki any questions" in text
    assert "No games were played" in text
    assert "Needs help" not in text


def test_summary_has_frequency_numbers(client, family):
    sid, parent, student = family
    for q in ("one", "two", "three"):
        client.post("/chat", headers=student, json={"message": q})
    s = client.get(f"/parent/children/{sid}/summary?days=7", headers=parent).json()
    assert s["avg_questions_per_week"] == 3.0
    assert s["questions_previous_period"] == 0


# ---------- safety: who may see what ----------
@pytest.mark.parametrize("path", ["games", "topics", "trends", "report"])
def test_new_endpoints_respect_family_boundaries(client, family, path):
    sid, parent, student = family
    make_user(client, "papa", "parent")
    other = login(client, "papa")
    assert client.get(f"/parent/children/{sid}/{path}", headers=other).status_code == 404
    assert client.get(f"/parent/children/{sid}/{path}", headers=student).status_code == 403
    assert client.get(f"/parent/children/{sid}/{path}").status_code == 401
    assert client.get(f"/parent/children/{sid}/{path}", headers=parent).status_code == 200


@pytest.mark.parametrize("path", ["games", "topics", "trends", "report"])
def test_days_parameter_limits(client, family, path):
    sid, parent, _ = family
    for bad in (0, 181):
        assert client.get(f"/parent/children/{sid}/{path}?days={bad}", headers=parent).status_code == 422


def test_hiding_content_still_hides_questions_in_report(client, family, monkeypatch):
    sid, parent, student = family
    client.post("/chat", headers=student, json={"message": "secret question"})
    monkeypatch.setattr(progress.settings, "parent_sees_chats", False)
    body = client.get(f"/parent/children/{sid}/report", headers=parent).json()
    assert "recent_questions" not in body["summary"]
    assert "secret question" not in str(body)


# ---------- question tagging ----------
@pytest.mark.parametrize("text,expected", [
    ("What is the HCF of 12 and 18?", "hcf"),
    ("explain the highest common factor", "hcf"),               # longer phrase beats 'factor'
    ("what are the factors of 24", "factors"),
    ("How do I add fractions?", "fractions"),
    ("what is 50% of 80", "percentages"),
    ("find the area of a circle", "area"),
    ("what is the mean of 2, 4 and 6", "mean"),
    ("what does this word mean?", None),                        # plain 'mean' is not maths
    ("help me arrange these words", None),                      # 'range' inside another word
    ("is 7 a prime number", "prime_numbers"),
    ("state Pythagoras theorem", "pythagoras"),
    ("why is the sky blue", None),
])
def test_tag_question(text, expected):
    assert catalog.tag_question(text) == expected


def test_slug_and_labels():
    assert catalog.slug("ZAKI Racing") == "zaki_racing"
    assert catalog.slug("  Parallel-Lines! ") == "parallel_lines"
    assert catalog.label("tic_tac_toe") == "Tic Tac Toe"
    assert catalog.label("some_new_game") == "Some New Game"
    assert catalog.subject_for("area") == "Maths" and catalog.subject_for("karate") == "General"


# ---------- demo data (also proves the whole pipeline on a realistic month) ----------
def test_demo_data_tells_the_planted_story(client):
    info = seed_demo()
    parent = login(client, info["parent"], info["password"])
    sid = info["student_id"]
    body = client.get(f"/parent/children/{sid}/report?days=28", headers=parent).json()

    assert "Fractions" in body["topics"]["needs_help"]
    assert set(body["trends"]["improved"]) == {"HCF", "Area"}
    assert set(body["trends"]["declined"]) == {"LCM", "Fractions"}
    assert "Decimals" in body["trends"]["less_active"]
    assert body["games"]["favourite_game"] == "Chess"
    assert body["games"]["games"][0]["sessions"] == 6
    assert body["summary"]["questions_in_period"] == 13
    assert body["summary"]["questions_previous_period"] == 6
    assert len(body["insights"]) >= 6
    assert by_topic(body["trends"]["topics"])["pythagoras"]["engagement"] == "new"


def test_demo_script_refuses_to_run_twice(client):
    seed_demo()
    with pytest.raises(SystemExit):
        seed_demo()


def test_old_database_gains_the_events_table(tmp_path, monkeypatch):
    import sqlite3
    path = str(tmp_path / "old.db")
    con = sqlite3.connect(path)
    con.executescript("""
        CREATE TABLE users (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL,
            password_hash BLOB NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE messages (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
            role TEXT NOT NULL, content TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
    """)
    con.commit()
    con.close()
    monkeypatch.setattr(progress.settings, "db_path", path)
    db.init_db()
    uid = db.create_user("kid", b"x")
    db.add_event(uid, "game", "chess", duration_sec=60)
    today = progress.local_today()
    assert db.game_days_and_sessions(uid, today, today + timedelta(days=1)) == (1, 1)
