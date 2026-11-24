"""AI-written insights for the parent report, using Google Gemini.

What it does
  The report used to build its "insights" from fixed sentence templates (progress.build_insights).
  When a Gemini key is configured, Gemini now reads the child's progress numbers and writes the
  headline, the insights and a few things a parent can do at home. If Gemini is not configured,
  is offline, is rate limited or returns something unusable, `generate` returns None and the
  caller keeps the template insights, so the report never breaks.

Privacy (same rules as the parent assistant in assistant.py)
  * Only the allow-listed progress tools are used. Nothing the child typed to the tutor is sent,
    and nothing derived from it (question counts, "asking often" topics) is sent either.
  * The child's name, school and teachers are swapped for placeholders before sending and swapped
    back in the answer (assistant.Redactor). Set TUTOR_INSIGHTS_REDACT=false to turn this off.
  * The API key is read from the environment and sent in a header, never put in a URL or a log.

Settings (environment variables)
  GEMINI_API_KEY              the key from Google AI Studio. Without it the template insights are used.
  GEMINI_MODEL                default gemini-3.8-flash
  GEMINI_BASE_URL             default https://generativelanguage.googleapis.com/v1beta
  TUTOR_INSIGHTS_AI           true/false switch, default true (only matters when a key is set)
  TUTOR_INSIGHTS_REDACT       default true
  TUTOR_INSIGHTS_SCHOOL_RECORDS  include school grades/attendance in what Gemini reads, default true
  TUTOR_INSIGHTS_CACHE_MINUTES   reuse an answer while the data is unchanged, default 360
  TUTOR_INSIGHTS_MIN_SECONDS     never call Gemini more often than this for one child, default 300
"""
import hashlib
import json
import logging
import os
import re
import time
from datetime import datetime, timezone

import httpx

from . import assistant, quizzes

log = logging.getLogger("uvicorn.error")

DEFAULT_MODEL = "gemini-3.8-flash"
DEFAULT_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
MAX_INSIGHTS = 5
MIN_INSIGHTS = 2            # fewer than this usable lines = fall back to the templates
MAX_SUGGESTIONS = 3
MAX_LINE = 300
MAX_DAYS = 90               # the progress tools cap their window at 90 days


class GeminiError(Exception):
    """Gemini answered, but not with something we can use."""


# --------------------------------------------------------------------------- settings
def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _flag(name: str, default: bool) -> bool:
    value = _env(name)
    return default if not value else value.lower() not in ("0", "false", "no", "off")


def api_key() -> str:
    return _env("GEMINI_API_KEY") or _env("TUTOR_GEMINI_API_KEY")


def enabled() -> bool:
    return bool(api_key()) and _flag("TUTOR_INSIGHTS_AI", True)


def model_name() -> str:
    return _env("GEMINI_MODEL") or DEFAULT_MODEL


# --------------------------------------------------------------------------- the prompt
SYSTEM_PROMPT = (
    "You are Zaki, a warm and practical assistant that writes a short progress summary for a parent "
    "about their child, using data from the Zaki learning device (and school records when present).\n\n"
    "Rules:\n"
    "- Use ONLY facts in the JSON data. Never invent scores, grades, dates, teachers or events. "
    "Quote numbers exactly as given.\n"
    "- Always call the child [CHILD]. Do not use any other name for them.\n"
    "- Say what is going well, what needs attention and what changed compared with the earlier period. "
    "Put the most important thing first.\n"
    "- If there is little data for a topic, say so instead of guessing.\n"
    "- If the data has quizzes, say how the child did and name the weak topics, because that is where help is needed.\n"
    "- You cannot see what the child typed to the tutor and must not guess at it.\n"
    "- Be kind and specific. Do not blame the child. Do not diagnose anything.\n"
    "- Plain text only: no markdown, no asterisks, no emoji.\n\n"
    "Reply as JSON with exactly these fields:\n"
    "  headline: one sentence of at most 20 words that sums up how the child is doing.\n"
    f"  insights: 3 to {MAX_INSIGHTS} short sentences. Each states one finding from the data and what it means.\n"
    f"  suggestions: 2 to {MAX_SUGGESTIONS} concrete things a parent can do at home this week."
)

RESPONSE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "headline": {"type": "STRING"},
        "insights": {"type": "ARRAY", "items": {"type": "STRING"}},
        "suggestions": {"type": "ARRAY", "items": {"type": "STRING"}},
    },
    "required": ["headline", "insights", "suggestions"],
}


# --------------------------------------------------------------------------- what is sent
def build_payload(child: dict, days: int) -> dict:
    """The allow-listed facts about one child. Reuses the parent assistant's read-only tools,
    so the AI insights can never see more than the assistant can."""
    d = max(1, min(int(days), MAX_DAYS))
    payload = {
        "period_days": d,
        "overview": assistant.tool_get_overview(child, {}),
        "topics": assistant.tool_get_topic_details(child, {"days": d}),
        "trends": assistant.tool_get_trends(child, {"days": d}),
        "games": assistant.tool_get_games(child, {"days": d}),
    }
    quiz_summary = quizzes.insight_summary(child["id"], d)      # topics and percentages only, never question text
    if quiz_summary:
        payload["quizzes"] = quiz_summary
    if _flag("TUTOR_INSIGHTS_SCHOOL_RECORDS", True) and payload["overview"].get("school_records_available"):
        payload["school_records"] = assistant.tool_get_school_records(child, {})
    return payload


def has_something_to_say(payload: dict) -> bool:
    """No practice, no games and no school records: nothing for Gemini to base an answer on."""
    return bool(payload["topics"]["topics"] or payload["games"]["total_sessions"]
                or payload.get("school_records") or payload.get("quizzes"))


# --------------------------------------------------------------------------- calling Gemini
def _client_factory() -> httpx.AsyncClient:
    """One place to build the HTTP client (tests replace this with a fake transport)."""
    return httpx.AsyncClient(timeout=httpx.Timeout(connect=10.0, read=45.0, write=10.0, pool=10.0))


_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.I)


def parse_json(text: str) -> dict:
    data = json.loads(_FENCE.sub("", text.strip()))
    if not isinstance(data, dict):
        raise GeminiError("Gemini did not return a JSON object")
    return data


async def call_gemini(user_text: str) -> dict:
    """Send one request and return the parsed JSON answer. Raises httpx errors or GeminiError."""
    key = api_key()
    if not key:
        raise GeminiError("GEMINI_API_KEY is not set")
    url = f"{_env('GEMINI_BASE_URL', DEFAULT_BASE_URL).rstrip('/')}/models/{model_name()}:generateContent"
    body = {
        "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": [{"role": "user", "parts": [{"text": user_text}]}],
        "generationConfig": {
            "temperature": 0.4,
            "maxOutputTokens": 2048,
            "responseMimeType": "application/json",
            "responseSchema": RESPONSE_SCHEMA,
        },
    }
    async with _client_factory() as client:
        resp = await client.post(url, json=body, headers={"x-goog-api-key": key})
    resp.raise_for_status()
    data = resp.json()

    candidates = data.get("candidates") or []
    if not candidates:
        reason = (data.get("promptFeedback") or {}).get("blockReason", "no answer returned")
        raise GeminiError(f"Gemini gave no answer ({reason})")
    candidate = candidates[0]
    finish = candidate.get("finishReason")
    if finish not in (None, "STOP"):
        raise GeminiError(f"Gemini stopped early ({finish})")
    parts = (candidate.get("content") or {}).get("parts") or []
    text = "".join(p.get("text", "") for p in parts if isinstance(p, dict) and not p.get("thought"))
    if not text.strip():
        raise GeminiError("Gemini returned an empty answer")
    return parse_json(text)


# --------------------------------------------------------------------------- checking the answer
_MARKDOWN = re.compile(r"[*_`#>]+")
_BULLET = re.compile(r"^\s*(?:[-•–]|\d+[.)])\s+")
_PERCENT = re.compile(r"(\d+(?:\.\d+)?)\s*%")
_NUMBER = re.compile(r"\d+(?:\.\d+)?")


def _tidy(line, restore) -> str:
    if not isinstance(line, str):
        return ""
    text = _BULLET.sub("", " ".join(restore(line).split()))
    text = _MARKDOWN.sub("", text).strip()
    return text[:MAX_LINE].rstrip()


def _grounded(line: str, known: list[float]) -> bool:
    """Every percentage a line quotes must be (nearly) one of the numbers we sent.
    Catches the model inventing a figure. Rounding to a whole number is allowed."""
    return all(any(abs(float(p) - k) <= 0.5 for k in known) for p in _PERCENT.findall(line))


def clean_result(raw: dict, payload: dict, restore) -> dict | None:
    """Turn Gemini's JSON into the shape the report uses, or None if it is not good enough."""
    known = [float(n) for n in _NUMBER.findall(json.dumps(payload))]
    insights = []
    for line in raw.get("insights") if isinstance(raw.get("insights"), list) else []:
        text = _tidy(line, restore)
        if text and _grounded(text, known):
            insights.append(text)
        elif text:
            log.warning("Dropped an AI insight that quoted a figure not in the data: %r", text[:80])
    if len(insights) < MIN_INSIGHTS:
        return None
    suggestions = [t for t in (_tidy(s, restore) for s in
                               (raw.get("suggestions") if isinstance(raw.get("suggestions"), list) else [])) if t]
    return {
        "headline": _tidy(raw.get("headline"), restore)[:200],
        "insights": insights[:MAX_INSIGHTS],
        "suggestions": suggestions[:MAX_SUGGESTIONS],
    }


# --------------------------------------------------------------------------- caching (cost + rate limits)
_cache: dict[tuple[int, int], dict] = {}


def clear_cache() -> None:
    _cache.clear()


def _cache_get(key: tuple[int, int], digest: str):
    entry = _cache.get(key)
    if not entry:
        return None
    age = time.monotonic() - entry["at"]
    if age < int(_env("TUTOR_INSIGHTS_MIN_SECONDS", "300")):
        return entry["result"]                                   # asked very recently: reuse
    if entry["digest"] == digest and age < int(_env("TUTOR_INSIGHTS_CACHE_MINUTES", "360")) * 60:
        return entry["result"]                                   # data has not changed: reuse
    return None


# --------------------------------------------------------------------------- the entry point
async def generate(child: dict, days: int) -> dict | None:
    """AI insights for one child, or None when the caller should use the template insights
    (not configured, nothing to summarise, or Gemini failed). Never raises for Gemini problems."""
    if not enabled():
        return None
    payload = build_payload(child, days)
    if not has_something_to_say(payload):
        return None

    key = (child["id"], payload["period_days"])
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    cached = _cache_get(key, digest)
    if cached:
        return cached

    if _flag("TUTOR_INSIGHTS_REDACT", True):
        redactor = assistant.Redactor(child)
        text, restore = redactor.out(json.dumps(payload, ensure_ascii=False)), redactor.back
    else:
        text, restore = json.dumps(payload, ensure_ascii=False), (lambda s: s)

    try:
        raw = await call_gemini("Progress data for the child (JSON):\n" + text)
        result = clean_result(raw, payload, restore)
    except (httpx.HTTPError, GeminiError, ValueError) as e:      # ValueError covers bad JSON
        log.warning("Gemini insights failed, using the template insights instead: %s", assistant.describe_error(e))
        return None
    if result is None:
        log.warning("Gemini insights were not usable, using the template insights instead.")
        return None

    result = {**result, "model": model_name(), "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    _cache[key] = {"at": time.monotonic(), "digest": digest, "result": result}
    return result
