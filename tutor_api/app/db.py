"""SQLite storage: users, parent-child links and chat messages."""
import sqlite3
from datetime import date

from .config import settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash BLOB NOT NULL,
    role TEXT NOT NULL DEFAULT 'student' CHECK (role IN ('student', 'parent')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_messages_user ON messages(user_id, id);
CREATE TABLE IF NOT EXISTS parent_links (
    parent_id  INTEGER NOT NULL REFERENCES users(id),
    student_id INTEGER NOT NULL REFERENCES users(id),
    PRIMARY KEY (parent_id, student_id)
);
-- What the child does on the device besides chatting.
--   game     : name = game key, optional duration and result
--   learn    : name = topic key (child opened a lesson)
--   practice : name = topic key, total = questions attempted, correct = questions right
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    kind TEXT NOT NULL CHECK (kind IN ('game', 'learn', 'practice')),
    name TEXT NOT NULL,
    subject TEXT,
    total INTEGER,
    correct INTEGER,
    duration_sec INTEGER,
    result TEXT CHECK (result IN ('win', 'loss', 'draw', 'completed')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_events_user ON events(user_id, kind, created_at);
-- Quizzes the child took on the device, with every question kept so weak spots can be found.
CREATE TABLE IF NOT EXISTS quizzes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    subject TEXT NOT NULL,
    topic TEXT NOT NULL,
    title TEXT NOT NULL,
    total INTEGER NOT NULL,
    correct INTEGER NOT NULL,
    duration_sec INTEGER,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_quizzes_user ON quizzes(user_id, created_at);
CREATE TABLE IF NOT EXISTS quiz_questions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    quiz_id INTEGER NOT NULL REFERENCES quizzes(id),
    position INTEGER NOT NULL,
    topic TEXT NOT NULL,
    question TEXT NOT NULL,
    correct_answer TEXT NOT NULL,
    student_answer TEXT,
    is_correct INTEGER NOT NULL CHECK (is_correct IN (0, 1))
);
CREATE INDEX IF NOT EXISTS idx_quiz_questions_quiz ON quiz_questions(quiz_id, position);
"""


def get_conn() -> sqlite3.Connection:
    # db_path is read at call time so tests can point it at a temp file.
    conn = sqlite3.connect(settings.db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript(SCHEMA)
        # Upgrade a database created before parents existed: every old user is a student.
        cols = [r["name"] for r in conn.execute("PRAGMA table_info(users)")]
        if "role" not in cols:
            conn.execute(
                "ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'student' "
                "CHECK (role IN ('student', 'parent'))"
            )


# ---------- users ----------
def create_user(username: str, password_hash: bytes, role: str = "student") -> int:
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
            (username, password_hash, role),
        )
        return cur.lastrowid


def get_user_by_name(username: str):
    with get_conn() as conn:
        return conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()


def get_user_by_id(user_id: int):
    with get_conn() as conn:
        return conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()


# ---------- parent <-> child links ----------
def link_parent(parent_id: int, student_id: int) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO parent_links (parent_id, student_id) VALUES (?, ?)",
            (parent_id, student_id),
        )


def is_linked(parent_id: int, student_id: int) -> bool:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT 1 FROM parent_links WHERE parent_id = ? AND student_id = ?",
            (parent_id, student_id),
        ).fetchone()
    return row is not None


def children_of(parent_id: int):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT u.id, u.username FROM parent_links l JOIN users u ON u.id = l.student_id "
            "WHERE l.parent_id = ? ORDER BY u.username",
            (parent_id,),
        ).fetchall()
    return [dict(r) for r in rows]


# ---------- messages ----------
def add_message(user_id: int, role: str, content: str, created_at: str | None = None) -> None:
    """created_at (UTC, 'YYYY-MM-DD HH:MM:SS') is only for tests/imports; normally the DB sets it."""
    with get_conn() as conn:
        if created_at is None:
            conn.execute(
                "INSERT INTO messages (user_id, role, content) VALUES (?, ?, ?)",
                (user_id, role, content),
            )
        else:
            conn.execute(
                "INSERT INTO messages (user_id, role, content, created_at) VALUES (?, ?, ?, ?)",
                (user_id, role, content, created_at),
            )


def recent_messages(user_id: int, limit: int):
    """Oldest-first list of the last `limit` messages."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT role, content, created_at FROM messages WHERE user_id = ? "
            "ORDER BY id DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
    return [dict(r) for r in reversed(rows)]


# ---------- progress queries (questions = messages the student sent) ----------
def _offset() -> str:
    return f"{settings.tz_offset_hours:+d} hours"


def question_totals(user_id: int) -> dict:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS total, MIN(created_at) AS first, MAX(created_at) AS last "
            "FROM messages WHERE user_id = ? AND role = 'user'",
            (user_id,),
        ).fetchone()
    return {"total": row["total"], "first": row["first"], "last": row["last"]}


def questions_per_day(user_id: int, since: date) -> dict[str, int]:
    """{'YYYY-MM-DD': count} for local days on/after `since` that had activity."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT date(created_at, ?) AS d, COUNT(*) AS n FROM messages "
            "WHERE user_id = ? AND role = 'user' AND date(created_at, ?) >= ? GROUP BY d",
            (_offset(), user_id, _offset(), since.isoformat()),
        ).fetchall()
    return {r["d"]: r["n"] for r in rows}


def active_dates(user_id: int, limit: int = 400) -> list[str]:
    """Most recent local days with any activity (a question, game, lesson or practice), newest first."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT d FROM ("
            " SELECT date(created_at, ?) AS d FROM messages WHERE user_id = ? AND role = 'user'"
            " UNION"
            " SELECT date(created_at, ?) AS d FROM events WHERE user_id = ?"
            ") ORDER BY d DESC LIMIT ?",
            (_offset(), user_id, _offset(), user_id, limit),
        ).fetchall()
    return [r["d"] for r in rows]


def recent_questions(user_id: int, limit: int):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT content, created_at FROM messages WHERE user_id = ? AND role = 'user' "
            "ORDER BY id DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
    return [dict(r) for r in rows]


# ---------- activity events and range queries ----------
# A "range" is local days start <= day < end (dates), using the configured UTC offset.
def add_event(user_id: int, kind: str, name: str, *, subject: str | None = None,
              total: int | None = None, correct: int | None = None,
              duration_sec: int | None = None, result: str | None = None,
              created_at: str | None = None) -> None:
    """created_at (UTC, 'YYYY-MM-DD HH:MM:SS') is only for tests/imports; normally the DB sets it."""
    cols = ["user_id", "kind", "name", "subject", "total", "correct", "duration_sec", "result"]
    vals = [user_id, kind, name, subject, total, correct, duration_sec, result]
    if created_at is not None:
        cols.append("created_at")
        vals.append(created_at)
    with get_conn() as conn:
        conn.execute(
            f"INSERT INTO events ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})", vals
        )


def _in_range(column: str = "created_at") -> str:
    return f"date({column}, ?) >= ? AND date({column}, ?) < ?"


def _range_args(start: date, end: date) -> list:
    return [_offset(), start.isoformat(), _offset(), end.isoformat()]


def count_questions(user_id: int, start: date, end: date) -> int:
    with get_conn() as conn:
        return conn.execute(
            f"SELECT COUNT(*) FROM messages WHERE user_id = ? AND role = 'user' AND {_in_range()}",
            [user_id, *_range_args(start, end)],
        ).fetchone()[0]


def questions_between(user_id: int, start: date, end: date):
    with get_conn() as conn:
        rows = conn.execute(
            f"SELECT content, created_at FROM messages WHERE user_id = ? AND role = 'user' "
            f"AND {_in_range()} ORDER BY id",
            [user_id, *_range_args(start, end)],
        ).fetchall()
    return [dict(r) for r in rows]


def game_stats(user_id: int, start: date, end: date):
    with get_conn() as conn:
        rows = conn.execute(
            f"SELECT name, COUNT(*) AS sessions, COALESCE(SUM(duration_sec), 0) AS secs, "
            f"COALESCE(SUM(result = 'win'), 0) AS wins, COALESCE(SUM(result = 'loss'), 0) AS losses, "
            f"COALESCE(SUM(result = 'draw'), 0) AS draws, MAX(created_at) AS last, "
            f"COUNT(DISTINCT date(created_at, ?)) AS days "
            f"FROM events WHERE user_id = ? AND kind = 'game' AND {_in_range()} "
            f"GROUP BY name ORDER BY sessions DESC, secs DESC, name",
            [_offset(), user_id, *_range_args(start, end)],
        ).fetchall()
    return [dict(r) for r in rows]


def game_days_and_sessions(user_id: int, start: date, end: date) -> tuple[int, int]:
    with get_conn() as conn:
        row = conn.execute(
            f"SELECT COUNT(DISTINCT date(created_at, ?)), COUNT(*) FROM events "
            f"WHERE user_id = ? AND kind = 'game' AND {_in_range()}",
            [_offset(), user_id, *_range_args(start, end)],
        ).fetchone()
    return row[0], row[1]


def practice_by_topic(user_id: int, start: date, end: date):
    with get_conn() as conn:
        rows = conn.execute(
            f"SELECT name AS topic, MAX(subject) AS subject, COUNT(*) AS sessions, "
            f"COALESCE(SUM(total), 0) AS total, COALESCE(SUM(correct), 0) AS correct "
            f"FROM events WHERE user_id = ? AND kind = 'practice' AND {_in_range()} GROUP BY name",
            [user_id, *_range_args(start, end)],
        ).fetchall()
    return [dict(r) for r in rows]


def learn_by_topic(user_id: int, start: date, end: date):
    with get_conn() as conn:
        rows = conn.execute(
            f"SELECT name AS topic, MAX(subject) AS subject, COUNT(*) AS views "
            f"FROM events WHERE user_id = ? AND kind = 'learn' AND {_in_range()} GROUP BY name",
            [user_id, *_range_args(start, end)],
        ).fetchall()
    return [dict(r) for r in rows]


# ---------- quizzes (every question is stored) ----------
def add_quiz(user_id: int, subject: str, topic: str, title: str, questions: list[dict], *,
             duration_sec: int | None = None, created_at: str | None = None) -> int:
    """Save a quiz and all its questions in one transaction. Each question dict has
    question, correct_answer, student_answer (or None), is_correct (bool) and topic.
    The totals are counted here from the questions, never taken from the caller."""
    total = len(questions)
    correct = sum(1 for q in questions if q["is_correct"])
    cols = ["user_id", "subject", "topic", "title", "total", "correct", "duration_sec"]
    vals = [user_id, subject, topic, title, total, correct, duration_sec]
    if created_at is not None:
        cols.append("created_at")
        vals.append(created_at)
    with get_conn() as conn:
        quiz_id = conn.execute(
            f"INSERT INTO quizzes ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})", vals
        ).lastrowid
        conn.executemany(
            "INSERT INTO quiz_questions (quiz_id, position, topic, question, correct_answer, student_answer, is_correct) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            [(quiz_id, i, q["topic"], q["question"], q["correct_answer"], q.get("student_answer"),
              1 if q["is_correct"] else 0) for i, q in enumerate(questions, 1)],
        )
    return quiz_id


def quizzes_between(user_id: int, start: date, end: date) -> list[dict]:
    """Quizzes on local days start <= day < end, oldest first. local_date is the child's local day."""
    with get_conn() as conn:
        rows = conn.execute(
            f"SELECT id, subject, topic, title, total, correct, duration_sec, created_at, "
            f"date(created_at, ?) AS local_date FROM quizzes "
            f"WHERE user_id = ? AND {_in_range()} ORDER BY created_at, id",
            [_offset(), user_id, *_range_args(start, end)],
        ).fetchall()
    return [dict(r) for r in rows]


def first_quiz_date(user_id: int) -> str | None:
    with get_conn() as conn:
        row = conn.execute("SELECT date(MIN(created_at), ?) FROM quizzes WHERE user_id = ?",
                           [_offset(), user_id]).fetchone()
    return row[0]


def get_quiz(user_id: int, quiz_id: int) -> dict | None:
    """One quiz with its questions, only if it belongs to this student."""
    with get_conn() as conn:
        quiz = conn.execute(
            "SELECT id, subject, topic, title, total, correct, duration_sec, created_at, "
            "date(created_at, ?) AS local_date FROM quizzes WHERE id = ? AND user_id = ?",
            [_offset(), quiz_id, user_id]).fetchone()
        if quiz is None:
            return None
        questions = conn.execute(
            "SELECT position, topic, question, correct_answer, student_answer, is_correct "
            "FROM quiz_questions WHERE quiz_id = ? ORDER BY position", [quiz_id]).fetchall()
    return {**dict(quiz), "questions": [dict(q) for q in questions]}


def quiz_questions_between(user_id: int, start: date, end: date) -> list[dict]:
    """Every question answered in the range, newest first, with the quiz it came from."""
    with get_conn() as conn:
        rows = conn.execute(
            f"SELECT q.topic AS topic, z.subject AS subject, q.question, q.correct_answer, q.student_answer, "
            f"q.is_correct, z.id AS quiz_id, z.title AS quiz_title, date(z.created_at, ?) AS local_date "
            f"FROM quiz_questions q JOIN quizzes z ON z.id = q.quiz_id "
            f"WHERE z.user_id = ? AND {_in_range('z.created_at')} ORDER BY z.created_at DESC, q.position",
            [_offset(), user_id, *_range_args(start, end)],
        ).fetchall()
    return [dict(r) for r in rows]
