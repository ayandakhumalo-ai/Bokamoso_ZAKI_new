"""AI insights from Gemini. No real Gemini is called: its HTTP side is replaced with a fake transport."""
import asyncio
import json

import httpx
import pytest

from app import db, gemini_insights
from app.main import app, get_insight_writer
from tests.test_insights import family, practice  # noqa: F401  (family is a fixture)

KEY = "test-key-NOT-REAL-123"


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for name in ("GEMINI_API_KEY", "TUTOR_GEMINI_API_KEY", "GEMINI_MODEL", "GEMINI_BASE_URL", "TUTOR_INSIGHTS_AI",
                 "TUTOR_INSIGHTS_REDACT", "TUTOR_INSIGHTS_SCHOOL_RECORDS"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("TUTOR_INSIGHTS_MIN_SECONDS", "0")     # tests control caching themselves
    gemini_insights.clear_cache()
    yield
    gemini_insights.clear_cache()


@pytest.fixture
def with_data(family):                                         # noqa: F811
    sid, parent, student = family
    practice(sid, "fractions", 10, 3, days_ago=3)              # 30%: needs help
    practice(sid, "hcf", 10, 9, days_ago=2)                    # 90%: going well
    return sid, parent, student


def gemini_reply(payload: dict, finish="STOP") -> dict:
    return {"candidates": [{"finishReason": finish, "content": {"parts": [{"text": json.dumps(payload)}]}}]}


GOOD = {
    "headline": "[CHILD] is strong in HCF but needs help with fractions.",
    "insights": [
        "[CHILD] got 30% correct on fractions over 10 questions, so this is the topic to work on.",
        "HCF is going well at 90% correct.",
    ],
    "suggestions": ["Spend ten minutes on fractions with a pizza or a ruler.", "Praise the HCF result."],
}


def fake_gemini(monkeypatch, handler):
    """Route Gemini HTTP calls to `handler(request) -> httpx.Response` and record the requests."""
    seen: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    monkeypatch.setattr(gemini_insights, "_client_factory",
                        lambda: httpx.AsyncClient(transport=httpx.MockTransport(respond)))
    return seen


def report(client, sid, parent, **params):
    r = client.get(f"/parent/children/{sid}/report", headers=parent, params=params)
    assert r.status_code == 200, r.text
    return r.json()


# ---------- the endpoint ----------
def test_without_a_key_the_template_insights_are_used(client, with_data):
    sid, parent, _ = with_data
    body = report(client, sid, parent)
    assert body["insights_source"] == "templates" and body["headline"] is None and body["suggestions"] == []
    assert any("Needs help with" in line for line in body["insights"])          # the old fixed sentences


def test_report_uses_gemini_when_a_key_is_set(client, with_data, monkeypatch):
    sid, parent, _ = with_data
    monkeypatch.setenv("GEMINI_API_KEY", KEY)
    fake_gemini(monkeypatch, lambda req: httpx.Response(200, json=gemini_reply(GOOD)))
    body = report(client, sid, parent)
    assert body["insights_source"] == "gemini"
    assert body["headline"] == "thandi is strong in HCF but needs help with fractions."      # name put back
    assert body["insights"][0].startswith("thandi got 30% correct on fractions")
    assert len(body["suggestions"]) == 2
    assert body["insights_model"] == gemini_insights.DEFAULT_MODEL
    assert "summary" in body and "topics" in body                              # the rest of the report is unchanged


def test_ai_false_skips_gemini(client, with_data, monkeypatch):
    sid, parent, _ = with_data
    monkeypatch.setenv("GEMINI_API_KEY", KEY)
    seen = fake_gemini(monkeypatch, lambda req: httpx.Response(200, json=gemini_reply(GOOD)))
    assert report(client, sid, parent, ai="false")["insights_source"] == "templates"
    assert seen == []


@pytest.mark.parametrize("response", [
    httpx.Response(429, json={"error": {"message": "quota"}}),
    httpx.Response(500, text="oops"),
    httpx.Response(200, text="not json at all"),
    httpx.Response(200, json={"candidates": []}),
    httpx.Response(200, json={"promptFeedback": {"blockReason": "SAFETY"}}),
    httpx.Response(200, json=gemini_reply(GOOD, finish="MAX_TOKENS")),
    httpx.Response(200, json=gemini_reply({"headline": "x", "insights": ["only one line"], "suggestions": []})),
])
def test_any_gemini_problem_falls_back_to_templates(client, with_data, monkeypatch, response):
    sid, parent, _ = with_data
    monkeypatch.setenv("GEMINI_API_KEY", KEY)
    fake_gemini(monkeypatch, lambda req: response)
    body = report(client, sid, parent)
    assert body["insights_source"] == "templates" and body["insights"]


def test_network_failure_falls_back_to_templates(client, with_data, monkeypatch):
    sid, parent, _ = with_data
    monkeypatch.setenv("GEMINI_API_KEY", KEY)

    def down(req):
        raise httpx.ConnectError("no internet")
    fake_gemini(monkeypatch, down)
    assert report(client, sid, parent)["insights_source"] == "templates"


def test_endpoint_can_be_driven_by_a_fake_writer(client, with_data):
    sid, parent, _ = with_data

    async def writer(child, days):
        return {"headline": "H", "insights": ["one", "two"], "suggestions": ["s"], "model": "m", "generated_at": "t"}
    app.dependency_overrides[get_insight_writer] = lambda: writer
    body = report(client, sid, parent)
    assert (body["headline"], body["insights"], body["insights_source"]) == ("H", ["one", "two"], "gemini")


def test_other_familys_child_is_still_404_and_gemini_is_not_called(client, with_data, monkeypatch):
    from tests.test_parent import login, make_user
    sid, _, _ = with_data
    make_user(client, "stranger", "parent")
    monkeypatch.setenv("GEMINI_API_KEY", KEY)
    seen = fake_gemini(monkeypatch, lambda req: httpx.Response(200, json=gemini_reply(GOOD)))
    assert client.get(f"/parent/children/{sid}/report", headers=login(client, "stranger")).status_code == 404
    assert seen == []


def test_health_says_which_insight_source_is_active(client, monkeypatch):
    assert client.get("/health").json()["ai_insights"] == "templates"
    monkeypatch.setenv("GEMINI_API_KEY", KEY)
    assert client.get("/health").json()["ai_insights"] == "gemini"
    monkeypatch.setenv("TUTOR_INSIGHTS_AI", "false")
    assert client.get("/health").json()["ai_insights"] == "templates"


# ---------- what is sent to Gemini ----------
def test_request_format_and_key_handling(client, with_data, monkeypatch):
    sid, parent, _ = with_data
    monkeypatch.setenv("GEMINI_API_KEY", KEY)
    monkeypatch.setenv("GEMINI_MODEL", "gemini-test-model")
    seen = fake_gemini(monkeypatch, lambda req: httpx.Response(200, json=gemini_reply(GOOD)))
    report(client, sid, parent)
    req = seen[0]
    assert str(req.url) == "https://generativelanguage.googleapis.com/v1beta/models/gemini-test-model:generateContent"
    assert req.headers["x-goog-api-key"] == KEY
    assert KEY not in str(req.url) and KEY.encode() not in req.content          # key only in the header
    body = json.loads(req.content)
    assert body["generationConfig"]["responseMimeType"] == "application/json"
    assert body["systemInstruction"]["parts"][0]["text"] == gemini_insights.SYSTEM_PROMPT


def test_child_name_and_chat_text_never_leave_the_machine(client, with_data, monkeypatch):
    sid, parent, student = with_data
    client.post("/chat", headers=student, json={"message": "SECRETCHATWORD how do I add fractions?"})
    monkeypatch.setenv("GEMINI_API_KEY", KEY)
    seen = fake_gemini(monkeypatch, lambda req: httpx.Response(200, json=gemini_reply(GOOD)))
    report(client, sid, parent)
    sent = seen[0].content.decode().lower()
    assert "secretchatword" not in sent
    assert "thandi" not in sent                                                 # replaced by [CHILD]
    assert "[child]" in sent
    assert "questions_asked" not in sent and "asking_often" not in sent        # nothing derived from chats


def test_redaction_can_be_switched_off(client, with_data, monkeypatch):
    sid, parent, _ = with_data
    monkeypatch.setenv("GEMINI_API_KEY", KEY)
    monkeypatch.setenv("TUTOR_INSIGHTS_REDACT", "false")
    seen = fake_gemini(monkeypatch, lambda req: httpx.Response(200, json=gemini_reply(GOOD)))
    report(client, sid, parent)
    assert "thandi" in seen[0].content.decode().lower()


def test_a_child_with_no_activity_does_not_call_gemini(client, family, monkeypatch):    # noqa: F811
    sid, parent, _ = family
    monkeypatch.setenv("GEMINI_API_KEY", KEY)
    seen = fake_gemini(monkeypatch, lambda req: httpx.Response(200, json=gemini_reply(GOOD)))
    assert report(client, sid, parent)["insights_source"] == "templates"
    assert seen == []


# ---------- checking the answer ----------
def test_invented_percentages_are_dropped(client, with_data, monkeypatch):
    sid, parent, _ = with_data
    monkeypatch.setenv("GEMINI_API_KEY", KEY)
    reply = {**GOOD, "insights": GOOD["insights"] + ["[CHILD] scored 81% on fractions, a big jump."]}
    fake_gemini(monkeypatch, lambda req: httpx.Response(200, json=gemini_reply(reply)))
    body = report(client, sid, parent)
    assert body["insights_source"] == "gemini" and len(body["insights"]) == 2
    assert not any("81%" in line for line in body["insights"])


def test_markdown_bullets_and_fences_are_cleaned(client, with_data, monkeypatch):
    sid, parent, _ = with_data
    monkeypatch.setenv("GEMINI_API_KEY", KEY)
    messy = {"headline": "**Good week**", "suggestions": ["- Try a game of chess together"],
             "insights": ["• **Fractions** is at 30% correct.", "1. HCF is at 90% correct."]}
    text = "```json\n" + json.dumps(messy) + "\n```"
    fake_gemini(monkeypatch, lambda req: httpx.Response(
        200, json={"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": text}]}}]}))
    body = report(client, sid, parent)
    assert body["headline"] == "Good week"
    assert body["insights"] == ["Fractions is at 30% correct.", "HCF is at 90% correct."]
    assert body["suggestions"] == ["Try a game of chess together"]


def test_thinking_parts_are_ignored(client, with_data, monkeypatch):
    sid, parent, _ = with_data
    monkeypatch.setenv("GEMINI_API_KEY", KEY)
    parts = [{"text": "let me think...", "thought": True}, {"text": json.dumps(GOOD)}]
    fake_gemini(monkeypatch, lambda req: httpx.Response(
        200, json={"candidates": [{"finishReason": "STOP", "content": {"parts": parts}}]}))
    assert report(client, sid, parent)["insights_source"] == "gemini"


# ---------- cost control ----------
def test_unchanged_data_is_answered_from_the_cache(client, with_data, monkeypatch):
    sid, parent, _ = with_data
    monkeypatch.setenv("GEMINI_API_KEY", KEY)
    seen = fake_gemini(monkeypatch, lambda req: httpx.Response(200, json=gemini_reply(GOOD)))
    first, second = report(client, sid, parent), report(client, sid, parent)
    assert len(seen) == 1 and first["insights"] == second["insights"]


def test_changed_data_asks_gemini_again_unless_it_was_asked_very_recently(client, with_data, monkeypatch):
    sid, parent, _ = with_data
    monkeypatch.setenv("GEMINI_API_KEY", KEY)
    seen = fake_gemini(monkeypatch, lambda req: httpx.Response(200, json=gemini_reply(GOOD)))
    report(client, sid, parent)
    practice(sid, "fractions", 5, 5, days_ago=0)
    report(client, sid, parent)
    assert len(seen) == 2                                                       # data changed, no cooldown

    monkeypatch.setenv("TUTOR_INSIGHTS_MIN_SECONDS", "300")
    practice(sid, "hcf", 5, 1, days_ago=0)
    report(client, sid, parent)
    assert len(seen) == 2                                                       # asked a moment ago: reused despite new data


def test_failures_are_not_cached(client, with_data, monkeypatch):
    sid, parent, _ = with_data
    monkeypatch.setenv("GEMINI_API_KEY", KEY)
    answers = [httpx.Response(503, text="busy"), httpx.Response(200, json=gemini_reply(GOOD))]
    fake_gemini(monkeypatch, lambda req: answers.pop(0))
    assert report(client, sid, parent)["insights_source"] == "templates"
    assert report(client, sid, parent)["insights_source"] == "gemini"


# ---------- unit level ----------
def test_generate_returns_none_when_not_configured(client, with_data):
    sid, _, _ = with_data
    assert asyncio.run(gemini_insights.generate(db.get_user_by_id(sid), 14)) is None


def test_payload_is_the_assistants_allow_list(client, with_data):
    sid, _, _ = with_data
    payload = gemini_insights.build_payload(db.get_user_by_id(sid), 14)
    assert set(payload) >= {"period_days", "overview", "topics", "trends", "games"}
    assert payload["overview"]["topics_needing_help"] and payload["overview"]["topics_going_well"]
