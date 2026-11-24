"""Quizzes: the device stores every question, parents read bars by range, quiz detail and weak topics."""
import json
import os
import tempfile

import pytest

from app import db, gemini_insights, quizzes
from tests.test_insights import ago, family            # noqa: F401  (family is a fixture)
from tests.test_parent import link, login, make_user


def q(question, right, answer, topic=None):
    return {"question": question, "correct_answer": right, "student_answer": answer, **({"topic": topic} if topic else {})}


def add(sid, days_ago, subject="Mathematics", topic="algebra", results=(True, True, True, False, False), title=None):
    """Store a quiz straight in the database. results = one True/False per question."""
    questions = [{"topic": topic, "question": f"{topic} question {i}", "correct_answer": "right",
                  "student_answer": "right" if ok else "wrong", "is_correct": ok} for i, ok in enumerate(results, 1)]
    return db.add_quiz(sid, subject, topic, title or f"{topic.title()} quiz", questions, created_at=ago(days_ago))


def get(client, parent, sid, path="", **params):
    return client.get(f"/parent/children/{sid}/quizzes{path}", headers=parent, params=params)


# ---------- the device saves a quiz ----------
def test_device_saves_a_quiz_and_the_server_marks_it(client, family):                 # noqa: F811
    sid, parent, student = family
    r = client.post("/activity/quiz", headers=student, json={
        "subject": "Mathematics", "topic": "Algebra", "duration_seconds": 240,
        "questions": [q("Solve 3x + 5 = 20", "x = 5", "X = 5 "),                       # forgiving comparison
                      q("Simplify 2(x + 4) - 3", "2x + 5", "2x + 1"),
                      q("What is 2 + 2?", "4", None),                                   # skipped
                      q("Expand (x+1)^2", "x^2+2x+1", "x^2+1", None) | {"is_correct": True}]})   # device says it was right
    assert r.status_code == 201, r.text
    assert (r.json()["correct"], r.json()["total"], r.json()["score_percent"]) == (2, 4, 50.0)

    detail = get(client, parent, sid, f"/{r.json()['quiz_id']}").json()
    assert detail["title"] == "Algebra quiz" and detail["topic"] == "algebra" and detail["grade"] == "C"
    assert [x["is_correct"] for x in detail["questions"]] == [True, False, False, True]
    assert detail["questions"][2]["student_answer"] is None
    assert detail["questions"][0]["topic_name"] == "Algebra"


def test_quiz_validation(client, family):                                              # noqa: F811
    _, _, student = family
    ok = [q("Q", "A", "A")]
    assert client.post("/activity/quiz", headers=student, json={"subject": "Maths", "topic": "Algebra", "questions": []}).status_code == 422
    assert client.post("/activity/quiz", headers=student, json={"subject": "Maths", "topic": "!!!", "questions": ok}).status_code == 422
    assert client.post("/activity/quiz", headers=student, json={"subject": "Maths", "topic": "Algebra", "questions": ok * 101}).status_code == 422
    assert client.post("/activity/quiz", headers=student, json={"subject": "Maths", "topic": "Algebra", "questions": [{"question": "Q"}]}).status_code == 422


def test_only_students_can_save_quizzes_and_login_is_needed(client, family):          # noqa: F811
    _, parent, _ = family
    body = {"subject": "Maths", "topic": "Algebra", "questions": [q("Q", "A", "A")]}
    assert client.post("/activity/quiz", headers=parent, json=body).status_code == 403
    assert client.post("/activity/quiz", json=body).status_code == 401


# ---------- bars by range ----------
@pytest.fixture
def spread(family):                                                                    # noqa: F811
    sid, parent, student = family
    add(sid, 1, "Mathematics", "algebra", (True, True, True, True, False), "Algebra quiz")           # 80%
    add(sid, 6, "Biology", "cell_division", (True, True, False, False, False), "Cell Division quiz")  # 40%
    add(sid, 7, "Physics", "forces", (True,) * 5)                                      # just outside the 7-day week
    add(sid, 20, "Mathematics", "geometry")
    add(sid, 100, "English", "grammar")
    add(sid, 300, "History", "industrial_revolution")
    add(sid, 400, "History", "industrial_revolution")                                  # older than a year
    return sid, parent, student


def test_default_range_is_the_last_week(client, spread):
    sid, parent, _ = spread
    body = get(client, parent, sid).json()
    assert body["range"] == "week"
    assert [x["title"] for x in body["quizzes"]] == ["Cell Division quiz", "Algebra quiz"]      # oldest first, day 6 and 1
    assert body["quiz_count"] == 2 and body["average_percent"] == 60.0
    first = body["quizzes"][0]
    assert (first["subject"], first["score_percent"], first["grade"], first["correct"], first["total"]) == ("Biology", 40.0, "D", 2, 5)
    assert {s["subject"]: s["average_percent"] for s in body["subjects"]} == {"Biology": 40.0, "Mathematics": 80.0}


@pytest.mark.parametrize("name,count", [("week", 2), ("month", 4), ("year", 6), ("all", 7)])
def test_zooming_out_adds_older_quizzes(client, spread, name, count):
    sid, parent, _ = spread
    body = get(client, parent, sid, range=name).json()
    assert body["quiz_count"] == count
    dates = [x["date"] for x in body["quizzes"]]
    assert dates == sorted(dates)


def test_range_dates_are_reported(client, spread):
    sid, parent, _ = spread
    week = get(client, parent, sid).json()
    month = get(client, parent, sid, range="month").json()
    assert week["end"] == month["end"] and week["start"] > month["start"]
    assert get(client, parent, sid, range="all").json()["start"] == get(client, parent, sid, range="all").json()["first_quiz_date"]


def test_a_child_with_no_quizzes_gets_an_empty_chart_not_an_error(client, family):             # noqa: F811
    sid, parent, _ = family
    body = get(client, parent, sid, range="all").json()
    assert body["quiz_count"] == 0 and body["quizzes"] == [] and body["average_percent"] is None


def test_bad_range_is_rejected(client, family):                                                # noqa: F811
    sid, parent, _ = family
    assert get(client, parent, sid, range="decade").status_code == 422


@pytest.mark.parametrize("percent,grade", [(100, "A+"), (95, "A+"), (94.9, "A"), (85, "A"), (75, "B+"), (65, "B"),
                                            (50, "C"), (40, "D"), (39.9, "F"), (0, "F")])
def test_letter_grades(percent, grade):
    assert quizzes.letter(percent) == grade


# ---------- one quiz ----------
def test_quiz_detail_lists_every_question(client, family):                                    # noqa: F811
    sid, parent, _ = family
    quiz_id = add(sid, 1)
    body = get(client, parent, sid, f"/{quiz_id}").json()
    assert body["total"] == 5 and len(body["questions"]) == 5
    assert [x["number"] for x in body["questions"]] == [1, 2, 3, 4, 5]
    assert body["questions"][3]["is_correct"] is False and body["questions"][3]["student_answer"] == "wrong"


def test_quiz_ids_are_private_to_the_family(client, family):                                  # noqa: F811
    sid, parent, _ = family
    quiz_id = add(sid, 1)
    other_child = make_user(client, "sipho")
    other_quiz = add(other_child, 1)
    make_user(client, "gogo", "parent")
    link(client, "gogo", "sipho")
    assert get(client, parent, sid, f"/{other_quiz}").status_code == 404            # another child's quiz id, via my child
    assert get(client, login(client, "gogo"), sid, f"/{quiz_id}").status_code == 404   # not my child
    assert get(client, login(client, "gogo"), sid).status_code == 404
    assert get(client, login(client, "gogo"), sid, "/weaknesses").status_code == 404
    assert get(client, parent, sid, "/999999").status_code == 404
    assert client.get(f"/parent/children/{sid}/quizzes").status_code == 401


def test_students_cannot_open_parent_quiz_endpoints(client, family):                          # noqa: F811
    sid, _, student = family
    assert get(client, student, sid).status_code == 403


# ---------- weak topics ----------
def test_weak_topics_come_from_the_stored_questions(client, family):                          # noqa: F811
    sid, parent, _ = family
    add(sid, 2, "Biology", "cell_biology", (False, False, True, False, False))      # 20%
    add(sid, 5, "Biology", "cell_biology", (False, True, False, False, True))       # 40%
    add(sid, 3, "Mathematics", "algebra", (True,) * 5)                              # strong
    add(sid, 4, "Physics", "forces", (True, False))                                 # only 2 questions
    body = get(client, parent, sid, "/weaknesses", range="month").json()

    assert [t["topic"] for t in body["weak_topics"]] == ["cell_biology"]
    weak = body["weak_topics"][0]
    assert (weak["questions"], weak["correct"], weak["accuracy_percent"], weak["quizzes"]) == (10, 3, 30.0, 2)
    assert len(weak["recent_mistakes"]) == 3                                         # capped
    assert weak["recent_mistakes"][0]["date"] >= weak["recent_mistakes"][-1]["date"]  # newest first
    assert {"question", "correct_answer", "student_answer", "quiz_title"} <= set(weak["recent_mistakes"][0])
    assert [t["topic"] for t in body["strong_topics"]] == ["algebra"]
    by_topic = {t["topic"]: t for t in body["topics"]}
    assert by_topic["forces"]["status"] == "not_enough_data" and by_topic["forces"]["recent_mistakes"] == []
    assert body["has_enough_data"] and body["questions_answered"] == 17


def test_weaknesses_respect_the_range(client, family):                                       # noqa: F811
    sid, parent, _ = family
    add(sid, 200, "Biology", "cell_biology", (False,) * 5)
    assert get(client, parent, sid, "/weaknesses", range="month").json()["weak_topics"] == []
    assert [t["topic"] for t in get(client, parent, sid, "/weaknesses", range="year").json()["weak_topics"]] == ["cell_biology"]


def test_weaknesses_with_no_quizzes(client, family):                                          # noqa: F811
    sid, parent, _ = family
    body = get(client, parent, sid, "/weaknesses").json()
    assert body["weak_topics"] == [] and body["has_enough_data"] is False


# ---------- the demo family ----------
@pytest.fixture
def demo(client):
    from scripts.seed_family import seed_family
    return seed_family()


def test_demo_family_has_a_year_of_quizzes(client, demo):
    token = client.post("/auth/login", json={"username": "Sarah", "password": "demo1234"}).json()["access_token"]
    parent = {"Authorization": f"Bearer {token}"}
    for child_id, name in ((demo["alex_id"], "Alex"), (demo["maya_id"], "Maya")):
        week = get(client, parent, child_id).json()
        year = get(client, parent, child_id, range="year").json()
        assert 3 <= week["quiz_count"] <= 6, name
        assert year["quiz_count"] > 60, name
        assert len({x["subject"] for x in year["quizzes"]}) >= 4, name
    alex_year = get(client, parent, demo["alex_id"], "/weaknesses", range="year").json()
    assert {"essay_writing", "cell_biology"} <= {t["topic"] for t in alex_year["weak_topics"]}
    maya_year = get(client, parent, demo["maya_id"], "/weaknesses", range="year").json()
    assert "fractions" in [t["topic"] for t in maya_year["weak_topics"]]


def test_demo_quiz_script_is_safe_to_rerun(client, demo, capsys):
    from scripts import demo_quizzes
    demo_quizzes.main()
    assert capsys.readouterr().out.count("already has quizzes") == 2


# ---------- Gemini gets topics and percentages only ----------
def test_ai_insights_see_quiz_topics_but_never_question_text(client, family):                # noqa: F811
    sid, _, _ = family
    add(sid, 2, "Biology", "cell_biology", (False, False, True, False, False))
    payload = gemini_insights.build_payload(db.get_user_by_id(sid), 14)
    assert payload["quizzes"]["quizzes_taken"] == 1
    assert payload["quizzes"]["weak_topics"][0] == {"subject": "Biology", "topic": "Cell Biology",
                                                    "accuracy_percent": 20.0, "questions": 5}
    assert "cell_biology question" not in json.dumps(payload)
    assert gemini_insights.has_something_to_say(payload)


def test_payload_has_no_quiz_section_without_quizzes(client, family):                        # noqa: F811
    sid, _, _ = family
    assert "quizzes" not in gemini_insights.build_payload(db.get_user_by_id(sid), 14)
