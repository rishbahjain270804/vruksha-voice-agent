# SPEAKLOG — a voice agent for Vruksha's Proof challenge

Talk to it for about two minutes about your day. It listens, **understands what you said and asks the
next question from it** (not a fixed script), keeps your words exactly, reads the log back, and posts it
to your Proof record — only after you say yes. English or Tamil.

Challenge: https://proof.zeromaintenanceengineer.in/tasks/7f675d9b-b050-4039-8899-da2caf7d537a

---

## Run it (works with zero keys, zero cost)

```bash
pip install -r requirements.txt
cp .env.example .env          # defaults are safe: DRY_RUN on, everything browser-side
uvicorn app.main:app --reload
# open http://127.0.0.1:8000
```

With no keys it runs the whole flow on the browser's own mic + speech and **dry-run posting** (prints the
exact `post_log` JSON, sends nothing). Add a free Groq key to switch on real understanding and Tamil-grade
speech (see config below).

---

## The one rule everything is built around

**The language model never touches the transcript.** Speech-to-text produces the raw words; they are
stored unchanged and are exactly what gets posted. The model only ever *reads* them to decide the next
question. This is enforced structurally, not by convention: `app/agent/conversation.py` owns the
transcripts and is the only place that writes them; `app/agent/planner.py` receives read-only copies and
can return only a question string — it has no path to mutate a stored answer.

## What makes it more than a form

- **Adaptive interview.** After each answer the planner reads the whole conversation and picks the single
  best next question — following your thread, quoting your own words — then decides on its own when it has
  enough. One fixed opener; everything after is generated. (`app/agent/planner.py`, on `gpt-oss-120b`, with
  a keyless rule fallback.)
- **Real turn-taking.** Time-based end-of-speech detection so a thinking pause doesn't cut you off, a
  "Done speaking" override, and a beat before it replies so it never talks over you. (`frontend/index.html`)
- **Project memory / recall.** If you refer back — "the project we talked about" — it stops and asks
  *which* earlier project, and threads today's log onto it as a continuation. (`app/agent/history.py`)
- **Tamil.** Questions, Whisper transcription, and yes/no confirmation all work in Tamil.
- **Confirm before post.** It reads the assembled log back verbatim; nothing posts until an explicit "yes".

## Designed for what Proof actually rewards

I read the public Proof corpus (the curated feed + the curator's "why I picked this" notes) and
built the interview around what separates a picked log from an ignored one: **a reason next to the
decision, the alternative it was chosen _over_, one honest thing (what was skipped / risked / got
wrong), and a concrete artefact (a file, an error, a number).** 19% of picked logs name an
alternative, 34% fill that honest "shadow line", 53% name a concrete artefact — so the planner steers
the conversation to surface those, **in the speaker's own words** (never fabricated). The verb is
chosen from Proof's real enum by the model, with a transparent rule fallback.

## How answers become a Proof log

Proof's `post_log` takes `{verb, content, why}`. Because questions are planned (not fixed), the mapping is
by **meaning**, not position:

| Proof field | Filled from |
|---|---|
| `content` | every answer except the reason, joined — your words, in order |
| `why` | the answer to whichever question asked *why / what made you / what led you* |
| `verb` | inferred from your words (broke → `stuck`, chose → `decided`, else `built`) |

## Configuration

| Env var | Default | Turn it up to |
|---|---|---|
| `STT_PROVIDER` | `browser` | `groq` (Whisper large-v3, best Tamil) or `faster_whisper` (local, offline) |
| `LLM_PROVIDER` | `rule` | `groq` (adaptive planner) or `gemini` |
| `GROQ_MODEL` | `openai/gpt-oss-120b` | any chat model your key has |
| `TTS_PROVIDER` | `browser` | `edge` (neural, free; needs Bing reachable) |
| `PROOF_DRY_RUN` | `1` (print JSON only) | `0` (actually POST — needs `PROOF_TOKEN`) |

A free Groq key (console.groq.com, no card) turns on both the adaptive planner and Whisper STT. If Groq
STT fails mid-session, it falls back to local Whisper so a network drop never strands the speaker.

## The Proof token — read this

Create it at `proof.zeromaintenanceengineer.in/settings/mcp`. It posts **only to your own record**, is
capped at **20 posts/day**, and must never be committed — it lives in `.env`, which is gitignored. Keep
`PROOF_DRY_RUN=1` while developing so the cap is never touched by accident; flip to `0` only for a
deliberate, confirmed test post.

## Architecture

```
app/
  main.py               FastAPI: start / answer / confirm / tts / healthz
  models/schemas.py     conversation state + Proof post shapes
  agent/
    conversation.py     the state machine; OWNS the raw transcripts
    planner.py          adaptive next-question (LLM) + keyless fallback
    history.py          recent-topic memory: recall + "which project?" matching
    followup.py         keyword helpers shared by the planner
  voice/
    transcriber.py      STT: Groq Whisper / local faster-whisper
    speaker.py          TTS: Edge / browser
  proof/client.py       the /api/mcp post_log connector (dry-run by default)
frontend/index.html     the hands-free UI (turn-taking, confirm, Proof theme)
```

## Honest limits

- Sessions are in-memory (single process) — fine for the demo; a restart clears in-flight sessions.
- Transcription is only as good as the model; proper nouns can still slip. A vocabulary hint biases
  spelling, but word-for-word is preserved — it never adds words you didn't say.
- The keyless rule planner references your words but cannot truly reason; the Groq planner is the real one.
