"""Tutor API: login, chat (streaming or not), history, health."""
import asyncio
import sqlite3
from contextlib import asynccontextmanager
from typing import AsyncIterator, Callable

import httpx
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from . import catalog, db, gemini_insights, llm, progress
from .config import settings
from .security import (check_rate_limit, create_token, current_user, hash_password,
                       require_admin, require_role, verify_password)

# The Pi can realistically run one generation at a time. Extra requests wait their turn.
_llm_lock = asyncio.Lock()


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    yield


app = FastAPI(title="Offline Tutor API", lifespan=lifespan)

from fastapi.middleware.cors import CORSMiddleware

# Websites allowed to call this API from a browser. Add your hosted frontend (for example your Vercel
# address) with TUTOR_CORS_ORIGINS="https://zaki-portal.vercel.app,https://other.example.com"
import os
_extra_origins = [o.strip().rstrip("/") for o in os.environ.get("TUTOR_CORS_ORIGINS", "").split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:4200", "http://127.0.0.1:4200",
        "http://localhost:3000", "http://127.0.0.1:3000",
    ] + _extra_origins,
    allow_methods=["*"],
    allow_headers=["Authorization", "Content-Type"],
)

from .assistant_routes import router as assistant_router
app.include_router(assistant_router)

from .quiz_routes import router as quiz_router
app.include_router(quiz_router)

def get_llm() -> Callable[[list[dict]], AsyncIterator[str]]:
    """Dependency so tests can replace the model with a fake."""
    return llm.stream_chat


def get_insight_writer():
    """Dependency: writes the report's insights with Gemini. Tests replace it with a fake."""
    return gemini_insights.generate


# ---------- schemas ----------
class Credentials(BaseModel):
    username: str = Field(min_length=3, max_length=40)
    password: str = Field(min_length=8, max_length=128)


class RegisterIn(Credentials):
    role: Literal["student", "parent"] = "student"


class LinkIn(BaseModel):
    parent_username: str
    student_username: str


class GameIn(BaseModel):
    game: str = Field(min_length=1, max_length=40, examples=["Chess"])
    duration_seconds: int | None = Field(default=None, ge=0, le=4 * 3600)
    result: Literal["win", "loss", "draw", "completed"] | None = None


class LearnIn(BaseModel):
    topic: str = Field(min_length=1, max_length=40, examples=["Fractions"])
    subject: str | None = Field(default=None, max_length=30)


class PracticeIn(BaseModel):
    topic: str = Field(min_length=1, max_length=40, examples=["Fractions"])
    subject: str | None = Field(default=None, max_length=30)
    total_questions: int = Field(ge=1, le=200)
    correct_answers: int = Field(ge=0)

    @model_validator(mode="after")
    def correct_cannot_exceed_total(self):
        if self.correct_answers > self.total_questions:
            raise ValueError("correct_answers cannot be more than total_questions")
        return self


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    stream: bool = False


# ---------- endpoints ----------
@app.get("/health")
async def health():
    return {"api": "ok", "ollama": await llm.ollama_alive(), "model": settings.model,
            "ai_insights": "gemini" if gemini_insights.enabled() else "templates"}


@app.post("/auth/register", status_code=201, dependencies=[Depends(require_admin)])
def register(body: RegisterIn):
    """Teacher/admin creates student or parent accounts (no open sign-up)."""
    try:
        user_id = db.create_user(body.username, hash_password(body.password), body.role)
    except sqlite3.IntegrityError:
        raise HTTPException(409, "Username already taken")
    return {"id": user_id, "username": body.username, "role": body.role}


@app.post("/admin/links", status_code=201, dependencies=[Depends(require_admin)])
def link_parent_to_student(body: LinkIn):
    """Connect a parent account to a child's account. A parent can have several children."""
    parent = db.get_user_by_name(body.parent_username)
    student = db.get_user_by_name(body.student_username)
    if parent is None or student is None:
        raise HTTPException(404, "Parent or student not found")
    if parent["role"] != "parent" or student["role"] != "student":
        raise HTTPException(400, "First name must be a parent account and second a student account")
    db.link_parent(parent["id"], student["id"])
    return {"parent": parent["username"], "student": student["username"]}


@app.post("/auth/login")
def login(body: Credentials):
    user = db.get_user_by_name(body.username)
    # Same error for 'no such user' and 'wrong password' so usernames can't be probed.
    if user is None or not verify_password(body.password, user["password_hash"]):
        raise HTTPException(401, "Incorrect username or password")
    return {"access_token": create_token(user["id"]), "token_type": "bearer", "role": user["role"]}


@app.get("/me")
def me(user=Depends(current_user)):
    """Lets the web app decide which screens to show (student chat vs parent dashboard)."""
    return {"id": user["id"], "username": user["username"], "role": user["role"]}


@app.post("/chat")
async def chat(body: ChatIn, user=Depends(require_role("student")), llm_fn=Depends(get_llm)):
    check_rate_limit(user["id"])

    history = db.recent_messages(user["id"], settings.history_turns * 2)
    messages = [{"role": "system", "content": settings.system_prompt}]
    messages += [{"role": m["role"], "content": m["content"]} for m in history]
    messages.append({"role": "user", "content": body.message})
    db.add_message(user["id"], "user", body.message)

    async def generate() -> AsyncIterator[str]:
        parts: list[str] = []
        async with _llm_lock:
            try:
                async for chunk in llm_fn(messages):
                    parts.append(chunk)
                    yield chunk
            finally:
                # Save whatever was produced, even if the client disconnected midway.
                if parts:
                    db.add_message(user["id"], "assistant", "".join(parts))

    if body.stream:
        return StreamingResponse(generate(), media_type="text/plain; charset=utf-8")

    try:
        reply = "".join([c async for c in generate()])
    except httpx.HTTPError:
        raise HTTPException(503, "The tutor model is not available right now")
    return {"reply": reply}


@app.get("/history")
def history(limit: int = 50, user=Depends(require_role("student"))):
    return {"messages": db.recent_messages(user["id"], max(1, min(limit, 200)))}


# ---------- activity reporting (called by the ZAKI device for the logged-in student) ----------
def _key(text: str) -> str:
    key = catalog.slug(text)
    if not key:
        raise HTTPException(422, "Name must contain letters or numbers")
    return key


@app.post("/activity/game", status_code=201)
def log_game(body: GameIn, user=Depends(require_role("student"))):
    """Call when a game session ends. Tells parents which games are played, how often and for how long."""
    key = _key(body.game)
    db.add_event(user["id"], "game", key, duration_sec=body.duration_seconds, result=body.result)
    return {"recorded": "game", "game": key}


@app.post("/activity/learn", status_code=201)
def log_learn(body: LearnIn, user=Depends(require_role("student"))):
    """Call when the student opens a lesson on the Learn screen."""
    key = _key(body.topic)
    db.add_event(user["id"], "learn", key, subject=catalog.subject_for(key, body.subject))
    return {"recorded": "learn", "topic": key}


@app.post("/activity/practice", status_code=201)
def log_practice(body: PracticeIn, user=Depends(require_role("student"))):
    """Call after a practice question or set. This is what shows parents which topics are hard."""
    key = _key(body.topic)
    db.add_event(user["id"], "practice", key, subject=catalog.subject_for(key, body.subject),
                 total=body.total_questions, correct=body.correct_answers)
    return {"recorded": "practice", "topic": key}


# ---------- parent endpoints (read-only) ----------
def linked_child(child_id: int, parent=Depends(require_role("parent"))):
    """A parent can only reach children linked to them. Unlinked and nonexistent
    children both give 404 so a parent can't discover other students' accounts."""
    if not db.is_linked(parent["id"], child_id):
        raise HTTPException(404, "Child not found")
    return db.get_user_by_id(child_id)


@app.get("/parent/children")
def parent_children(parent=Depends(require_role("parent"))):
    return {"children": db.children_of(parent["id"])}


@app.get("/parent/children/{child_id}/summary")
def child_summary(days: int = Query(7, ge=1, le=90), child=Depends(linked_child)):
    """Headline numbers: questions asked, active days, streak, last active."""
    return progress.summary(child, days, include_content=settings.parent_sees_chats)


@app.get("/parent/children/{child_id}/activity")
def child_activity(days: int = Query(14, ge=1, le=90), child=Depends(linked_child)):
    """Questions per day (zeros included), ready to draw as a bar chart."""
    return {"child": child["username"], "days": progress.activity(child["id"], days)}


@app.get("/parent/children/{child_id}/games")
def child_games(days: int = Query(30, ge=1, le=180), child=Depends(linked_child)):
    """Which games the child plays, how often and for how long, and how that compares with before."""
    return progress.games_report(child["id"], days)


@app.get("/parent/children/{child_id}/topics")
def child_topics(days: int = Query(28, ge=1, le=180), child=Depends(linked_child)):
    """Every topic the child touched, with accuracy and a status (struggling / developing / strong ...)."""
    return progress.topics_report(child["id"], days)


@app.get("/parent/children/{child_id}/trends")
def child_trends(days: int = Query(28, ge=1, le=180), child=Depends(linked_child)):
    """Improved, dropped and less-active topics and subjects: this period compared with the one before."""
    return progress.trends_report(child["id"], days)


@app.get("/parent/children/{child_id}/report")
async def child_report(days: int = Query(14, ge=1, le=180),
                       ai: bool = Query(True, description="false = skip Gemini and use the fixed-template insights"),
                       child=Depends(linked_child), write_insights=Depends(get_insight_writer)):
    """Everything in one call, plus plain-language insights. Best for a dashboard's first screen.

    When a Gemini key is set, `insights` (and `headline`, `suggestions`) are written by Gemini.
    `insights_source` says which: "gemini" or "templates" (no key, Gemini failed, or ai=false).
    """
    report = progress.report(child, days, include_content=settings.parent_sees_chats)
    written = await write_insights(child, days) if ai else None
    if written:
        report.update(insights=written["insights"], headline=written["headline"],
                      suggestions=written["suggestions"], insights_source="gemini",
                      insights_model=written["model"], insights_generated_at=written["generated_at"])
    else:
        report.update(headline=None, suggestions=[], insights_source="templates")
    return report
