"""Quiz results for parents: a bar per quiz, and where the child keeps getting questions wrong.

The device sends each finished quiz with all of its questions (POST /activity/quiz). Parents read:
  * the quizzes in a time range (last week by default, or month, year, or everything since the first quiz),
  * one quiz with every question,
  * the topics where the child is weak, with the questions they got wrong.
Quiz questions are schoolwork, not chat, so they are not hidden by TUTOR_PARENT_SEES_CHATS.
"""
import re
from datetime import date, timedelta

from . import catalog, db, progress

RANGES = {"week": 7, "month": 30, "year": 365, "all": None}
DEFAULT_RANGE = "week"

MIN_QUESTIONS = 4          # questions on a topic before it can be called weak or strong
WEAK_BELOW = 60.0          # accuracy percent under this = weak spot
STRONG_AT = 80.0           # accuracy percent at/above this = strong
MAX_MISTAKES = 3           # wrong questions shown per weak topic

# (lowest percent, letter). Matches the grades the portal already shows (88 = A, 76 = B+, 95 = A+).
GRADES = [(95, "A+"), (85, "A"), (75, "B+"), (65, "B"), (50, "C"), (40, "D"), (0, "F")]


def letter(percent: float) -> str:
    return next(g for low, g in GRADES if percent >= low)


def resolve_range(name: str, student_id: int) -> tuple[date, date]:
    """(start, end) local dates, end exclusive. 'all' starts at the child's first quiz."""
    today = progress.local_today()
    end = today + timedelta(days=1)
    if name == "all":
        first = db.first_quiz_date(student_id)
        return (date.fromisoformat(first) if first else today), end
    return today - timedelta(days=RANGES[name] - 1), end


def _score(correct: int, total: int) -> float:
    return round(100 * correct / total, 1) if total else 0.0


def _quiz_row(q: dict) -> dict:
    percent = _score(q["correct"], q["total"])
    return {
        "id": q["id"], "title": q["title"], "subject": q["subject"],
        "topic": q["topic"], "topic_name": catalog.label(q["topic"]),
        "date": q["local_date"], "taken_at": progress.to_iso_utc(q["created_at"]),
        "correct": q["correct"], "total": q["total"],
        "score_percent": percent, "grade": letter(percent),
        "duration_seconds": q["duration_sec"],
    }


def quiz_report(child: dict, range_name: str) -> dict:
    """Everything the Grades bar chart needs for one child and one range."""
    start, end = resolve_range(range_name, child["id"])
    rows = db.quizzes_between(child["id"], start, end)
    quizzes = [_quiz_row(q) for q in rows]

    by_subject: dict[str, list[dict]] = {}
    for q in rows:
        by_subject.setdefault(q["subject"], []).append(q)
    subjects = []
    for name, items in by_subject.items():
        correct, total = sum(i["correct"] for i in items), sum(i["total"] for i in items)
        percents = [_score(i["correct"], i["total"]) for i in items]
        subjects.append({"subject": name, "quizzes": len(items), "average_percent": _score(correct, total),
                         "best_percent": max(percents), "lowest_percent": min(percents)})
    subjects.sort(key=lambda s: s["subject"])

    correct, total = sum(q["correct"] for q in rows), sum(q["total"] for q in rows)
    return {
        "child": child["username"],
        "range": range_name,
        "start": start.isoformat(),
        "end": (end - timedelta(days=1)).isoformat(),
        "first_quiz_date": db.first_quiz_date(child["id"]),
        "quiz_count": len(quizzes),
        "average_percent": _score(correct, total) if total else None,
        "quizzes": quizzes,
        "subjects": subjects,
    }


def quiz_detail(child_id: int, quiz_id: int) -> dict | None:
    quiz = db.get_quiz(child_id, quiz_id)
    if quiz is None:
        return None
    row = _quiz_row(quiz)
    row["questions"] = [{
        "number": q["position"], "topic": q["topic"], "topic_name": catalog.label(q["topic"]),
        "question": q["question"], "correct_answer": q["correct_answer"],
        "student_answer": q["student_answer"], "is_correct": bool(q["is_correct"]),
    } for q in quiz["questions"]]
    return row


def weaknesses(child: dict, range_name: str) -> dict:
    """Topics grouped from every stored question: weak (under 60%), strong (80%+), the rest developing."""
    start, end = resolve_range(range_name, child["id"])
    questions = db.quiz_questions_between(child["id"], start, end)

    groups: dict[tuple[str, str], list[dict]] = {}
    for q in questions:
        groups.setdefault((q["subject"], q["topic"]), []).append(q)

    topics = []
    for (subject, topic), items in groups.items():
        right = sum(i["is_correct"] for i in items)
        percent = _score(right, len(items))
        enough = len(items) >= MIN_QUESTIONS
        status = ("not_enough_data" if not enough else
                  "weak" if percent < WEAK_BELOW else
                  "strong" if percent >= STRONG_AT else "developing")
        wrong = [i for i in items if not i["is_correct"]]            # already newest first
        topics.append({
            "subject": subject, "topic": topic, "topic_name": catalog.label(topic),
            "questions": len(items), "correct": right, "accuracy_percent": percent, "status": status,
            "quizzes": len({i["quiz_id"] for i in items}),
            "recent_mistakes": [{
                "question": w["question"], "correct_answer": w["correct_answer"],
                "student_answer": w["student_answer"], "quiz_id": w["quiz_id"],
                "quiz_title": w["quiz_title"], "date": w["local_date"],
            } for w in wrong[:MAX_MISTAKES]] if status == "weak" else [],
        })
    order = {"weak": 0, "developing": 1, "strong": 2, "not_enough_data": 3}
    topics.sort(key=lambda t: (order[t["status"]], t["accuracy_percent"], -t["questions"], t["topic"]))

    return {
        "child": child["username"], "range": range_name,
        "start": start.isoformat(), "end": (end - timedelta(days=1)).isoformat(),
        "questions_answered": len(questions),
        "has_enough_data": any(t["status"] != "not_enough_data" for t in topics),
        "weak_topics": [t for t in topics if t["status"] == "weak"],
        "strong_topics": [t for t in topics if t["status"] == "strong"],
        "topics": topics,
    }


def insight_summary(child_id: int, days: int) -> dict | None:
    """A small, text-free summary for the AI insights: no question wording, just topics and percentages."""
    today = progress.local_today()
    start, end = today - timedelta(days=days - 1), today + timedelta(days=1)
    rows = db.quizzes_between(child_id, start, end)
    if not rows:
        return None
    weak = weaknesses_between(child_id, start, end)
    by_subject: dict[str, list[int]] = {}
    for q in rows:
        agg = by_subject.setdefault(q["subject"], [0, 0, 0])
        agg[0] += q["correct"]; agg[1] += q["total"]; agg[2] += 1            # noqa: E702
    return {
        "period_days": days,
        "quizzes_taken": len(rows),
        "average_by_subject": [{"subject": s, "average_percent": _score(c, t), "quizzes": n}
                               for s, (c, t, n) in sorted(by_subject.items())],
        "weak_topics": [{"subject": w["subject"], "topic": w["topic_name"],
                         "accuracy_percent": w["accuracy_percent"], "questions": w["questions"]}
                        for w in weak[:5]],
    }


def weaknesses_between(child_id: int, start: date, end: date) -> list[dict]:
    questions = db.quiz_questions_between(child_id, start, end)
    groups: dict[tuple[str, str], list[dict]] = {}
    for q in questions:
        groups.setdefault((q["subject"], q["topic"]), []).append(q)
    out = []
    for (subject, topic), items in groups.items():
        percent = _score(sum(i["is_correct"] for i in items), len(items))
        if len(items) >= MIN_QUESTIONS and percent < WEAK_BELOW:
            out.append({"subject": subject, "topic": topic, "topic_name": catalog.label(topic),
                        "questions": len(items), "accuracy_percent": percent})
    return sorted(out, key=lambda w: (w["accuracy_percent"], -w["questions"]))


# ---------- marking ----------
_SPACE = re.compile(r"\s+")


def same_answer(student: str | None, correct: str) -> bool:
    """Forgiving text comparison for when the device does not say whether an answer was right."""
    if student is None:
        return False
    norm = lambda s: _SPACE.sub(" ", s.strip().lower()).rstrip(".")      # noqa: E731
    return norm(student) == norm(correct)


# ---------- for the parent assistant (read on demand) ----------
MAX_DAYS = 365
MAX_RECENT = 15            # quizzes listed in an answer
MAX_WRONG = 12             # wrong questions listed in an answer


def _span(days: int) -> tuple[date, date, date]:
    """(previous_start, start, end) for the last `days` local days; end is exclusive."""
    today = progress.local_today()
    start = today - timedelta(days=days - 1)
    return start - timedelta(days=days), start, today + timedelta(days=1)


def _avg(rows: list[dict]) -> float | None:
    total = sum(r["total"] for r in rows)
    return _score(sum(r["correct"] for r in rows), total) if total else None


def assistant_summary(child_id: int, days: int, subject: str | None = None) -> dict:
    """Quiz scores for the parent assistant: per subject averages and the change since the previous period of the
    same length, the latest quizzes, and weak and strong topics. No question wording."""
    days = max(1, min(int(days), MAX_DAYS))
    prev_start, start, end = _span(days)
    wanted = (subject or "").strip().lower()
    keep = lambda r: not wanted or r["subject"].lower() == wanted                          # noqa: E731
    rows = [r for r in db.quizzes_between(child_id, start, end) if keep(r)]
    before = [r for r in db.quizzes_between(child_id, prev_start, start) if keep(r)]

    subjects = []
    for name in sorted({r["subject"] for r in rows}):
        now = _avg([r for r in rows if r["subject"] == name])
        then = _avg([r for r in before if r["subject"] == name])
        subjects.append({"subject": name, "quizzes": sum(1 for r in rows if r["subject"] == name),
                         "average_percent": now, "previous_period_average_percent": then,
                         "change_points": round(now - then, 1) if then is not None else None})

    weak = [w for w in weaknesses_between(child_id, start, end) if not wanted or w["subject"].lower() == wanted]
    groups: dict[tuple[str, str], list[dict]] = {}
    for q in db.quiz_questions_between(child_id, start, end):
        groups.setdefault((q["subject"], q["topic"]), []).append(q)
    strong = []
    for (subj, topic), items in groups.items():
        percent = _score(sum(i["is_correct"] for i in items), len(items))
        if (keep({"subject": subj}) and len(items) >= MIN_QUESTIONS and percent >= STRONG_AT):
            strong.append({"subject": subj, "topic": catalog.label(topic), "accuracy_percent": percent, "questions": len(items)})
    strong.sort(key=lambda t: (-t["accuracy_percent"], -t["questions"]))

    return {
        "period_days": days, "subject_filter": wanted or None,
        "quizzes_taken": len(rows), "average_percent": _avg(rows),
        "by_subject": subjects,
        "latest_quizzes": [{"title": r["title"], "subject": r["subject"], "date": r["local_date"],
                            "score_percent": _score(r["correct"], r["total"]),
                            "grade": letter(_score(r["correct"], r["total"])),
                            "right": r["correct"], "out_of": r["total"]} for r in reversed(rows)][:MAX_RECENT],
        "weak_topics": [{"subject": w["subject"], "topic": w["topic_name"], "accuracy_percent": w["accuracy_percent"],
                         "questions": w["questions"]} for w in weak[:8]],
        "strong_topics": strong[:8],
        "note": (None if rows else "No quizzes were taken in this period."),
    }


def assistant_mistakes(child_id: int, days: int, topic: str | None = None, subject: str | None = None) -> dict:
    """The quiz questions the child got wrong, newest first, with the right answer and what they answered."""
    days = max(1, min(int(days), MAX_DAYS))
    _, start, end = _span(days)
    t, s = (topic or "").strip().lower(), (subject or "").strip().lower()
    wrong = []
    for q in db.quiz_questions_between(child_id, start, end):
        if q["is_correct"]:
            continue
        if s and q["subject"].lower() != s:
            continue
        if t and t != catalog.label(q["topic"]).lower() and catalog.slug(t) != q["topic"]:
            continue                                   # matches "Cell Biology", "cell_biology" or "cell biology"
        wrong.append(q)
    return {
        "period_days": days, "topic_filter": t or None, "subject_filter": s or None,
        "wrong_answers_found": len(wrong),
        "wrong_answers": [{"quiz": w["quiz_title"], "subject": w["subject"], "topic": catalog.label(w["topic"]),
                           "date": w["local_date"], "question": w["question"],
                           "correct_answer": w["correct_answer"], "child_answered": w["student_answer"] or "(skipped)"}
                          for w in wrong[:MAX_WRONG]],
        "note": (None if wrong else "No wrong answers match."),
    }
