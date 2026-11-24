"""Quiz endpoints.

  POST /activity/quiz                              the device saves a finished quiz with every question (student)
  GET  /parent/children/{id}/quizzes?range=week    bars for the Grades tab: week (default), month, year, all
  GET  /parent/children/{id}/quizzes/weaknesses    topics the child keeps getting wrong, with the wrong questions
  GET  /parent/children/{id}/quizzes/{quiz_id}     one quiz with all its questions
Parents only reach their own linked children (404 otherwise, like the other parent endpoints).
"""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from . import catalog, db, quizzes
from .security import require_role

router = APIRouter()

RangeName = Literal["week", "month", "year", "all"]


class QuestionIn(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    correct_answer: str = Field(min_length=1, max_length=300)
    student_answer: str | None = Field(default=None, max_length=300, description="null if skipped")
    is_correct: bool | None = Field(default=None, description="leave out to let the server compare the answers")
    topic: str | None = Field(default=None, max_length=40, description="defaults to the quiz topic")


class QuizIn(BaseModel):
    subject: str = Field(min_length=1, max_length=30, examples=["Mathematics"])
    topic: str = Field(min_length=1, max_length=40, examples=["Algebra"])
    title: str | None = Field(default=None, max_length=80, description="defaults to '<topic> quiz'")
    duration_seconds: int | None = Field(default=None, ge=0, le=4 * 3600)
    questions: list[QuestionIn] = Field(min_length=1, max_length=100)


def linked_child(child_id: int, parent=Depends(require_role("parent"))):
    if not db.is_linked(parent["id"], child_id):
        raise HTTPException(404, "Child not found")
    return db.get_user_by_id(child_id)


@router.post("/activity/quiz", status_code=201)
def log_quiz(body: QuizIn, user=Depends(require_role("student"))):
    """Call when a quiz ends. Send every question and the student's answer: that is what lets parents
    see which topics are weak. The score is counted by the server from the questions."""
    topic = catalog.slug(body.topic)
    if not topic:
        raise HTTPException(422, "Topic must contain letters or numbers")
    questions = []
    for q in body.questions:
        q_topic = catalog.slug(q.topic) if q.topic and catalog.slug(q.topic) else topic
        is_correct = q.is_correct if q.is_correct is not None else quizzes.same_answer(q.student_answer, q.correct_answer)
        questions.append({"topic": q_topic, "question": q.question.strip(), "correct_answer": q.correct_answer.strip(),
                          "student_answer": q.student_answer.strip() if q.student_answer else None,
                          "is_correct": is_correct})
    title = (body.title or "").strip() or f"{catalog.label(topic)} quiz"
    quiz_id = db.add_quiz(user["id"], catalog.subject_for(topic, body.subject), topic, title, questions,
                          duration_sec=body.duration_seconds)
    right = sum(1 for q in questions if q["is_correct"])
    return {"recorded": "quiz", "quiz_id": quiz_id, "correct": right, "total": len(questions),
            "score_percent": round(100 * right / len(questions), 1)}


@router.get("/parent/children/{child_id}/quizzes")
def child_quizzes(range: RangeName = Query("week", description="week = last 7 days, month = 30, year = 365, all = since the first quiz"),
                  child=Depends(linked_child)):
    """One entry per quiz (title, subject, score, grade, date) plus per-subject averages, for the Grades bar chart."""
    return quizzes.quiz_report(child, range)


# Declared before /{quiz_id} so the word "weaknesses" is not read as a quiz id.
@router.get("/parent/children/{child_id}/quizzes/weaknesses")
def child_quiz_weaknesses(range: RangeName = Query("month"), child=Depends(linked_child)):
    """Topics grouped from every stored question: weak (under 60%), strong (80%+), developing, with the wrong answers."""
    return quizzes.weaknesses(child, range)


@router.get("/parent/children/{child_id}/quizzes/{quiz_id}")
def child_quiz_detail(quiz_id: int, child=Depends(linked_child)):
    """One quiz with every question, the right answer and what the child answered."""
    quiz = quizzes.quiz_detail(child["id"], quiz_id)
    if quiz is None:
        raise HTTPException(404, "Quiz not found")
    return quiz
