"""Fills the database with DEMO data for one fake family, so the parent endpoints can be shown
without weeks of real use.  Run from the project folder:

    python -m scripts.seed_demo

It creates a parent and a student, links them, and adds ~8 weeks of made-up activity with known patterns.
Do not run it against a database that holds real students you care about; use a separate file:

    TUTOR_DB=demo.db python -m scripts.seed_demo
    TUTOR_DB=demo.db uvicorn app.main:app
"""
import sys
from datetime import timedelta

from app import db, progress
from app.security import hash_password

PARENT = "demo_parent"
STUDENT = "demo_student"
PASSWORD = "demo-password-123"

# topic: (sessions in the older 4 weeks, accuracy then, sessions in the last 4 weeks, accuracy now)
# Each practice session is 10 questions, so accuracy is exact.
PRACTICE_PLAN = {
    "hcf":         (4, 0.4, 5, 0.9),    # improved
    "lcm":         (4, 0.8, 4, 0.5),    # declined
    "fractions":   (3, 0.4, 5, 0.3),    # struggling
    "area":        (3, 0.7, 4, 0.9),    # strong
    "percentages": (3, 0.7, 3, 0.7),    # stable
    "decimals":    (5, 0.8, 0, 0.0),    # stopped practising
    "pythagoras":  (0, 0.0, 3, 0.7),    # new
}

# game: (sessions in the older 4 weeks, sessions in the last 4 weeks)
GAME_PLAN = {
    "chess": (3, 6), "zaki_racing": (2, 4), "hangman": (4, 3),
    "memory_match": (3, 2), "tic_tac_toe": (0, 1), "music_studio": (3, 0),
}

QUESTIONS_NOW = [
    "How do I add fractions?", "What is a numerator?", "Why do I need a common denominator?",
    "How do I simplify fractions?", "What is a mixed fraction?", "What is the HCF of 12 and 18?",
    "How do I find the HCF?", "What is the area of a rectangle?", "How do I find area?",
    "Why is the sky blue?", "How far is the moon?", "What is a noun?", "Tell me a fun fact",
]
QUESTIONS_BEFORE = [
    "What is the LCM of 4 and 6?", "How do I work out the LCM?", "What is a decimal?",
    "How do I add decimals?", "What is 50 percent of 80?", "Who built the pyramids?",
]


def _spread(n: int, first_day_ago: int, last_day_ago: int) -> list[int]:
    """n day offsets spread evenly from first_day_ago to last_day_ago (both counted back from today)."""
    if n == 0:
        return []
    if n == 1:
        return [(first_day_ago + last_day_ago) // 2]
    step = (last_day_ago - first_day_ago) / (n - 1)
    return [round(first_day_ago + i * step) for i in range(n)]


def _ts(days_ago: int, hour: int = 16, minute: int = 0) -> str:
    """UTC timestamp for `hour`:`minute` local time, `days_ago` days back."""
    day = progress.local_today() - timedelta(days=days_ago)
    utc_hour = (hour - progress.settings.tz_offset_hours) % 24
    return f"{day.isoformat()} {utc_hour:02d}:{minute:02d}:00"


def seed_demo() -> dict:
    db.init_db()
    if db.get_user_by_name(PARENT) or db.get_user_by_name(STUDENT):
        raise SystemExit("Demo users already exist in this database. Use a fresh TUTOR_DB file.")
    pid = db.create_user(PARENT, hash_password(PASSWORD), "parent")
    sid = db.create_user(STUDENT, hash_password(PASSWORD), "student")
    db.link_parent(pid, sid)

    # practice: older window = 30..54 days ago, recent window = 1..26 days ago
    for topic, (n_old, acc_old, n_new, acc_new) in PRACTICE_PLAN.items():
        for n, acc, lo, hi in ((n_old, acc_old, 30, 54), (n_new, acc_new, 1, 26)):
            for day in _spread(n, lo, hi):
                db.add_event(sid, "practice", topic, subject="Maths", total=10,
                             correct=round(acc * 10), created_at=_ts(day, 17))
                db.add_event(sid, "learn", topic, subject="Maths", created_at=_ts(day, 16, 40))

    # games
    results = ["win", "loss", "win", "draw", "loss", "win"]
    for game, (n_old, n_new) in GAME_PLAN.items():
        for n, lo, hi in ((n_old, 30, 54), (n_new, 1, 26)):
            for i, day in enumerate(_spread(n, lo, hi)):
                db.add_event(sid, "game", game, duration_sec=480 + 120 * (i % 5),
                             result=results[i % 6] if game in ("chess", "tic_tac_toe") else "completed",
                             created_at=_ts(day, 18))

    # chat questions (each followed by a tutor reply)
    for questions, lo, hi in ((QUESTIONS_NOW, 0, 25), (QUESTIONS_BEFORE, 31, 53)):
        for q, day in zip(questions, _spread(len(questions), lo, hi)):
            db.add_message(sid, "user", q, _ts(day, 15))
            db.add_message(sid, "assistant", "Great question! Let me explain step by step...", _ts(day, 15, 1))

    return {"parent": PARENT, "student": STUDENT, "password": PASSWORD,
            "parent_id": pid, "student_id": sid}


if __name__ == "__main__":
    info = seed_demo()
    print("Demo data created.")
    print(f"  Parent login : {info['parent']} / {info['password']}   (child id {info['student_id']})")
    print(f"  Student login: {info['student']} / {info['password']}")
    print("Start the API and open /docs, log in as the parent, and try /parent/children/"
          f"{info['student_id']}/report")
    sys.exit(0)
