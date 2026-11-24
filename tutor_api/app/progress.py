"""Turns raw activity into the numbers a parent wants to see.

How "struggling", "improved" and "dropped" are decided (all from the child's own results):
  * Practice results are the evidence for how well a child understands a topic (accuracy).
  * A topic needs at least MIN_PRACTICE practice questions in the period before we judge it.
  * struggling  = accuracy below 50%       strong = accuracy 80% or more      otherwise developing
  * Trends compare the last N days with the N days before that. A change of 10 percentage
    points or more counts as improved / declined. Too little data in either period = "insufficient_data".
  * Chat questions are tagged to topics by keyword. They show what the child is curious or stuck
    about (asking about the same topic often is a warning sign) but never count as test results.
"""
from datetime import date, datetime, timedelta, timezone

from . import catalog, db
from .config import settings

MIN_PRACTICE = 5        # practice questions needed before judging a topic
STRUGGLE_BELOW = 0.50   # accuracy under this = struggling
STRONG_AT = 0.80        # accuracy at/above this = strong
CHANGE_POINTS = 10.0    # percentage-point change that counts as improved/declined
ASKS_OFTEN = 4          # chat questions on one topic that suggest the child finds it hard


def local_today() -> date:
    return (datetime.now(timezone.utc) + timedelta(hours=settings.tz_offset_hours)).date()


def to_iso_utc(ts: str | None) -> str | None:
    """SQLite 'YYYY-MM-DD HH:MM:SS' (UTC) -> '2026-10-26T15:01:00Z'."""
    return ts.replace(" ", "T") + "Z" if ts else None


def compute_streak(active: list[str], today: date) -> int:
    """Consecutive days of activity ending today.

    If the student hasn't studied yet today, yesterday still counts, so the streak
    only resets after a whole day is missed.
    """
    days = {date.fromisoformat(d) for d in active}
    day = today if today in days else today - timedelta(days=1)
    streak = 0
    while day in days:
        streak += 1
        day -= timedelta(days=1)
    return streak


def window(days: int) -> list[date]:
    """The last `days` local dates, oldest first, ending today."""
    today = local_today()
    return [today - timedelta(days=i) for i in range(days - 1, -1, -1)]


def periods(days: int) -> tuple[date, date, date]:
    """(previous_start, start, end): previous period is [previous_start, start), current is [start, end)."""
    today = local_today()
    start = today - timedelta(days=days - 1)
    return start - timedelta(days=days), start, today + timedelta(days=1)


def pct(correct: int, total: int) -> float | None:
    return round(100 * correct / total, 1) if total else None


def per_week(count: int, days: int) -> float:
    return round(count / (days / 7), 1)


# ---------- questions (chat) ----------
def activity(student_id: int, days: int) -> list[dict]:
    dates = window(days)
    counts = db.questions_per_day(student_id, dates[0])
    return [{"date": d.isoformat(), "questions": counts.get(d.isoformat(), 0)} for d in dates]


def summary(student: dict, days: int, include_content: bool) -> dict:
    per_day = activity(student["id"], days)
    totals = db.question_totals(student["id"])
    prev_start, start, _ = periods(days)
    in_period = sum(d["questions"] for d in per_day)
    result = {
        "child": {"id": student["id"], "username": student["username"]},
        "period_days": days,
        "questions_total": totals["total"],
        "questions_in_period": in_period,
        "questions_previous_period": db.count_questions(student["id"], prev_start, start),
        "avg_questions_per_week": per_week(in_period, days),
        "active_days_in_period": sum(1 for d in per_day if d["questions"] > 0),
        "current_streak_days": compute_streak(db.active_dates(student["id"]), local_today()),
        "first_active": to_iso_utc(totals["first"]),
        "last_active": to_iso_utc(totals["last"]),
    }
    if include_content:
        result["recent_questions"] = [
            {"question": q["content"], "asked_at": to_iso_utc(q["created_at"])}
            for q in db.recent_questions(student["id"], 5)
        ]
    return result


# ---------- games ----------
def games_report(student_id: int, days: int) -> dict:
    prev_start, start, end = periods(days)
    rows = db.game_stats(student_id, start, end)
    days_played, sessions = db.game_days_and_sessions(student_id, start, end)
    _, prev_sessions = db.game_days_and_sessions(student_id, prev_start, start)
    games = [{
        "game": r["name"],
        "name": catalog.label(r["name"]),
        "sessions": r["sessions"],
        "share_percent": round(100 * r["sessions"] / sessions, 1),
        "minutes": round(r["secs"] / 60, 1),
        "days_played": r["days"],
        "wins": r["wins"], "losses": r["losses"], "draws": r["draws"],
        "last_played": to_iso_utc(r["last"]),
    } for r in rows]
    return {
        "period_days": days,
        "total_sessions": sessions,
        "sessions_previous_period": prev_sessions,
        "sessions_per_week": per_week(sessions, days),
        "days_played": days_played,
        "total_minutes": round(sum(r["secs"] for r in rows) / 60, 1),
        "favourite_game": games[0]["name"] if games else None,   # rows are ordered most-played first
        "games": games,
    }


# ---------- topics ----------
def _blank() -> dict:
    return {"practice_total": 0, "practice_correct": 0, "practice_sessions": 0,
            "learn_views": 0, "questions_asked": 0, "subject": None}


def collect(student_id: int, start: date, end: date) -> dict[str, dict]:
    """Everything the child did per topic between start (inclusive) and end (exclusive)."""
    data: dict[str, dict] = {}

    def slot(topic: str) -> dict:
        return data.setdefault(topic, _blank())

    for r in db.practice_by_topic(student_id, start, end):
        d = slot(r["topic"])
        d["practice_total"] += r["total"]
        d["practice_correct"] += r["correct"]
        d["practice_sessions"] += r["sessions"]
        d["subject"] = d["subject"] or r["subject"]
    for r in db.learn_by_topic(student_id, start, end):
        d = slot(r["topic"])
        d["learn_views"] += r["views"]
        d["subject"] = d["subject"] or r["subject"]
    for q in db.questions_between(student_id, start, end):
        topic = catalog.tag_question(q["content"])
        if topic:
            slot(topic)["questions_asked"] += 1
    for topic, d in data.items():
        d["subject"] = catalog.subject_for(topic, d["subject"])
        d["activity"] = d["practice_total"] + d["learn_views"] + d["questions_asked"]
    return data


def topic_status(d: dict) -> str:
    total = d["practice_total"]
    if total >= MIN_PRACTICE:
        accuracy = d["practice_correct"] / total
        if accuracy < STRUGGLE_BELOW:
            return "struggling"
        return "strong" if accuracy >= STRONG_AT else "developing"
    if d["questions_asked"] >= ASKS_OFTEN:
        return "asking_often"
    return "not_enough_data"


_STATUS_ORDER = {"struggling": 0, "asking_often": 1, "developing": 2, "strong": 3, "not_enough_data": 4}


def topics_report(student_id: int, days: int) -> dict:
    _, start, end = periods(days)
    data = collect(student_id, start, end)
    rows = []
    for topic, d in data.items():
        rows.append({
            "topic": topic,
            "name": catalog.label(topic),
            "subject": d["subject"],
            "status": topic_status(d),
            "accuracy_percent": pct(d["practice_correct"], d["practice_total"]),
            "practice_questions": d["practice_total"],
            "practice_sessions": d["practice_sessions"],
            "lessons_viewed": d["learn_views"],
            "questions_asked": d["questions_asked"],
        })
    rows.sort(key=lambda r: (_STATUS_ORDER[r["status"]],
                             r["accuracy_percent"] if r["accuracy_percent"] is not None else 101,
                             r["name"]))

    by_subject: dict[str, dict] = {}
    for d in data.values():
        s = by_subject.setdefault(d["subject"], {"practice_total": 0, "practice_correct": 0, "activity": 0})
        s["practice_total"] += d["practice_total"]
        s["practice_correct"] += d["practice_correct"]
        s["activity"] += d["activity"]
    subjects = [{
        "subject": name,
        "accuracy_percent": pct(s["practice_correct"], s["practice_total"]),
        "practice_questions": s["practice_total"],
        "activity": s["activity"],
    } for name, s in sorted(by_subject.items())]

    names = lambda status: [r["name"] for r in rows if r["status"] == status]  # noqa: E731
    return {
        "period_days": days,
        "has_practice_data": any(d["practice_total"] for d in data.values()),
        "min_practice_questions": MIN_PRACTICE,
        "needs_help": names("struggling"),
        "asking_often": names("asking_often"),
        "doing_well": names("strong"),
        "topics": rows,
        "subjects": subjects,
    }


# ---------- trends: this period vs the one before ----------
def _compare(now: dict, before: dict) -> dict:
    n_t, n_c = now["practice_total"], now["practice_correct"]
    b_t, b_c = before["practice_total"], before["practice_correct"]
    change = None
    performance = "insufficient_data"
    if n_t >= MIN_PRACTICE and b_t >= MIN_PRACTICE:
        change = round(pct(n_c, n_t) - pct(b_c, b_t), 1)
        performance = ("improved" if change >= CHANGE_POINTS
                       else "declined" if change <= -CHANGE_POINTS else "stable")
    a, b = now["activity"], before["activity"]
    if a == 0 and b == 0:
        engagement = "none"
    elif b == 0:
        engagement = "new"
    elif a == 0:
        engagement = "stopped"
    elif a >= b * 1.5 and a - b >= 2:
        engagement = "more"
    elif a <= b * 0.5 and b - a >= 2:
        engagement = "less"
    else:
        engagement = "same"
    return {
        "accuracy_now": pct(n_c, n_t),
        "accuracy_before": pct(b_c, b_t),
        "change_points": change,
        "performance": performance,
        "practice_questions_now": n_t,
        "practice_questions_before": b_t,
        "activity_now": a,
        "activity_before": b,
        "engagement": engagement,
    }


def _zero() -> dict:
    return {"practice_total": 0, "practice_correct": 0, "activity": 0}


def trends_report(student_id: int, days: int) -> dict:
    prev_start, start, end = periods(days)
    now = collect(student_id, start, end)
    before = collect(student_id, prev_start, start)

    topic_rows = []
    subj_now: dict[str, dict] = {}
    subj_before: dict[str, dict] = {}
    for topic in sorted(set(now) | set(before)):
        n, b = now.get(topic, _zero()), before.get(topic, _zero())
        subject = (now.get(topic) or before.get(topic))["subject"]
        topic_rows.append({"topic": topic, "name": catalog.label(topic), "subject": subject,
                           **_compare(n, b)})
        for bucket, src in ((subj_now, n), (subj_before, b)):
            agg = bucket.setdefault(subject, _zero())
            for key in agg:
                agg[key] += src[key]
    subject_rows = [{"subject": s, **_compare(subj_now.get(s, _zero()), subj_before.get(s, _zero()))}
                    for s in sorted(set(subj_now) | set(subj_before))]

    def names(key: str, value, order_key, reverse=False):
        picked = [r for r in topic_rows if r[key] == value]
        return [r["name"] for r in sorted(picked, key=order_key, reverse=reverse)]

    return {
        "period_days": days,
        "compared_with": "the previous %d days" % days,
        "improved": names("performance", "improved", lambda r: r["change_points"], reverse=True),
        "declined": names("performance", "declined", lambda r: r["change_points"]),
        "less_active": [r["name"] for r in sorted(
            (r for r in topic_rows if r["engagement"] in ("less", "stopped")),
            key=lambda r: -r["activity_before"])],
        "subjects": subject_rows,
        "topics": topic_rows,
    }


# ---------- one-call report with plain-language insights ----------
def _joined(items: list[str]) -> str:
    return ", ".join(items)


def build_insights(name: str, summary_: dict, games: dict, topics: dict, trends: dict) -> list[str]:
    out: list[str] = []
    days = summary_["period_days"]

    # questions
    n, prev = summary_["questions_in_period"], summary_["questions_previous_period"]
    if n == 0:
        out.append(f"{name} has not asked Zaki any questions in the last {days} days.")
    else:
        line = f"{name} asked {n} question{'s' if n != 1 else ''} on {summary_['active_days_in_period']} of the last {days} days."
        if prev and n >= prev * 1.5 and n - prev >= 2:
            line += f" That is more than the {prev} in the previous {days} days."
        elif prev and n <= prev * 0.5 and prev - n >= 2:
            line += f" That is fewer than the {prev} in the previous {days} days."
        out.append(line)

    # games
    if games["total_sessions"] == 0:
        out.append(f"No games were played in the last {days} days.")
    else:
        line = (f"Played {games['total_sessions']} game session{'s' if games['total_sessions'] != 1 else ''} "
                f"on {games['days_played']} day{'s' if games['days_played'] != 1 else ''}")
        if games["total_minutes"]:
            line += f" (about {games['total_minutes']:g} minutes)"
        line += f". Favourite: {games['favourite_game']}."
        out.append(line)

    # topics
    if not topics["has_practice_data"]:
        out.append("No practice results have been recorded in this period, so strengths and weak spots "
                   "cannot be shown yet.")
    by_name = {r["name"]: r for r in topics["topics"]}
    if topics["needs_help"]:
        parts = [f"{t} ({by_name[t]['accuracy_percent']:g}% correct over {by_name[t]['practice_questions']} questions)"
                 for t in topics["needs_help"][:3]]
        out.append("Needs help with: " + _joined(parts) + ".")
    if topics["asking_often"]:
        parts = [f"{t} ({by_name[t]['questions_asked']} questions)" for t in topics["asking_often"][:3]]
        out.append("Keeps asking about: " + _joined(parts) + ". This may be a topic they find hard.")
    if topics["doing_well"]:
        out.append("Doing well in: " + _joined(topics["doing_well"][:3]) + ".")

    # trends
    rows = {r["name"]: r for r in trends["topics"]}
    if trends["improved"]:
        parts = [f"{t} ({rows[t]['change_points']:+g} points)" for t in trends["improved"][:3]]
        out.append("Improved: " + _joined(parts) + ".")
    if trends["declined"]:
        parts = [f"{t} ({rows[t]['change_points']:+g} points)" for t in trends["declined"][:3]]
        out.append("Dropped: " + _joined(parts) + ".")
    if trends["less_active"]:
        out.append("Practising or asking less about: " + _joined(trends["less_active"][:3]) + ".")
    return out


def report(student: dict, days: int, include_content: bool) -> dict:
    s = summary(student, days, include_content)
    g = games_report(student["id"], days)
    t = topics_report(student["id"], days)
    tr = trends_report(student["id"], days)
    return {
        "child": s["child"],
        "period_days": days,
        "insights": build_insights(student["username"], s, g, t, tr),
        "summary": s,
        "games": g,
        "topics": t,
        "trends": tr,
    }
