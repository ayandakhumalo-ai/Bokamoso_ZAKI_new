# Offline Tutor API

FastAPI layer in front of Ollama (qwen2.5:3b). Gives students login, chat (streaming or not), and saved history,
and gives parents a read-only view of their children's progress.
Ollama stays on localhost; only this API is reachable.

```
app/config.py    settings from environment variables
app/progress.py  turns activity into streaks, struggles, trends and insights for parents
app/catalog.py   the device's topics and games, and keyword matching of questions to topics
scripts/         seed_demo.py: fake family with ~8 weeks of activity, for demos
app/db.py        SQLite: users (student/parent), parent-child links, messages
app/security.py  bcrypt, JWT login tokens, rate limiter
app/llm.py       streaming client for Ollama
app/main.py      the endpoints
tests/           pytest suite (uses a fake model, no Ollama needed)
```

## 1. Run on your laptop

```bash
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
ollama pull qwen2.5:3b            # skip if you already have it
uvicorn app.main:app --reload --port 8000
```

Interactive docs (try every endpoint in the browser): http://localhost:8000/docs

## 2. Test it

**Automated** (no Ollama needed, the model is faked):

```bash
pytest -v
```

Covers login, bad/expired tokens, per-student history isolation, streaming, rate limiting, and Ollama being down.

**By hand with curl** (needs Ollama running):

```bash
# teacher creates a student
curl -X POST localhost:8000/auth/register -H 'X-Admin-Key: dev-admin-key' \
  -H 'Content-Type: application/json' -d '{"username":"thandi","password":"password123"}'

# student logs in -> copy the access_token
curl -X POST localhost:8000/auth/login -H 'Content-Type: application/json' \
  -d '{"username":"thandi","password":"password123"}'

# ask a question (add "stream": true to see words arrive live; use curl -N)
curl -X POST localhost:8000/chat -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' -d '{"message":"Explain fractions simply"}'

curl localhost:8000/history -H "Authorization: Bearer $TOKEN"
curl localhost:8000/health
```

## 2b. Parent access

Two kinds of account now exist: `student` and `parent`. `/auth/login` and `/me` return the role, so the web app
can show the chat screen to students and a progress dashboard to parents.

| Endpoint | Who | Returns |
|---|---|---|
| `POST /auth/register` (admin key) | admin | create an account; add `"role": "parent"` for parents (default `student`) |
| `POST /admin/links` (admin key) | admin | link a parent to a child: `{"parent_username": "...", "student_username": "..."}` |
| `GET /me` | anyone logged in | id, username, role |
| `GET /parent/children` | parent | the parent's linked children |
| `GET /parent/children/{id}/summary?days=7` | parent | questions asked, active days, current streak, first/last active, 5 most recent questions |
| `GET /parent/children/{id}/activity?days=14` | parent | questions per day, zeros included, for a bar chart |
| `GET /parent/children/{id}/conversations?limit=50` | parent | the child's questions and the tutor's answers |

Rules enforced by the API (and covered by tests):
- A parent can only see children linked to them. Anyone else's child gives 404, same as a child that doesn't exist.
- Parents cannot call `/chat` or `/history`, and students cannot call the `/parent/...` endpoints.
- Parents have read-only access. Nothing here lets a parent change a child's data.
- With `TUTOR_PARENT_SEES_CHATS=false`, parents still see per-topic counts derived from questions, but never the questions themselves.
- Set `TUTOR_PARENT_SEES_CHATS=false` to hide conversation content: parents then get counts and streaks only.
- Days are counted in local time (`TUTOR_TZ_OFFSET_HOURS`, default 2 for Eswatini).
- An existing `tutor.db` upgrades itself on start-up: current accounts become students, nothing is lost.

Try it in `/docs`, or with curl:

```bash
curl -X POST localhost:8000/auth/register -H 'X-Admin-Key: dev-admin-key' -H 'Content-Type: application/json' \
  -d '{"username":"mama_thandi","password":"password123","role":"parent"}'
curl -X POST localhost:8000/admin/links -H 'X-Admin-Key: dev-admin-key' -H 'Content-Type: application/json' \
  -d '{"parent_username":"mama_thandi","student_username":"thandi"}'
# log in as the parent, then:
curl localhost:8000/parent/children -H "Authorization: Bearer $PARENT_TOKEN"
curl "localhost:8000/parent/children/1/summary?days=7" -H "Authorization: Bearer $PARENT_TOKEN"
```

What "progress" means right now: how much and how consistently the child uses the tutor (questions, active days,
streak, recent questions). It does not measure how well they understand a subject. That needs quizzes or marked
exercises, which would be the next feature to add.

## 2c. Progress tracking for parents (games, topics, struggles, trends)

Chat questions are logged automatically. Everything else (games, lessons, practice) is only known if the
**ZAKI device reports it**. The device calls these three endpoints with the student's token:

| When on the device | Call | Body |
|---|---|---|
| A game session ends | `POST /activity/game` | `{"game": "Chess", "duration_seconds": 540, "result": "win"}` (`result`: win / loss / draw / completed, optional) |
| Child opens a lesson on **Learn** | `POST /activity/learn` | `{"topic": "Fractions"}` |
| Child answers practice questions on **Practice** | `POST /activity/practice` | `{"topic": "Fractions", "total_questions": 5, "correct_answers": 3}` |

Names are tidied automatically ("Tic Tac Toe" and "tic_tac_toe" are the same). Topics and games the API has not
heard of still work. To name a subject other than Maths, add `"subject": "Music"` to learn/practice calls.
The known topics and games live in `app/catalog.py`. Add new ones there.

```javascript
// in the ZAKI web app, after a practice round (token = the student's login token)
fetch(API + "/activity/practice", {
  method: "POST",
  headers: { "Content-Type": "application/json", "Authorization": "Bearer " + token },
  body: JSON.stringify({ topic: "Fractions", total_questions: 5, correct_answers: 3 })
});
```

### What parents can ask

| Endpoint (all read-only, parent login, `?days=` optional) | Answers |
|---|---|
| `GET /parent/children/{id}/report` (default 14 days) | **Everything in one call** plus plain-language `insights`, best for the dashboard's first screen |
| `GET /parent/children/{id}/summary` | How often they ask questions: totals, per-week average, vs the previous period, active days, streak |
| `GET /parent/children/{id}/activity` | Questions per day, for a chart |
| `GET /parent/children/{id}/games` (default 30) | Which games, how many sessions and minutes, days played, wins/losses, favourite, vs the previous period |
| `GET /parent/children/{id}/topics` (default 28) | Every topic with accuracy and a status: `struggling`, `asking_often`, `developing`, `strong`, `not_enough_data`; subjects summarised |
| `GET /parent/children/{id}/trends` (default 28) | `improved`, `declined` and `less_active` topics, and the same per subject, comparing with the previous period |
| `GET /parent/children/{id}/conversations` | The actual conversations (can be switched off) |

### How the verdicts are decided

Defined at the top of `app/progress.py`, so they are easy to change:
- **Struggling** = under 50% correct in practice; **strong** = 80% or more. A topic needs at least **5 practice questions**
  before it is judged, otherwise it is `not_enough_data`.
- **Improved / dropped** = accuracy changed by **10 percentage points or more** compared with the previous period of the
  same length (needs 5+ questions in both). Smaller changes are `stable`.
- **Less active / stopped / new / more** compares how much the child did on a topic (practice questions + lessons +
  chat questions) with the previous period.
- **Asking often** = 4+ chat questions about one topic with no practice results. It is a warning sign, not a score.
- Chat questions are matched to topics by **keywords**, so this is a good guess, not exact. "Help with my homework"
  matches no topic.
- Without practice results the API cannot say how well a child understands anything. It says so in the `insights`
  instead of guessing.

### Try it with demo data

```bash
TUTOR_DB=demo.db python -m scripts.seed_demo        # creates demo_parent / demo_student, ~8 weeks of made-up activity
TUTOR_DB=demo.db uvicorn app.main:app
# open http://localhost:8000/docs, log in as demo_parent (password: demo-password-123),
# then GET /parent/children/2/report?days=28
```

The demo child struggles with Fractions, improved in HCF and Area, dropped in LCM, stopped practising Decimals, and
plays Chess most. Use a separate database file, not your real `tutor.db`.

## 2d. AI-written insights with Google Gemini

By default `GET /parent/children/{id}/report` builds its `insights` from fixed sentence templates. Set a Gemini key and
Gemini writes them instead: a one-sentence `headline`, 3 to 5 `insights`, and 2 to 3 `suggestions` for the parent.

1. Create a key in Google AI Studio (aistudio.google.com, "Get API key").
2. Set it where the API runs, never in code or in git:
   - Windows (PowerShell): `$env:GEMINI_API_KEY="your-key"`
   - Linux / Pi: `export GEMINI_API_KEY=your-key`, or `Environment=GEMINI_API_KEY=...` in the systemd service.
3. Restart the API. `GET /health` now shows `"ai_insights": "gemini"`.
4. Open `/parent/children/{id}/report`. The reply has `"insights_source": "gemini"`. If it says `"templates"`, look at the
   API window: it logs why Gemini was not used.

Add `?ai=false` to a report request to skip Gemini for that call.

**It can never break the report.** No key, no internet, a rate limit, a blocked or half-finished answer, or unusable JSON:
the report quietly falls back to the old template insights and `insights_source` says `"templates"`.

**What is sent to Google.** Only the same allow-listed progress facts the parent assistant can read: accuracy by topic,
improved/declined topics, game totals, and school records if you have them. Never anything the child typed to the tutor, and
nothing derived from it (question counts, "asking often" topics). The child's name, school and teachers are swapped for
placeholders and put back in the answer. This is pseudonymisation, not anonymisation: scores and grades still go out.
Tell parents and the school this before using real children's data, and check Google's terms for the plan you use
(free-tier terms differ from paid ones on how data may be used).

**Checks on the answer.** A line that quotes a percentage that is not in the data is dropped. If fewer than 2 good lines
remain, the templates are used. Markdown and bullets are stripped.

**Cost control.** An answer is reused while the child's data is unchanged (6 hours), and Gemini is never called more than
once per 5 minutes for the same child, so refreshing the dashboard does not use up your quota. These are process-local, so
restarting the API clears them.

| Variable | Default | Meaning |
|---|---|---|
| `GEMINI_API_KEY` | not set | turns Gemini insights on |
| `GEMINI_MODEL` | `gemini-3.8-flash` | change if Google retires or renames the model |
| `GEMINI_BASE_URL` | Google's v1beta address | only change for a proxy |
| `TUTOR_INSIGHTS_AI` | `true` | set `false` to switch Gemini off while keeping the key |
| `TUTOR_INSIGHTS_REDACT` | `true` | swap names for placeholders before sending |
| `TUTOR_INSIGHTS_SCHOOL_RECORDS` | `true` | let Gemini read school grades and attendance |
| `TUTOR_INSIGHTS_CACHE_MINUTES` | `360` | reuse an answer while the data is unchanged |
| `TUTOR_INSIGHTS_MIN_SECONDS` | `300` | shortest gap between Gemini calls for one child |

## 2e. Quizzes and the Grades tab

The device saves every finished quiz **with all of its questions**, so parents can see scores over time and where the child
keeps going wrong.

**Device (student login):** `POST /activity/quiz`
```json
{
  "subject": "Mathematics", "topic": "Algebra", "title": "Algebra quiz", "duration_seconds": 240,
  "questions": [
    {"question": "Solve 3x + 5 = 20", "correct_answer": "x = 5", "student_answer": "x = 5"},
    {"question": "Factorise x^2 + 5x + 6", "correct_answer": "(x + 2)(x + 3)", "student_answer": "(x + 1)(x + 6)"}
  ]
}
```
Leave out `is_correct` and the server compares the answers (ignoring capitals, spaces and a final full stop). Send it yourself
for maths answers that can be written several ways ("1/2" and "0.5"). `student_answer: null` means skipped. The score is
counted by the server from the questions. `title` and a question's own `topic` are optional.

**Parent (read-only):**

| Endpoint | What it gives |
|---|---|
| `GET /parent/children/{id}/quizzes?range=week` | one entry per quiz (title, subject, score, grade, date) plus subject averages, for the bar chart. `range` is `week` (last 7 days, the default), `month` (30), `year` (365) or `all` (since the first quiz) |
| `GET /parent/children/{id}/quizzes/{quiz_id}` | one quiz with every question, the right answer and what the child answered |
| `GET /parent/children/{id}/quizzes/weaknesses?range=month` | topics grouped from all stored questions: **weak** under 60%, **strong** 80% and over, at least 4 questions needed. Weak topics include the last 3 wrong questions |

Grades use A+ 95, A 85, B+ 75, B 65, C 50, D 40, F below (change `GRADES` in `app/quizzes.py`).
Quiz questions are schoolwork, not chat, so `TUTOR_PARENT_SEES_CHATS=false` does not hide them.
Gemini insights get only quiz topics and percentages, never the question text.

Demo data: `scripts.seed_family` now also stores about 100 quizzes per child over a year (Alex is weak at Cell Biology and
Essay Writing, Maya at Fractions). For a database you already have, run `python -m scripts.demo_quizzes` (it skips anyone
who already has quizzes).

## 2f. How the parent chat (`/ask`) answers

It answers the parent's question first. The child's data is only loaded when the question is about the child (the child's name,
"she/he/her/his", "my child", grades, quiz, progress, games, school, homework, attendance and similar words). A short follow-up
such as "and in English?" counts only if the previous answer was about the child. For anything else ("What is photosynthesis?")
nothing about the child is sent to the model, but the read-only tools stay available if it decides it needs them.

**Length follows the question.** A simple factual question gets 1 to 3 sentences. An explanation, advice or "tell me about"
question gets a full answer. Ollama is given room for the whole prompt (`TUTOR_ASSISTANT_NUM_CTX`, default 8192 tokens). If
answers still look cut short or the model forgets the rules, raise it; lower it (for example 4096) if the machine runs out of memory.

**Quiz data on demand.** Besides the overview, school records, topics, trends and games, the assistant can call
`get_quizzes` (score of each recent quiz, subject averages and the change since the previous period, weak and strong topics)
and `get_quiz_mistakes` (the wrong questions, the right answers and what the child answered). It uses them when a parent asks
about quiz results, improvement or mistakes. Quiz question text only leaves the machine, with names replaced, when a parent
asks for it and you use an online model.

Which local model answers parents? By default the same model as the child's tutor (`OLLAMA_MODEL`, for example `zaki-tutor`).
If that model is tuned to talk to children and the parent answers sound off, use a plain model just for parents:
`TUTOR_ASSISTANT_OLLAMA_MODEL=qwen2.5:3b` (run `ollama pull qwen2.5:3b` once).

## 3. Deploy on the Raspberry Pi 5

1. Install Ollama on the Pi and `ollama pull qwen2.5:3b`. Copy this folder to `/home/pi/tutor_api`.
2. Create the venv and install requirements as above.
3. Make real secrets (do not keep the defaults):

   ```bash
   python -c "import secrets; print(secrets.token_urlsafe(48))"   # run twice: secret key + admin key
   ```

4. Create `/etc/systemd/system/tutor-api.service`:

   ```ini
   [Unit]
   Description=Tutor API
   After=network-online.target ollama.service

   [Service]
   User=pi
   WorkingDirectory=/home/pi/tutor_api
   Environment=TUTOR_SECRET_KEY=PASTE_FIRST_VALUE
   Environment=TUTOR_ADMIN_KEY=PASTE_SECOND_VALUE
   Environment=TUTOR_DB=/home/pi/tutor_api/tutor.db
   ExecStart=/home/pi/tutor_api/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
   Restart=always

   [Install]
   WantedBy=multi-user.target
   ```

   ```bash
   sudo systemctl daemon-reload && sudo systemctl enable --now tutor-api
   ```

   The API listens on `127.0.0.1` on purpose. Tailscale or Cloudflare Tunnel (below) is what exposes it.

5. Remote access, pick one:
   - **Tailscale:** `curl -fsSL https://tailscale.com/install.sh | sh && sudo tailscale up`, then run `sudo tailscale serve --bg 8000` for HTTPS inside your tailnet. Install Tailscale on each student's device.
   - **Cloudflare Tunnel:** install `cloudflared`, create a tunnel pointing to `http://localhost:8000`, and attach a hostname on your domain.

6. Test from outside: turn off Wi-Fi on your phone, use mobile data, and open `https://<your-address>/docs`.

## 4. Settings (environment variables)

| Variable | Default | Meaning |
|---|---|---|
| `TUTOR_SECRET_KEY` | dev value | signs login tokens, must be long and random |
| `TUTOR_ADMIN_KEY` | dev value | required to create student accounts |
| `OLLAMA_MODEL` | `qwen2.5:3b` | model name |
| `OLLAMA_URL` | `http://127.0.0.1:11434` | where Ollama listens |
| `TUTOR_DB` | `tutor.db` | SQLite file |
| `TUTOR_RATE_LIMIT` | `10` | chat requests per student per minute |
| `TUTOR_HISTORY_TURNS` | `6` | past exchanges sent to the model as context |
| `TUTOR_TOKEN_MINUTES` | `720` | how long a login lasts |
| `TUTOR_PARENT_SEES_CHATS` | `true` | let parents read conversation content |
| `TUTOR_TZ_OFFSET_HOURS` | `2` | hours ahead of UTC, for counting days |
| `TUTOR_SYSTEM_PROMPT` | generic tutor | put your tutor's real system prompt here |

## 5. Known limits (worth knowing before real students use it)

- Only one answer is generated at a time (a lock queues the rest). Fine for a small class, slow for many at once.
- The rate limiter is in memory, so it resets when the service restarts.
- No password reset or "change password" yet; the admin key holder creates accounts and parent links.
- Back up `tutor.db` regularly. It holds all student history.
