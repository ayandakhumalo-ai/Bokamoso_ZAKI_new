import pytest
import asyncio
import json

import httpx

from app import assistant, db
from app.assistant_routes import get_tool_llm
from app.main import app
from tests.test_parent import link, login, make_user


def fake_model(replies, seen):
    """A scripted stand-in for Ollama. `seen` collects every (messages, tools) the model receives."""
    it = iter(replies)

    async def chat(messages, tools):
        seen.append((json.loads(json.dumps(messages)), tools))
        reply = next(it)
        if isinstance(reply, Exception):
            raise reply
        return reply

    return chat


def use_model(chat):
    app.dependency_overrides[get_tool_llm] = lambda: chat   # the conftest fixture clears this afterwards


def setup_family(client):
    make_user(client, "mama", "parent")
    sid = make_user(client, "thandi")
    link(client, "mama", "thandi")
    return sid


def ask(client, sid, question="How is she doing?", who="mama", history=None):
    return client.post(f"/parent/children/{sid}/ask", headers=login(client, who),
                       json={"question": question, "history": history or []})


# ---------- the endpoint ----------
def test_parent_gets_an_answer_and_the_read_only_tools_are_offered(client):
    sid = setup_family(client)
    seen = []
    use_model(fake_model([{"role": "assistant", "content": "**Thandi** is doing fine."}], seen))
    r = ask(client, sid)
    assert r.status_code == 200, r.text
    assert r.json()["answer"] == "Thandi is doing fine."          # markdown removed
    assert r.json()["tools_used"] == ["get_overview"]
    assert {t["function"]["name"] for t in seen[0][1]} == {
        "get_overview", "get_topic_details", "get_trends", "get_games", "get_school_records",
        "get_quizzes", "get_quiz_mistakes"}


def test_only_linked_parents_can_ask(client):
    sid = setup_family(client)
    make_user(client, "stranger", "parent")
    use_model(fake_model([], []))
    url = f"/parent/children/{sid}/ask"
    assert client.post(url, json={"question": "hi"}).status_code == 401
    assert ask(client, sid, who="stranger").status_code == 404     # not their child
    assert ask(client, sid, who="thandi").status_code == 403       # students cannot use it


def test_the_assistant_never_sees_the_childs_chat(client):
    sid = setup_family(client)
    db.add_message(sid, "user", "my secret question xyz", "2026-10-29 10:00:00")
    db.add_message(sid, "assistant", "private tutor reply abc", "2026-10-29 10:00:05")
    seen = []
    use_model(fake_model([
        {"role": "assistant", "content": "", "tool_calls": [
            {"function": {"name": "get_topic_details", "arguments": {}}},
            {"function": {"name": "get_trends", "arguments": {}}},
            {"function": {"name": "get_games", "arguments": {}}}]},
        {"role": "assistant", "content": "ok"}], seen))
    r = ask(client, sid, "What did she ask the tutor?")
    assert r.status_code == 200, r.text
    everything = json.dumps(seen)
    assert "my secret question xyz" not in everything
    assert "private tutor reply abc" not in everything
    for banned in ("questions_asked", "recent_questions", "last_active", "engagement", "activity_now"):
        assert banned not in everything


def test_a_model_without_tool_support_still_answers(client):
    sid = setup_family(client)
    seen = []
    use_model(fake_model([assistant.ToolsUnsupported("no tools"),
                          {"role": "assistant", "content": "She is doing well."}], seen))
    r = ask(client, sid)
    assert r.status_code == 200 and r.json()["answer"] == "She is doing well."
    assert seen[1][1] is None and all(m["role"] != "tool" for m in seen[1][0])


def test_model_offline_gives_503(client):
    sid = setup_family(client)
    use_model(fake_model([httpx.ConnectError("down")], []))
    assert ask(client, sid).status_code == 503


def test_question_is_validated(client):
    sid = setup_family(client)
    use_model(fake_model([], []))
    assert ask(client, sid, "").status_code == 422
    assert ask(client, sid, "x" * 1001).status_code == 422


# ---------- online models: names stay off the internet ----------
def test_redactor_replaces_names_and_restores_them():
    r = assistant.Redactor({"id": 1, "username": "Alex"})
    sent = r.out("Alex goes to St. Mary's High School. Ask Mrs. Davis or just Davis about alex.")
    for secret in ("Alex", "alex", "St. Mary", "Davis"):
        assert secret not in sent
    assert r.back("[Child] studies at [SCHOOL] with [TEACHER_2].") == (
        "Alex studies at St. Mary's High School with Mrs. Davis.")


def test_an_online_model_never_receives_names_but_the_parent_sees_them(client):
    make_user(client, "mama", "parent")
    sid = make_user(client, "Alex")
    link(client, "mama", "Alex")
    seen = []
    chat = fake_model([{"role": "assistant", "content": "[CHILD] is doing well at [SCHOOL]. Ask [TEACHER_2]."}], seen)
    chat.external = True                      # marks it as a model that lives on the internet
    use_model(chat)
    r = ask(client, sid, "How is Alex doing at St. Mary's? Should I ask Mrs. Davis?")
    assert r.status_code == 200, r.text
    wire = json.dumps(seen)
    for secret in ("Alex", "St. Mary", "Davis", "Thompson", "Patel"):
        assert secret not in wire
    assert r.json()["answer"] == "Alex is doing well at St. Mary's High School. Ask Mrs. Davis."


def test_openai_messages_are_converted_with_paired_call_ids():
    msgs = [
        {"role": "user", "content": "q"},
        {"role": "assistant", "content": "", "tool_calls": [{"function": {"name": "get_games", "arguments": {"days": 7}}},
                                                           {"function": {"name": "get_trends", "arguments": {}}}]},
        {"role": "tool", "tool_name": "get_games", "content": "G"},
        {"role": "tool", "tool_name": "get_trends", "content": "T"},
    ]
    out = assistant.to_openai_messages(msgs)
    assert [c["id"] for c in out[1]["tool_calls"]] == ["call_1", "call_2"]
    assert out[1]["tool_calls"][0]["function"]["arguments"] == '{"days": 7}'
    assert [out[2]["tool_call_id"], out[3]["tool_call_id"]] == ["call_1", "call_2"]
    assert all("tool_name" not in m for m in out)
    back = assistant.from_openai_message({"content": None, "tool_calls": [
        {"id": "x", "type": "function", "function": {"name": "get_games", "arguments": '{"days": 7}'}}]})
    assert back["tool_calls"][0]["function"] == {"name": "get_games", "arguments": {"days": 7}}


def test_default_model_is_local_and_online_is_opt_in(monkeypatch):
    monkeypatch.delenv("TUTOR_ASSISTANT_PROVIDER", raising=False)
    assert assistant.build_chat() is assistant.ollama_chat
    monkeypatch.setenv("TUTOR_ASSISTANT_PROVIDER", "openai")
    assert getattr(assistant.build_chat(), "external", False) is True
    monkeypatch.setenv("TUTOR_ASSISTANT_FALLBACK", "false")
    assert assistant.build_chat() is assistant.openai_chat


def test_online_failure_falls_back_to_the_local_model(monkeypatch):
    monkeypatch.setenv("TUTOR_ASSISTANT_PROVIDER", "openai")
    monkeypatch.delenv("TUTOR_ASSISTANT_FALLBACK", raising=False)

    async def down(messages, tools):
        raise httpx.ConnectError("no internet")

    async def local(messages, tools):
        return {"role": "assistant", "content": "local answer"}

    monkeypatch.setattr(assistant, "openai_chat", down)
    monkeypatch.setattr(assistant, "ollama_chat", local)
    assert asyncio.run(assistant.build_chat()([], None))["content"] == "local answer"


def test_when_both_models_fail_the_reason_is_kept(monkeypatch):
    monkeypatch.setenv("TUTOR_ASSISTANT_PROVIDER", "openai")
    monkeypatch.delenv("TUTOR_ASSISTANT_FALLBACK", raising=False)
    bad_key = httpx.HTTPStatusError("401", request=httpx.Request("POST", "http://x"),
                                    response=httpx.Response(401, json={"error": {"message": "Invalid API Key"}}))

    async def online(messages, tools):
        raise bad_key

    async def local(messages, tools):
        raise httpx.ConnectError("ollama is not running")

    monkeypatch.setattr(assistant, "openai_chat", online)
    monkeypatch.setattr(assistant, "ollama_chat", local)
    try:
        asyncio.run(assistant.build_chat()([], None))
        raised = None
    except assistant.AssistantUnavailable as e:
        raised = str(e)
    assert raised and "401" in raised and "Invalid API Key" in raised and "ollama is not running" in raised


def test_unavailable_gives_503_and_debug_mode_shows_the_reason(client, monkeypatch):
    sid = setup_family(client)
    use_model(fake_model([assistant.AssistantUnavailable("online service: HTTP 404: model not found")], []))
    r = ask(client, sid)
    assert r.status_code == 503 and "model not found" not in r.json()["detail"]
    monkeypatch.setenv("TUTOR_ASSISTANT_DEBUG", "true")
    use_model(fake_model([assistant.AssistantUnavailable("online service: HTTP 404: model not found")], []))
    assert "model not found" in ask(client, sid).json()["detail"]


def test_unconfigured_online_provider_is_reported_not_hidden(client, monkeypatch):
    sid = setup_family(client)
    monkeypatch.setenv("TUTOR_ASSISTANT_PROVIDER", "openai")
    monkeypatch.setenv("TUTOR_ASSISTANT_FALLBACK", "false")
    for name in ("TUTOR_ASSISTANT_BASE_URL", "TUTOR_ASSISTANT_API_KEY", "TUTOR_ASSISTANT_MODEL"):
        monkeypatch.delenv(name, raising=False)
    r = ask(client, sid)                      # uses the real model selection
    assert r.status_code == 503 and "not set up" in r.json()["detail"]


def test_provider_rate_limit_is_reported_as_429(client):
    sid = setup_family(client)
    busy = httpx.HTTPStatusError("busy", request=httpx.Request("POST", "http://x"), response=httpx.Response(429))
    use_model(fake_model([busy], []))
    assert ask(client, sid).status_code == 429


# ---------- pure helpers ----------
def test_plain_text_removes_markdown():
    text = "# Title\n**Bold** and *italic*\n- one\n* two\n`code`"
    assert assistant.plain_text(text) == "Title\nBold and italic\n• one\n• two\ncode"


def test_inline_tool_calls_are_understood():
    msg = {"content": '<tool_call>\n{"name": "get_games", "arguments": {"days": 7}}\n</tool_call>'}
    assert assistant.calls_from(msg) == [("get_games", {"days": 7})]
    assert assistant.plain_text(msg["content"]) == ""


# ---------- answers the question first: the child's data is only loaded when the question needs it ----------
def system_text(seen, call=0):
    return seen[call][0][0]["content"]


def test_a_general_question_does_not_load_the_childs_data(client):
    sid = setup_family(client)
    seen = []
    use_model(fake_model([{"role": "assistant", "content": "Photosynthesis is how plants make food."}], seen))
    r = ask(client, sid, "What is photosynthesis?")
    assert r.status_code == 200 and r.json()["answer"].startswith("Photosynthesis")
    assert r.json()["tools_used"] == []                                        # nothing was looked up
    assert "No data about thandi is loaded" in system_text(seen)
    assert "streak_days" not in json.dumps(seen[0][0])                         # no snapshot anywhere
    assert seen[0][0][-1] == {"role": "user", "content": "What is photosynthesis?"}
    assert {t["function"]["name"] for t in seen[0][1]} >= {"get_overview"}     # tools are still there if the model wants them


def test_a_question_about_the_child_loads_the_data_and_the_question_comes_last(client):
    sid = setup_family(client)
    seen = []
    use_model(fake_model([{"role": "assistant", "content": "She is doing fine."}], seen))
    r = ask(client, sid, "How is she doing in maths?")
    assert r.json()["tools_used"] == ["get_overview"]
    assert "streak_days" in system_text(seen)                                  # data is in the system prompt
    assert [m["role"] for m in seen[0][0]] == ["system", "user"]               # no data blob after the question
    assert seen[0][0][-1]["content"] == "How is she doing in maths?"


def test_the_prompt_tells_the_model_to_answer_first_and_not_to_summarise(client):
    sid = setup_family(client)
    seen = []
    use_model(fake_model([{"role": "assistant", "content": "ok"}], seen))
    ask(client, sid, "How is she doing?")
    prompt = system_text(seen)
    assert "Answer the parent's question first" in prompt
    assert "Do NOT open with a summary" in prompt
    assert "nothing to do with thandi" in prompt


def test_using_the_childs_name_counts_as_about_the_child(client):
    sid = setup_family(client)
    seen = []
    use_model(fake_model([{"role": "assistant", "content": "ok"}], seen))
    assert ask(client, sid, "What worries you about Thandi?").json()["tools_used"] == ["get_overview"]


@pytest.mark.parametrize("question", [
    "What is the capital of France?", "How do I help a child sleep better?", "Explain fractions simply",
    "How does a rainbow form?",
])
def test_general_questions_are_not_treated_as_about_the_child(client, question):
    child = {"id": 1, "username": "thandi"}
    assert assistant.is_about_child(question, [], child) is False


@pytest.mark.parametrize("question", [
    "How is she doing?", "Is Thandi struggling anywhere?", "What were her quiz scores?", "Which games does he play?",
    "Show me the latest grades", "Any homework due?", "What is my child's attendance?",
])
def test_child_questions_are_recognised(client, question):
    assert assistant.is_about_child(question, [], {"id": 1, "username": "thandi"}) is True


def test_short_follow_ups_follow_the_previous_answer(client):
    child = {"id": 1, "username": "thandi"}
    about = [{"role": "user", "content": "How is she?"}, {"role": "assistant", "content": "Thandi scored 80% in maths."}]
    general = [{"role": "user", "content": "What is a noun?"}, {"role": "assistant", "content": "A naming word."}]
    assert assistant.is_about_child("and in English?", about, child) is True
    assert assistant.is_about_child("and an example?", general, child) is False
    assert assistant.is_about_child("and in English?", [], child) is False


def test_a_general_question_still_works_when_the_model_cannot_use_tools(client):
    sid = setup_family(client)
    seen = []
    use_model(fake_model([assistant.ToolsUnsupported("no tools"),
                          {"role": "assistant", "content": "Two plus two is four."}], seen))
    r = ask(client, sid, "What is 2 + 2?")
    assert r.status_code == 200 and r.json()["answer"] == "Two plus two is four."
    assert seen[1][1] is None


def test_the_childs_name_is_still_hidden_from_online_models_in_the_system_prompt(client, monkeypatch):
    sid = setup_family(client)
    seen = []
    online = fake_model([{"role": "assistant", "content": "[CHILD] is fine."}], seen)
    online.external = True
    use_model(online)
    r = ask(client, sid, "How is Thandi doing?")
    assert "thandi" not in json.dumps(seen).lower() and "[CHILD]" in json.dumps(seen)
    assert r.json()["answer"] == "thandi is fine."


# ---------- quiz data on demand ----------
from tests.test_quizzes import add as add_quiz           # noqa: E402  (stores a quiz straight in the database)


def quiz_family(client):
    sid = setup_family(client)
    add_quiz(sid, 3, "Mathematics", "algebra", (True, True, True, True, False), "Algebra quiz")                # 80
    add_quiz(sid, 40, "Mathematics", "algebra", (True, False, False, False, False), "Algebra quiz")            # 20, earlier
    add_quiz(sid, 5, "Biology", "cell_biology", (False, False, True, False, False), "Cell Biology quiz")         # 20
    add_quiz(sid, 9, "Biology", "cell_biology", (False, True, False, False, True), "Cell Biology quiz")          # 40
    return sid


def test_quiz_summary_has_scores_change_and_weak_topics(client):
    sid = quiz_family(client)
    body = assistant.execute_tool({"id": sid, "username": "thandi"}, "get_quizzes", {"days": 30})
    assert body["quizzes_taken"] == 3 and body["average_percent"] == 46.7
    by = {r["subject"]: r for r in body["by_subject"]}
    assert by["Mathematics"]["average_percent"] == 80.0 and by["Mathematics"]["previous_period_average_percent"] == 20.0
    assert by["Mathematics"]["change_points"] == 60.0
    assert by["Biology"]["previous_period_average_percent"] is None and by["Biology"]["change_points"] is None
    assert [t["topic"] for t in body["weak_topics"]] == ["Cell Biology"]
    assert body["latest_quizzes"][0]["date"] >= body["latest_quizzes"][-1]["date"]          # newest first
    assert {"title", "subject", "score_percent", "grade", "right", "out_of"} <= set(body["latest_quizzes"][0])


def test_quiz_summary_filters_by_subject_and_reaches_back_a_year(client):
    sid = quiz_family(client)
    child = {"id": sid, "username": "thandi"}
    bio = assistant.execute_tool(child, "get_quizzes", {"subject": "biology"})
    assert [r["subject"] for r in bio["by_subject"]] == ["Biology"] and bio["quizzes_taken"] == 2
    assert assistant.execute_tool(child, "get_quizzes", {"days": 365})["quizzes_taken"] == 4
    assert assistant.execute_tool(child, "get_quizzes", {"days": "banana"})["period_days"] == 30       # bad input is tidied
    assert assistant.execute_tool(child, "get_quizzes", {"days": 99999})["period_days"] == 365


def test_quiz_summary_for_a_child_with_no_quizzes(client):
    sid = setup_family(client)
    body = assistant.execute_tool({"id": sid, "username": "thandi"}, "get_quizzes", {})
    assert body["quizzes_taken"] == 0 and body["note"] == "No quizzes were taken in this period."


def test_quiz_mistakes_lists_wrong_questions_with_the_right_answers(client):
    sid = quiz_family(client)
    child = {"id": sid, "username": "thandi"}
    body = assistant.execute_tool(child, "get_quiz_mistakes", {"topic": "Cell Biology"})
    assert body["wrong_answers_found"] == 7 and len(body["wrong_answers"]) == 7
    first = body["wrong_answers"][0]
    assert first["topic"] == "Cell Biology" and first["correct_answer"] == "right" and first["child_answered"] == "wrong"
    assert all(w["subject"] == "Biology" for w in body["wrong_answers"])
    assert assistant.execute_tool(child, "get_quiz_mistakes", {"topic": "cell_biology"})["wrong_answers_found"] == 7
    assert assistant.execute_tool(child, "get_quiz_mistakes", {"subject": "Mathematics"})["wrong_answers_found"] == 5   # 60 days
    assert assistant.execute_tool(child, "get_quiz_mistakes", {"subject": "Mathematics", "days": 30})["wrong_answers_found"] == 1
    assert assistant.execute_tool(child, "get_quiz_mistakes", {"topic": "Geography"})["note"] == "No wrong answers match."


def test_quiz_mistakes_are_limited_and_skipped_answers_are_marked(client):
    sid = setup_family(client)
    questions = [{"topic": "fractions", "question": f"Q{i}", "correct_answer": "A", "student_answer": None, "is_correct": False}
                 for i in range(20)]
    db.add_quiz(sid, "Mathematics", "fractions", "Fractions quiz", questions)
    body = assistant.execute_tool({"id": sid, "username": "thandi"}, "get_quiz_mistakes", {"days": 60})
    assert body["wrong_answers_found"] == 20 and len(body["wrong_answers"]) == assistant.quizzes.MAX_WRONG
    assert body["wrong_answers"][0]["child_answered"] == "(skipped)"


def test_the_model_can_call_the_quiz_tools_and_gets_the_data_back(client):
    sid = quiz_family(client)
    seen = []
    use_model(fake_model([
        {"role": "assistant", "content": "", "tool_calls": [
            {"function": {"name": "get_quizzes", "arguments": {"subject": "Mathematics", "days": 90}}},
            {"function": {"name": "get_quiz_mistakes", "arguments": {"topic": "Algebra"}}}]},
        {"role": "assistant", "content": "Her algebra improved a lot."}], seen))
    r = ask(client, sid, "Is she improving in algebra? What does she get wrong?")
    assert r.status_code == 200, r.text
    assert r.json()["tools_used"] == ["get_overview", "get_quizzes", "get_quiz_mistakes"]
    tool_results = [m["content"] for m in seen[1][0] if m["role"] == "tool"]
    assert len(tool_results) == 2 and "change_points" in tool_results[0] and "wrong_answers" in tool_results[1]


def test_the_overview_mentions_quizzes_only_when_there_are_some(client):
    sid = quiz_family(client)
    child = {"id": sid, "username": "thandi"}
    overview = assistant.execute_tool(child, "get_overview", {})
    assert overview["quizzes_last_30_days"]["taken"] == 3
    assert overview["quizzes_last_30_days"]["weak_topics"] == ["Cell Biology (30%)"]
    other = db.create_user("sipho", b"x")
    assert "quizzes_last_30_days" not in assistant.execute_tool({"id": other, "username": "sipho"}, "get_overview", {})


def test_quiz_tools_never_expose_chat_content(client):
    sid = quiz_family(client)
    db.add_message(sid, "user", "my secret question xyz", "2026-10-29 10:00:00")
    child = {"id": sid, "username": "thandi"}
    everything = json.dumps([assistant.execute_tool(child, n, {}) for n in ("get_quizzes", "get_quiz_mistakes", "get_overview")])
    assert "my secret question xyz" not in everything
    for banned in ("questions_asked", "recent_questions", "last_active", "engagement", "activity_now"):
        assert banned not in everything


def test_quiz_text_is_redacted_for_online_models(client):
    sid = setup_family(client)
    db.add_quiz(sid, "English", "reading", "Reading quiz", [{
        "topic": "reading", "question": "Why was Thandi sad in the story?", "correct_answer": "She lost her bag",
        "student_answer": "She was tired", "is_correct": False}])
    seen = []
    online = fake_model([{"role": "assistant", "content": "", "tool_calls": [
        {"function": {"name": "get_quiz_mistakes", "arguments": {}}}]},
        {"role": "assistant", "content": "[CHILD] missed a reading question."}], seen)
    online.external = True
    use_model(online)
    r = ask(client, sid, "Which quiz questions did Thandi miss?")
    assert "thandi" not in json.dumps(seen).lower() and "[CHILD]" in json.dumps(seen)
    assert r.json()["answer"] == "thandi missed a reading question."


# ---------- answers as long as the question needs ----------
def test_the_prompt_lets_length_follow_the_question_and_has_no_word_cap(client):
    sid = setup_family(client)
    seen = []
    use_model(fake_model([{"role": "assistant", "content": "ok"}], seen))
    ask(client, sid, "How is she doing?")
    prompt = system_text(seen)
    assert "Match the length to the question" in prompt and "several paragraphs" in prompt
    assert "under 120 words" not in prompt


def test_ollama_gets_room_for_the_whole_prompt(monkeypatch):
    sent = []

    def handler(request):
        sent.append(json.loads(request.content))
        return httpx.Response(200, json={"message": {"role": "assistant", "content": "hi"}})

    real = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(handler), **kw))
    monkeypatch.delenv("TUTOR_ASSISTANT_NUM_CTX", raising=False)
    asyncio.run(assistant.ollama_chat([{"role": "user", "content": "hi"}], None))
    assert sent[0]["options"]["num_ctx"] == 8192 and sent[0]["options"]["temperature"] == 0.3
    monkeypatch.setenv("TUTOR_ASSISTANT_NUM_CTX", "4096")
    asyncio.run(assistant.ollama_chat([{"role": "user", "content": "hi"}], None))
    assert sent[1]["options"]["num_ctx"] == 4096
