"""POST /parent/children/{child_id}/ask : the parent's AI assistant.

Parents only, and only for their own linked children (404 otherwise, like the other parent
endpoints). The assistant reads progress through fixed read-only tools (see assistant.py).
It never receives the child's chat messages.
"""
import logging
import os
from typing import Literal

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from . import assistant, db
from .security import check_rate_limit, require_role

router = APIRouter()
log = logging.getLogger("uvicorn.error")


def _debug() -> bool:
    return os.environ.get("TUTOR_ASSISTANT_DEBUG", "").strip().lower() in ("1", "true", "yes", "on")


def get_tool_llm() -> assistant.ChatFn:
    """The model to use, chosen from the environment (local Ollama by default).
    A dependency so tests can replace it with a fake."""
    return assistant.build_chat()


class HistoryItem(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=4000)


class AskBody(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    history: list[HistoryItem] = Field(default_factory=list, max_length=20)


def parent_and_child(child_id: int, parent=Depends(require_role("parent"))):
    # Unlinked and nonexistent children both give 404 so a parent can't discover other accounts.
    if not db.is_linked(parent["id"], child_id):
        raise HTTPException(404, "Child not found")
    return parent, db.get_user_by_id(child_id)


@router.post("/parent/children/{child_id}/ask")
async def ask_about_child(body: AskBody, pc=Depends(parent_and_child), chat=Depends(get_tool_llm)):
    parent, child = pc
    check_rate_limit(parent["id"])

    # Online models don't use this machine's CPU, so only local generation waits its turn.
    if getattr(chat, "external", False):
        model = chat                    # keep the marker: names are replaced before sending online
    else:
        from . import main  # imported late (main includes this router) to share the one-answer-at-a-time lock

        async def model(messages, tools):
            async with main._llm_lock:  # the Pi runs one generation at a time
                return await chat(messages, tools)

    try:
        return await assistant.run_assistant(
            {"id": child["id"], "username": child["username"]},
            body.question,
            [h.model_dump() for h in body.history],
            model,
        )
    except assistant.ConfigError as e:
        log.warning("Assistant not configured: %s", e)
        raise HTTPException(503, "The online AI service is not set up yet (missing key, address or model).")
    except assistant.AssistantUnavailable as e:
        log.warning("Assistant unavailable: %s", e)
        raise HTTPException(503, f"The AI assistant is unavailable right now. ({e})" if _debug()
                            else "The AI assistant is unavailable right now. Please try again.")
    except httpx.HTTPStatusError as e:
        log.warning("Assistant model call failed: %s", assistant.describe_error(e))
        if e.response.status_code == 429:
            raise HTTPException(429, "The AI service is busy. Please try again in a minute.")
        raise HTTPException(503, "The AI assistant is unavailable right now. Please try again.")
    except httpx.HTTPError as e:
        log.warning("Assistant model call failed: %s", assistant.describe_error(e))
        raise HTTPException(503, "The AI assistant is unavailable right now. Is the AI model running or online?")
