"""Parent assistant: an LLM that can only READ a child's progress, through a few fixed functions.

How it works
  1. The server decides WHICH child (checked against the parent's links). The model never
     chooses a child, so it cannot reach anyone else's data.
  2. Every tool returns a hand-picked set of fields (an allowlist). Nothing the child typed to
     the tutor is reachable, and nothing derived from it either: no question counts, no
     "asking often" topics, no last-asked times.
  3. A snapshot (`get_overview`) is loaded up front, as if the model had already called it.
     Small models are unreliable at deciding to call tools; this keeps answers grounded.
     The model can still call more tools for detail.
  4. No tool writes anything. The assistant cannot change data or contact anyone.
"""
import json
import logging
import os
import re
from typing import Awaitable, Callable

from . import db, progress, quizzes
from .config import settings
from .school_records import school_records_for

MAX_ROUNDS = 4              # how many tool-calling rounds before we force an answer
MAX_CALLS_PER_ROUND = 3
MAX_HISTORY = 6             # earlier messages of this conversation sent along
MAX_TOPIC_ROWS = 25

ChatFn = Callable[[list[dict], "list[dict] | None"], Awaitable[dict]]

log = logging.getLogger("uvicorn.error")      # shows up in the window that runs the API


class ToolsUnsupported(Exception):
    """The configured model cannot do tool calling."""


class AssistantUnavailable(Exception):
    """Every model that was tried failed. The message says why (never contains the API key)."""


class ConfigError(Exception):
    """The online AI provider is selected but not fully configured (base URL, key or model missing)."""


def describe_error(e: Exception) -> str:
    """A short, key-free reason for a failed model call, for the API window and for debugging."""
    response = getattr(e, "response", None)
    if response is not None:
        try:
            body = " ".join(str(response.text).split())[:200]
        except Exception:                      # noqa: BLE001
            body = ""
        return f"HTTP {response.status_code}" + (f": {body}" if body else "")
    return f"{type(e).__name__}: {e}"[:200]


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _flag(name: str, default: bool) -> bool:
    value = _env(name)
    return default if not value else value.lower() not in ("0", "false", "no", "off")


# --------------------------------------------------------------------------- prompt
def system_prompt(name: str, snapshot: dict | None = None) -> str:
    text = (
        f"You are Zaki, a warm and practical assistant for a parent whose child, {name}, goes to school "
        "and uses the Zaki learning device.\n\n"
        "How to answer:\n"
        "- Answer the parent's question first, in your first sentence, then give the detail it needs.\n"
        "- Match the length to the question. A simple factual question gets a short answer (1 to 3 sentences). "
        "A request to explain, advise, plan, compare or 'tell me about' something deserves a complete, well-organised "
        "answer like a thoughtful assistant would give: several paragraphs or a list, with reasons and examples. "
        "Never stop after one sentence when the parent clearly wants more.\n"
        "- Backend tools are internal. Never reveal tool names, function names, JSON arguments, API requests, "
        "commands, or implementation details to the parent.\n"
        "- Never instruct the parent to execute backend functions or commands manually.\n"
        "- If information requires a backend tool, request it through the available tool-calling mechanism. "
        "Wait for the backend to execute the tool and use its returned data to formulate the answer.\n"
        "- Never fabricate tool results. If a tool fails or its information is unavailable, explain the limitation naturally.\n"
        "- Present the results of backend operations as normal, helpful explanations without mentioning internal functions.\n"
        f"- Do NOT open with a summary of {name}'s performance unless the parent asks how {name} is doing. "
        "Never recite all the data. Mention only the facts that matter to this question.\n"
        f"- If the question has nothing to do with {name} (general knowledge, how something works, parenting or study "
        f"tips), just answer it normally and do not bring up {name}'s data. You may end with one short, relevant tip "
        "only if it really helps.\n"
        "- When you do talk about the child, use ONLY facts from the data. Never invent scores, grades, dates, "
        "teachers or events. Quote numbers exactly as given. If something is not in the data, say you do not have it.\n"
        f"- You can read progress data, but you can NOT see what {name} types to the Zaki tutor. "
        "Those conversations are private. If asked, say so politely.\n"
        "- You cannot change anything or contact anyone.\n"
        "- When the parent asks what to do, give concrete steps they can take at home and say why each helps.\n"
        "- RESPONSE FORMATTING AND PRESENTATION:\n"
        "  - Use Markdown formatting to make every response clear, structured, and visually appealing.\n"
        "  - Use **bold headings** for major sections and subheadings where appropriate.\n"
        "  - Use numbered lists for sequential instructions, procedures, and steps.\n"
        "  - Use bullet points for recommendations, explanations, and collections of facts.\n"
        "  - Use tables when comparing information, presenting structured data, or displaying grades and results.\n"
        "  - Use bold text to highlight important concepts, key results, warnings, and conclusions.\n"
        "  - Use horizontal separators only when they improve readability.\n"
        "  - Use properly formatted mathematical notation for equations and calculations.\n"
        "  - Avoid long, uninterrupted paragraphs. Break explanations into logical sections.\n"
        "  - Ensure responses are readable on mobile screens.\n"
        "  - Do not force headings into simple factual answers. Use formatting proportionate to the question.\n"
        "  - Never return plain, unformatted blocks of text when structured formatting would improve readability.\n"
        f"- Grades come from quizzes {name} took on the Zaki device."
        "For quiz scores, weak topics and mistakes, use the quiz tools.\n"
        "- Formatting is important: responses must be readable, organised and visually structured. Use Markdown headings (## or ###), bullet points, numbered lists, bold text for important concepts, and tables when appropriate.\n"
        "- For educational explanations, organise content into sections such as Explanation, Examples, and Practice where appropriate.\n"
        "- For step-by-step instructions, number each step clearly.\n"
        "- Never sacrifice clarity or completeness for brevity when the parent asks for a detailed explanation.\n"
    )
    if snapshot is not None:
        text += (
            f"\n\nBackground data about {name} (JSON). Use it only if the question is about {name}. "
            "Call a tool only when you need more detail (one subject's topics, trends, games, or school records):\n"

            + json.dumps(snapshot, ensure_ascii=False)
        )
    else:
        text += (
            f"\n\nNo data about {name} is loaded for this question. If the parent asks about {name}'s progress, "
            "grades, games or school, call a tool to look it up first."
        )
    return text


# Words that show a question is about the child. Anything else is answered as a general question,
# without loading the child's data, so a small model has nothing to summarise.
_ABOUT_CHILD = re.compile(
    r"\b(?:my\s+(?:child|son|daughter|kid|boy|girl|learner|student)|he|she|him|his|her|hers|"
    r"grades?|marks?|scores?|quiz(?:zes)?|tests?|exams?|results?|progress|practice|practising|practicing|streak|"
    r"struggl\w*|weakness(?:es)?|weak|strengths?|strong|improv\w*|declin\w*|dropp\w*|games?|"
    r"attendance|absen\w*|school|teachers?|homework|assignments?|report|gpa|rank|mistakes?|zaki)\b", re.I)


def is_about_child(question: str, history: list[dict], child: dict) -> bool:
    """True when the question needs the child's data. Short follow-ups ("why?", "and in maths?") count
    only if the previous answer was about the child."""
    if re.search(rf"(?<!\w){re.escape(child['username'])}(?!\w)", question, re.I) or _ABOUT_CHILD.search(question):
        return True
    if len(question.split()) <= 5 and history:
        last = next((h["content"] for h in reversed(history) if h["role"] == "assistant"), "")
        return bool(re.search(rf"(?<!\w){re.escape(child['username'])}(?!\w)|%", last, re.I))
    return False


# --------------------------------------------------------------------------- tools
def _fn(name: str, description: str, properties: dict | None = None) -> dict:
    return {"type": "function", "function": {
        "name": name, "description": description,
        "parameters": {"type": "object", "properties": properties or {}, "required": []},
    }}


_DAYS = lambda default: {"type": "integer", "description": f"How many recent days to cover, 1 to 90. Default {default}."}  # noqa: E731

TOOLS: list[dict] = [
    _fn("get_overview",
        "Snapshot: learning streak, accuracy per subject, topics needing help or going well, "
        "recent improvements and declines, and game usage."),
    _fn("get_topic_details",
        "Practice results per topic: accuracy, practice questions, lessons viewed, status. "
        "Use for questions about one subject or topic.",
        {"subject": {"type": "string", "description": "Optional subject filter, e.g. Mathematics, English, Biology"},
         "days": _DAYS(28)}),
    _fn("get_trends",
        "Which topics and subjects improved or declined compared with the previous period of the same length.",
        {"days": _DAYS(14)}),
    _fn("get_games",
        "Which games the child played, how often and for how long, with wins and losses.",
        {"days": _DAYS(30)}),
    _fn("get_school_records",
        "Information from the SCHOOL: GPA, attendance, class rank, grades the school recorded, upcoming "
        "assignments, teacher comments and school events. Not the quizzes done on the Zaki device."),
    _fn("get_quizzes",
        "Quizzes the child took on the Zaki device: the score of each recent quiz, the average per subject and how it "
        "changed since the previous period, and the weak and strong topics found from the questions. Use for any "
        "question about quiz results, scores over time, improving or dropping in a subject, or weak topics.",
        {"subject": {"type": "string", "description": "Optional subject filter, e.g. Mathematics, Biology"},
         "days": {"type": "integer", "description": "How many recent days to cover, 1 to 365. Default 30. Use 365 for 'all year'."}}),
    _fn("get_quiz_mistakes",
        "The actual quiz questions the child got wrong: the question, the right answer and what the child answered. "
        "Use when the parent asks what mistakes the child makes, which questions they missed, or why they lose marks "
        "in a topic.",
        {"topic": {"type": "string", "description": "Optional topic filter, e.g. Cell Biology, Fractions"},
         "subject": {"type": "string", "description": "Optional subject filter"},
         "days": {"type": "integer", "description": "How many recent days to cover, 1 to 365. Default 60."}}),
]
TOOL_NAMES = {t["function"]["name"] for t in TOOLS}


def _days(args: dict, default: int) -> int:
    try:
        value = int(args.get("days", default))
    except (TypeError, ValueError):
        value = default
    return max(1, min(90, value))


# Statuses derived from the child's chat questions are hidden from the assistant.
_STATUS_HIDDEN = {"asking_often": "not_enough_data"}


def tool_get_overview(child: dict, args: dict) -> dict:
    cid = child["id"]
    topics = progress.topics_report(cid, 28)
    trends = progress.trends_report(cid, 14)
    games = progress.games_report(cid, 30)
    return {
        "child": child["username"],
        "streak_days": progress.compute_streak(db.active_dates(cid), progress.local_today()),
        "accuracy_by_subject_last_28_days": [
            {"subject": s["subject"], "accuracy_percent": s["accuracy_percent"],
             "practice_questions": s["practice_questions"]}
            for s in topics["subjects"]
        ],
        "topics_needing_help": topics["needs_help"],
        "topics_going_well": topics["doing_well"],
        "improved_vs_previous_14_days": trends["improved"],
        "declined_vs_previous_14_days": trends["declined"],
        "games_last_30_days": {"favourite": games["favourite_game"], "sessions": games["total_sessions"],
                               "minutes": games["total_minutes"]},
        "school_records_available": school_records_for(child["username"]) is not None,
        **_quiz_overview(cid),
    }


def _quiz_overview(child_id: int) -> dict:
    """A few quiz facts for the snapshot, only when the child has taken quizzes. Details come from get_quizzes."""
    summary = quizzes.assistant_summary(child_id, 30)
    if not summary["quizzes_taken"]:
        return {}
    return {"quizzes_last_30_days": {
        "taken": summary["quizzes_taken"], "average_percent": summary["average_percent"],
        "weak_topics": [f"{w['topic']} ({w['accuracy_percent']:g}%)" for w in summary["weak_topics"][:3]],
        "more_detail_with_tools": "get_quizzes, get_quiz_mistakes",
    }}


def tool_get_topic_details(child: dict, args: dict) -> dict:
    days = _days(args, 28)
    wanted = str(args.get("subject") or "").strip().lower()
    report = progress.topics_report(child["id"], days)
    rows = [r for r in report["topics"] if not wanted or r["subject"].lower() == wanted]
    return {
        "period_days": days,
        "subject_filter": wanted or None,
        "topics": [{
            "topic": r["name"], "subject": r["subject"],
            "status": _STATUS_HIDDEN.get(r["status"], r["status"]),
            "accuracy_percent": r["accuracy_percent"],
            "practice_questions": r["practice_questions"],
            "practice_sessions": r["practice_sessions"],
            "lessons_viewed": r["lessons_viewed"],
        } for r in rows[:MAX_TOPIC_ROWS]],
    }


def tool_get_trends(child: dict, args: dict) -> dict:
    days = _days(args, 14)
    t = progress.trends_report(child["id"], days)
    keep = lambda r: {  # noqa: E731
        "accuracy_now": r["accuracy_now"], "accuracy_before": r["accuracy_before"],
        "change_points": r["change_points"], "performance": r["performance"],
    }
    return {
        "period_days": days, "compared_with": t["compared_with"],
        "improved": t["improved"], "declined": t["declined"],
        "subjects": [{"subject": r["subject"], **keep(r)} for r in t["subjects"]],
        "topics": [{"topic": r["name"], "subject": r["subject"], **keep(r)}
                   for r in t["topics"] if r["performance"] != "insufficient_data"][:MAX_TOPIC_ROWS],
    }


def tool_get_games(child: dict, args: dict) -> dict:
    days = _days(args, 30)
    g = progress.games_report(child["id"], days)
    return {
        "period_days": days, "total_sessions": g["total_sessions"], "total_minutes": g["total_minutes"],
        "days_played": g["days_played"], "favourite_game": g["favourite_game"],
        "games": [{"game": r["name"], "sessions": r["sessions"], "minutes": r["minutes"],
                   "wins": r["wins"], "losses": r["losses"], "draws": r["draws"]} for r in g["games"]],
    }


def _long_days(args: dict, default: int) -> int:
    try:
        value = int(args.get("days", default))
    except (TypeError, ValueError):
        value = default
    return max(1, min(365, value))


def tool_get_quizzes(child: dict, args: dict) -> dict:
    return quizzes.assistant_summary(child["id"], _long_days(args, 30), str(args.get("subject") or "") or None)


def tool_get_quiz_mistakes(child: dict, args: dict) -> dict:
    return quizzes.assistant_mistakes(child["id"], _long_days(args, 60), str(args.get("topic") or "") or None,
                                      str(args.get("subject") or "") or None)


def tool_get_school_records(child: dict, args: dict) -> dict:
    records = school_records_for(child["username"])
    return records if records is not None else {"available": False, "note": "No school records for this child."}


_EXECUTORS = {
    "get_overview": tool_get_overview,
    "get_topic_details": tool_get_topic_details,
    "get_trends": tool_get_trends,
    "get_games": tool_get_games,
    "get_school_records": tool_get_school_records,
    "get_quizzes": tool_get_quizzes,
    "get_quiz_mistakes": tool_get_quiz_mistakes,
}


def execute_tool(child: dict, name: str, args: dict) -> dict:
    fn = _EXECUTORS.get(name)
    if fn is None:
        return {"error": f"Unknown tool '{name}'. Available: {', '.join(sorted(TOOL_NAMES))}."}
    return fn(child, args)


# --------------------------------------------------------------------------- reading the model's reply

# ---------------------------------------------------------------------------
# Reading and validating the model's reply

_INLINE = re.compile(
    r"<tool_call>\s*(\{.*?\})\s*</tool_call>",
    re.S | re.I,
)

_TOOL_JSON = re.compile(
    r'\{\s*"name"\s*:\s*"([a-zA-Z_][a-zA-Z0-9_]*)"\s*,'
    r'\s*"arguments"\s*:\s*(\{.*?\})\s*\}',
    re.S,
)

_TOOL_LEAK_PATTERNS = [
    re.compile(r"<tool_call\b.*?</tool_call>", re.I | re.S),
    re.compile(
        r"(?im)^\s*(?:run|execute|call)\s+(?:the\s+)?"
        r"(?:following\s+)?(?:command|function|tool)\b"
    ),
    re.compile(
        r"(?im)^\s*(?:json|javascript|python)\s*$"
    ),
    re.compile(
        r'(?im)^\s*\{\s*"name"\s*:\s*"'
        r'[a-zA-Z_][a-zA-Z0-9_]*"\s*,\s*"arguments"\s*:\s*\{'
    ),
]


def _as_args(raw) -> dict:
    if isinstance(raw, dict):
        return raw

    if isinstance(raw, str):
        try:
            value = json.loads(raw)
        except (ValueError, TypeError):
            return {}

        return value if isinstance(value, dict) else {}

    return {}


def calls_from(msg: dict) -> list[tuple[str, dict]]:
    """Extract valid tool calls from structured or text-based model output."""

    calls: list[tuple[str, dict]] = []

    # 1. Proper structured tool calls.
    for c in msg.get("tool_calls") or []:
        fn = (c or {}).get("function") or {}
        name = fn.get("name")

        if isinstance(name, str) and name in TOOL_NAMES:
            calls.append((name, _as_args(fn.get("arguments"))))

    content = msg.get("content") or ""

    # 2. Tool calls enclosed in <tool_call> tags.
    for match in _INLINE.finditer(content):
        try:
            data = json.loads(match.group(1))
        except (ValueError, TypeError):
            continue

        name = data.get("name") if isinstance(data, dict) else None

        if isinstance(name, str) and name in TOOL_NAMES:
            calls.append((name, _as_args(data.get("arguments"))))

    # 3. Bare JSON tool calls sometimes generated by smaller models.
    for match in _TOOL_JSON.finditer(content):
        name = match.group(1)

        if name not in TOOL_NAMES:
            continue

        try:
            args = json.loads(match.group(2))
        except (ValueError, TypeError):
            continue

        if isinstance(args, dict):
            calls.append((name, args))

    # Remove duplicate calls while preserving order.
    unique = []
    seen = set()

    for name, args in calls:
        key = (name, json.dumps(args, sort_keys=True))

        if key not in seen:
            seen.add(key)
            unique.append((name, args))

    return unique[:MAX_CALLS_PER_ROUND]


def contains_tool_leak(text: str) -> bool:
    """Detect internal tool instructions accidentally included in a response."""

    if not text:
        return False

    # Known tool names appearing inside JSON function-call syntax.
    for name in TOOL_NAMES:
        if re.search(
            rf'"name"\s*:\s*"{re.escape(name)}"',
            text,
            re.I,
        ):
            return True

    return any(pattern.search(text) for pattern in _TOOL_LEAK_PATTERNS)


def plain_text(text: str) -> str:
    """Remove internal tool-call syntax while preserving Markdown."""

    text = text or ""

    # Remove explicit tool-call blocks.
    text = _INLINE.sub("", text)

    # Preserve Markdown headings, bold, lists, tables and equations.
    return text.strip()


def clean_history(history: list[dict]) -> list[dict]:
    out = []

    for item in history[-MAX_HISTORY:]:
        role = item.get("role")
        content = item.get("content")

        if (
            role in ("user", "assistant")
            and isinstance(content, str)
            and content.strip()
        ):
            # Never carry leaked tool instructions into future conversations.
            if contains_tool_leak(content):
                continue

            out.append({
                "role": role,
                "content": content.strip()[:1500],
            })

    return out


def _tool_message(name: str, result: dict) -> dict:
    return {
        "role": "tool",
        "tool_name": name,
        "content": json.dumps(result, ensure_ascii=False),
    }


# ---------------------------------------------------------------------------
# The assistant loop

async def run_assistant(
    child: dict,
    question: str,
    history: list[dict],
    chat: ChatFn,
) -> dict:
    """Answer one parent question using safe, controlled backend tools."""

    if getattr(chat, "external", False) and _flag(
        "TUTOR_ASSISTANT_REDACT", True
    ):
        chat = _redacting(chat, child)

    history = clean_history(history)
    used: list[str] = []
    snapshot = None

    if is_about_child(question, history, child):
        used.append("get_overview")
        snapshot = execute_tool(child, "get_overview", {})

    messages: list[dict] = [{
        "role": "system",
        "content": system_prompt(child["username"], snapshot),
    }]

    messages += history
    messages.append({
        "role": "user",
        "content": question.strip(),
    })

    tools: list[dict] | None = TOOLS

    for _ in range(MAX_ROUNDS):
        try:
            reply = await chat(messages, tools)

        except ToolsUnsupported:
            # Model does not support tool calling.
            tools = None
            reply = await chat(messages, None)

        calls = calls_from(reply) if tools else []

        # Execute actual tool calls.
        if calls:
            messages.append({
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "function": {
                            "name": name,
                            "arguments": args,
                        }
                    }
                    for name, args in calls
                ],
            })

            for name, args in calls:
                if name not in TOOL_NAMES:
                    continue

                if name not in used:
                    used.append(name)

                result = execute_tool(child, name, args)

                messages.append(_tool_message(name, result))

            continue

        # No tool calls: inspect the answer for leaked commands.
        answer = reply.get("content") or ""

        if not contains_tool_leak(answer):
            return _finish(reply, used)

        log.warning(
            "Model generated malformed tool instructions. Retrying."
        )

        # Give the model one opportunity to correct itself.
        messages.append({
            "role": "assistant",
            "content": answer,
        })

        messages.append({
            "role": "user",
            "content": (
                "Your previous response contained internal backend "
                "instructions instead of a proper answer. "
                "Do not display function names, JSON arguments, "
                "commands, or implementation details. "
                "If you need data, use the available tools properly. "
                "Otherwise, answer the parent's question naturally "
                "using the information already available."
            ),
        })

        try:
            retry = await chat(messages, tools)
        except ToolsUnsupported:
            retry = await chat(messages, None)

        retry_calls = calls_from(retry) if tools else []

        # If retry produces actual tool calls, execute them.
        if retry_calls:
            messages.append({
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "function": {
                            "name": name,
                            "arguments": args,
                        }
                    }
                    for name, args in retry_calls
                ],
            })

            for name, args in retry_calls:
                if name not in TOOL_NAMES:
                    continue

                if name not in used:
                    used.append(name)

                messages.append(
                    _tool_message(
                        name,
                        execute_tool(child, name, args),
                    )
                )

            # Force a final natural-language answer.
            retry = await chat(messages, None)

        return _finish(retry, used)

    # Too many tool rounds: request a final natural-language answer.
    messages.append({
        "role": "user",
        "content": (
            "Now answer the parent's question using the data "
            "you have. Do not display internal tool instructions."
        ),
    })

    final_reply = await chat(messages, None)

    return _finish(final_reply, used)


def _finish(reply: dict, used: list[str]) -> dict:
    """Final response validation before returning to the frontend."""

    answer = plain_text(reply.get("content") or "")

    if contains_tool_leak(answer):
        log.warning(
            "Blocked final response containing internal tool instructions."
        )

        answer = (
            "I encountered a problem preparing your answer. "
            "Please try asking your question again."
        )

    if not answer:
        answer = (
            "I could not put an answer together just now. "
            "Please try asking again."
        )

    return {
        "answer": answer,
        "tools_used": used,
    }

# --------------------------------------------------------------------------- keeping names off the internet
_TITLE = re.compile(r"^(?:Mr|Mrs|Ms|Miss|Dr|Prof)\.?\s+", re.I)
_SCHOOL_TAIL = re.compile(r"\s+(?:High School|Secondary School|Primary School|Junior School|School|Academy|College)$", re.I)


class Redactor:
    """Swaps the child's name, school and teachers for placeholders before a message is sent to an
    ONLINE model, and swaps them back in the answer. Short forms are caught too ("St. Mary's",
    "Davis"). This is pseudonymisation, not anonymisation: grades and other figures still go out,
    and any other personal detail a parent types is sent as typed."""

    def __init__(self, child: dict):
        self.child_name = child["username"]
        self._child_re = re.compile(rf"(?<!\w){re.escape(self.child_name)}(?!\w)", re.I)
        self.rules: list[tuple[re.Pattern, str]] = []     # (what to find, placeholder)
        self.restore: dict[str, str] = {}                  # placeholder -> real text

        record = school_records_for(child["username"]) or {}
        if record.get("school"):
            full = record["school"]
            short = _SCHOOL_TAIL.sub("", full)
            self._add(full, [full] + ([short] if short != full and len(short) >= 4 else []), "[SCHOOL]")
        for i, teacher in enumerate(dict.fromkeys((record.get("teachers") or {}).values()), 1):
            surname = _TITLE.sub("", teacher)
            self._add(teacher, [teacher] + ([surname] if surname != teacher and len(surname) >= 3 else []),
                      f"[TEACHER_{i}]")

    def _add(self, real: str, aliases: list[str], token: str) -> None:
        self.restore[token] = real
        for alias in sorted(set(aliases), key=len, reverse=True):      # longest first
            self.rules.append((re.compile(rf"(?<!\w){re.escape(alias)}(?!\w)", re.I), token))

    def out(self, text: str) -> str:
        for pattern, token in self.rules:
            text = pattern.sub(token, text)
        return self._child_re.sub("[CHILD]", text)

    def back(self, text: str) -> str:
        text = re.sub(r"\[child\]", lambda _: self.child_name, text, flags=re.I)
        for token, real in self.restore.items():
            text = re.sub(re.escape(token), lambda _, r=real: r, text, flags=re.I)
        return text

    def scrub_message(self, message: dict) -> dict:
        clean = dict(message)
        if isinstance(clean.get("content"), str):
            clean["content"] = self.out(clean["content"])
        return clean


def _redacting(chat: ChatFn, child: dict) -> ChatFn:
    redactor = Redactor(child)

    async def wrapped(messages: list[dict], tools: "list[dict] | None") -> dict:
        reply = await chat([redactor.scrub_message(m) for m in messages], tools)
        return {**reply, "content": redactor.back(reply.get("content") or "")}

    return wrapped


# --------------------------------------------------------------------------- the models
async def ollama_chat(messages: list[dict], tools: list[dict] | None) -> dict:
    """The local model. Uses OLLAMA_MODEL (for example your custom 'zaki-tutor') unless
    TUTOR_ASSISTANT_OLLAMA_MODEL names a different local model just for parents."""
    import httpx  # imported here so the rest of this module works without it (tests)

    payload: dict = {"model": _env("TUTOR_ASSISTANT_OLLAMA_MODEL") or settings.model,
                     "messages": messages, "stream": False,
               "options": {"temperature": 0.3, "num_ctx": int(_env("TUTOR_ASSISTANT_NUM_CTX", "8192") or 8192)}}
    if tools:
        payload["tools"] = tools
    timeout = httpx.Timeout(connect=5.0, read=300.0, write=10.0, pool=5.0)  # Pi inference is slow
    async with httpx.AsyncClient(base_url=settings.ollama_url, timeout=timeout) as client:
        resp = await client.post("/api/chat", json=payload)
    if resp.status_code == 400 and tools and "tool" in resp.text.lower():
        raise ToolsUnsupported(resp.text[:200])
    resp.raise_for_status()
    return resp.json().get("message", {})


def to_openai_messages(messages: list[dict]) -> list[dict]:
    """Our messages use Ollama's shape (arguments as a dict). OpenAI-style APIs want call ids,
    arguments as a JSON string, and each tool result tied to its call id."""
    out: list[dict] = []
    pending: list[str] = []
    counter = 0
    for m in messages:
        role = m["role"]
        if role == "assistant" and m.get("tool_calls"):
            calls, pending = [], []
            for c in m["tool_calls"]:
                counter += 1
                call_id = f"call_{counter}"
                pending.append(call_id)
                fn = c["function"]
                calls.append({"id": call_id, "type": "function",
                              "function": {"name": fn["name"], "arguments": json.dumps(fn.get("arguments") or {})}})
            out.append({"role": "assistant", "content": m.get("content") or None, "tool_calls": calls})
        elif role == "tool":
            out.append({"role": "tool", "tool_call_id": pending.pop(0) if pending else f"call_{counter}",
                        "content": m.get("content", "")})
        else:
            out.append({"role": role, "content": m.get("content", "")})
    return out


def from_openai_message(msg: dict) -> dict:
    reply: dict = {"role": "assistant", "content": msg.get("content") or ""}
    calls = []
    for c in msg.get("tool_calls") or []:
        fn = (c or {}).get("function") or {}
        if isinstance(fn.get("name"), str):
            calls.append({"function": {"name": fn["name"], "arguments": _as_args(fn.get("arguments"))}})
    if calls:
        reply["tool_calls"] = calls
    return reply


async def openai_chat(messages: list[dict], tools: list[dict] | None) -> dict:
    """Any OpenAI-compatible online API: Groq, Google Gemini, OpenRouter, Mistral, Cerebras and others."""
    import httpx

    base, key, model = _env("TUTOR_ASSISTANT_BASE_URL"), _env("TUTOR_ASSISTANT_API_KEY"), _env("TUTOR_ASSISTANT_MODEL")
    if not (base and key and model):
        raise ConfigError("Set TUTOR_ASSISTANT_BASE_URL, TUTOR_ASSISTANT_API_KEY and TUTOR_ASSISTANT_MODEL.")

    payload: dict = {"model": model, "messages": to_openai_messages(messages), "temperature": 0.3}
    if tools:
        payload["tools"] = tools
    timeout = httpx.Timeout(connect=10.0, read=60.0, write=10.0, pool=10.0)
    async with httpx.AsyncClient(base_url=base.rstrip("/") + "/", timeout=timeout) as client:
        resp = await client.post("chat/completions", json=payload, headers={"Authorization": f"Bearer {key}"})
    if resp.status_code in (400, 404, 422) and tools and "tool" in resp.text.lower():
        raise ToolsUnsupported(resp.text[:200])
    resp.raise_for_status()
    return from_openai_message(resp.json()["choices"][0]["message"])


openai_chat.external = True      # data leaves this machine: names are replaced first (see Redactor)


def build_chat() -> ChatFn:
    """Pick the model from the environment. Default: the local Ollama model."""
    if _env("TUTOR_ASSISTANT_PROVIDER", "ollama").lower() != "openai":
        return ollama_chat
    if not _flag("TUTOR_ASSISTANT_FALLBACK", True):
        return openai_chat

    async def online_then_local(messages: list[dict], tools: "list[dict] | None") -> dict:
        import httpx
        try:
            return await openai_chat(messages, tools)
        except httpx.HTTPError as online_error:   # no internet, rate limited, bad key or model, provider down
            reason = describe_error(online_error)
            log.warning("Online AI service failed (%s). Trying the local model instead.", reason)
            try:
                return await ollama_chat(messages, tools)
            except httpx.HTTPError as local_error:
                raise AssistantUnavailable(
                    f"online service: {reason}; local model: {describe_error(local_error)}") from local_error

    online_then_local.external = True
    return online_then_local
