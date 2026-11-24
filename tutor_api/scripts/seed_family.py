"""Demo data for the ZAKI portal: ONE parent (Sarah Johnson) and TWO children (Alex, Maya).

    TUTOR_DB=demo.db python -m scripts.seed_family
    TUTOR_DB=demo.db uvicorn app.main:app

This seed contains NO chat messages at all: only games, lessons and practice results. Parents
therefore have nothing of the children's conversations to see, even if the privacy switch is off.

Logins (API usernames are first names, case-sensitive; the API's insight sentences use them.
The frontend maps its email field to these, see demo-data.ts):
    Sarah / demo1234   (parent@demo.com)   -> Sarah Johnson, parent of both children
    Alex  / demo1234   (student@demo.com)  -> Alex Johnson, Grade 10
    Maya  / demo1234   (maya@demo.com)     -> Maya Johnson, Grade 8

The patterns match the frontend's story so both sides agree:
  Alex: active every day for the last 7 days and not 8 days ago, strong in
        History/Physics/Maths, struggling with Essay Writing and Cell Biology.
  Maya: active the last 3 days, strong in English, struggling with Fractions (but improving).
Use a fresh database file; this refuses to run if the demo users already exist.
"""
from datetime import timedelta

from app import db, progress
from app.security import hash_password

PASSWORD = "demo1234"          # the API requires 8+ characters
PARENT = "Sarah"
ALEX = "Alex"
MAYA = "Maya"


def ts(days_ago: int, hour: int, minute: int = 0) -> str:
    """UTC timestamp for local time `hour:minute`, `days_ago` days back."""
    day = progress.local_today() - timedelta(days=days_ago)
    utc_hour = (hour - progress.settings.tz_offset_hours) % 24
    return f"{day.isoformat()} {utc_hour:02d}:{minute:02d}:00"


# ---- (days_ago, hour, minute, topic key, subject, total questions, correct) ----
ALEX_PRACTICE = [
    # Mathematics  ~88%  (older window: ~77%, so it shows as improved)
    (0, 15, 42, "algebra", "Mathematics", 10, 8),          # "Algebra Quiz 8/10" shown today
    (2, 16, 0, "algebra", "Mathematics", 10, 9),
    (5, 16, 30, "exponents", "Mathematics", 10, 9),
    (9, 16, 15, "pythagoras", "Mathematics", 10, 9),
    (13, 16, 0, "algebra", "Mathematics", 10, 9),
    (32, 16, 0, "algebra", "Mathematics", 10, 7),
    (42, 16, 0, "algebra", "Mathematics", 10, 8),
    (50, 16, 0, "algebra", "Mathematics", 10, 8),
    # Physics ~92%
    (1, 17, 0, "forces", "Physics", 10, 9),
    (4, 17, 0, "electricity", "Physics", 10, 10),
    (8, 17, 0, "energy", "Physics", 10, 9),
    (12, 17, 0, "waves", "Physics", 10, 9),
    (17, 17, 0, "forces", "Physics", 10, 9),
    # History ~95%
    (0, 14, 5, "industrial_revolution", "History", 10, 9),  # "History Quiz 9/10" shown today
    (3, 15, 30, "industrial_revolution", "History", 10, 9),
    (10, 15, 30, "world_war_1", "History", 10, 10),
    (15, 15, 30, "world_war_1", "History", 10, 10),
    # English ~76%: grammar/vocabulary fine, ESSAY WRITING is the weak spot
    (0, 16, 10, "vocabulary", "English", 10, 8),            # "English Vocabulary Quiz 8/10" today
    (2, 17, 30, "grammar", "English", 10, 10),
    (6, 17, 30, "grammar", "English", 10, 10),
    (11, 17, 30, "grammar", "English", 10, 9),
    (3, 18, 0, "essay_writing", "English", 10, 4),
    (9, 18, 0, "essay_writing", "English", 10, 5),
    (35, 18, 0, "essay_writing", "English", 10, 4),
    (45, 18, 0, "essay_writing", "English", 10, 4),
    # Biology ~73%: CELL BIOLOGY is the dip (older window ~67%, now 43%)
    (1, 18, 30, "cell_biology", "Biology", 10, 4),
    (8, 18, 30, "cell_biology", "Biology", 10, 5),
    (14, 18, 30, "cell_biology", "Biology", 10, 4),
    (10, 17, 45, "genetics", "Biology", 10, 10),
    (16, 17, 45, "genetics", "Biology", 10, 9),
    (12, 17, 45, "ecosystems", "Biology", 10, 10),
    (18, 17, 45, "ecosystems", "Biology", 10, 10),
    (33, 18, 30, "cell_biology", "Biology", 10, 7),
    (40, 18, 30, "cell_biology", "Biology", 10, 6),
    (47, 18, 30, "cell_biology", "Biology", 10, 7),
]
ALEX_LESSONS = [  # (days_ago, hour, minute, topic, subject)
    (0, 14, 30, "cell_biology", "Biology"), (0, 14, 52, "forces", "Physics"),
    (1, 16, 0, "algebra", "Mathematics"), (3, 15, 0, "essay_writing", "English"),
    (6, 16, 40, "grammar", "English"), (10, 17, 30, "genetics", "Biology"),
]
ALEX_GAMES = [  # (days_ago, hour, minute, game, seconds, result)
    (0, 15, 12, "maths_word_game", 1080, "completed"),      # 18 min, "Level 7 reached"
    (0, 16, 25, "memory_match", 840, "completed"),          # 14 min
    (2, 19, 0, "chess", 900, "win"), (3, 19, 0, "zaki_racing", 600, "completed"),
    (4, 19, 0, "maths_word_game", 960, "completed"), (5, 19, 0, "chess", 1200, "loss"),
    (9, 19, 0, "hangman", 480, "completed"), (11, 19, 0, "chess", 1080, "win"),
    (14, 19, 0, "memory_match", 600, "completed"),
    (31, 19, 0, "chess", 900, "win"), (44, 19, 0, "chess", 1000, "loss"),
    (36, 19, 0, "hangman", 480, "completed"), (48, 19, 0, "hangman", 540, "completed"),
]

MAYA_PRACTICE = [
    # Mathematics ~65%: FRACTIONS is the struggle but improving (previous 2 weeks 35%, now 47%)
    (0, 15, 55, "fractions", "Mathematics", 10, 6),         # "Fractions Quiz 6/10" shown today
    (1, 16, 0, "fractions", "Mathematics", 10, 4),
    (4, 16, 0, "fractions", "Mathematics", 10, 4),
    (16, 16, 0, "fractions", "Mathematics", 10, 3),
    (22, 16, 0, "fractions", "Mathematics", 10, 4),
    (2, 16, 30, "percentages", "Mathematics", 10, 8),
    (6, 16, 30, "percentages", "Mathematics", 10, 9),
    (10, 16, 30, "percentages", "Mathematics", 10, 9),
    (36, 16, 30, "percentages", "Mathematics", 10, 6),
    (46, 16, 30, "percentages", "Mathematics", 10, 6),
    (8, 16, 45, "decimals", "Mathematics", 10, 9),
    (12, 16, 45, "decimals", "Mathematics", 10, 9),
    # English ~92% (older ~80%)
    (0, 14, 15, "reading_comprehension", "English", 10, 9),  # "Reading Comprehension Quiz 9/10"
    (2, 15, 0, "reading_comprehension", "English", 10, 10),
    (5, 15, 0, "reading_comprehension", "English", 10, 9),
    (9, 15, 0, "reading_comprehension", "English", 10, 9),
    (4, 15, 30, "poetry", "English", 10, 9),
    (11, 15, 30, "grammar", "English", 10, 9),
    (34, 15, 0, "reading_comprehension", "English", 10, 8),
    (44, 15, 0, "reading_comprehension", "English", 10, 8),
    # Science ~85%
    (1, 17, 0, "photosynthesis", "Science", 10, 9),
    (5, 17, 15, "states_of_matter", "Science", 10, 8),
    (8, 17, 0, "ecosystems", "Science", 10, 9),
    (13, 17, 0, "forces", "Science", 10, 8),
    # Geography ~80%
    (6, 17, 30, "map_skills", "Geography", 10, 8),
    (12, 17, 30, "climate", "Geography", 10, 8),
    (15, 17, 30, "rivers", "Geography", 10, 9),
    (18, 17, 30, "rivers", "Geography", 10, 7),
    # History ~77%
    (9, 17, 45, "ancient_egypt", "History", 10, 8),
    (14, 17, 45, "ancient_egypt", "History", 10, 7),
    (17, 17, 45, "romans", "History", 10, 8),
]
MAYA_LESSONS = [
    (0, 14, 40, "photosynthesis", "Science"), (0, 15, 35, "equivalent_fractions", "Mathematics"),
    (1, 15, 40, "fractions", "Mathematics"), (4, 15, 40, "fractions", "Mathematics"),
    (6, 16, 10, "percentages", "Mathematics"), (9, 17, 15, "ancient_egypt", "History"),
]
MAYA_GAMES = [
    (0, 15, 10, "hangman", 900, "completed"),               # 15 min
    (1, 18, 0, "memory_match", 600, "completed"), (4, 18, 0, "music_studio", 1500, "completed"),
    (6, 18, 0, "hangman", 540, "completed"), (8, 18, 0, "tic_tac_toe", 300, "win"),
    (11, 18, 0, "music_studio", 1320, "completed"), (14, 18, 0, "memory_match", 660, "completed"),
    (18, 18, 0, "hangman", 480, "completed"),
    (32, 18, 0, "music_studio", 1200, "completed"), (38, 18, 0, "music_studio", 1380, "completed"),
    (50, 18, 0, "music_studio", 1260, "completed"), (35, 18, 0, "hangman", 600, "completed"),
    (47, 18, 0, "hangman", 540, "completed"),
]


def load(user_id: int, practice, lessons, games) -> None:
    for d, h, m, topic, subject, total, correct in practice:
        db.add_event(user_id, "practice", topic, subject=subject, total=total,
                     correct=correct, created_at=ts(d, h, m))
    for d, h, m, topic, subject in lessons:
        db.add_event(user_id, "learn", topic, subject=subject, created_at=ts(d, h, m))
    for d, h, m, game, secs, result in games:
        db.add_event(user_id, "game", game, duration_sec=secs, result=result, created_at=ts(d, h, m))


def seed_family() -> dict:
    db.init_db()
    for name in (PARENT, ALEX, MAYA):
        if db.get_user_by_name(name):
            raise SystemExit(f"{name} already exists. Use a fresh TUTOR_DB file.")
    pid = db.create_user(PARENT, hash_password(PASSWORD), "parent")
    aid = db.create_user(ALEX, hash_password(PASSWORD), "student")
    mid = db.create_user(MAYA, hash_password(PASSWORD), "student")
    db.link_parent(pid, aid)
    db.link_parent(pid, mid)
    load(aid, ALEX_PRACTICE, ALEX_LESSONS, ALEX_GAMES)
    load(mid, MAYA_PRACTICE, MAYA_LESSONS, MAYA_GAMES)
    from scripts.demo_quizzes import seed_quizzes      # a year of quizzes with every question, for the Grades tab
    seed_quizzes(aid, mid)
    return {"parent_id": pid, "alex_id": aid, "maya_id": mid}


if __name__ == "__main__":
    ids = seed_family()
    print("Demo family created.")
    print(f"  Parent : {PARENT} / {PASSWORD}   (children: Alex id={ids['alex_id']}, Maya id={ids['maya_id']})")
    print(f"  Alex   : {ALEX} / {PASSWORD}")
    print(f"  Maya   : {MAYA} / {PASSWORD}")
