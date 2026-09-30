# SPEAKLOG — voice agent for Vruksha's Proof challenge

A voice agent that talks to a student for ~2 minutes about their day, keeps their words exactly, asks one
contextual follow-up, gets explicit confirmation, and posts the result to their Proof record.

Challenge: https://proof.zeromaintenanceengineer.in/tasks/7f675d9b-b050-4039-8899-da2caf7d537a

## The one rule everything is built around

**The LLM never touches the transcript.** Speech-to-text produces the raw transcript; it is stored
unchanged and is what gets posted. The LLM only *reads* the transcripts to write one follow-up question.
That boundary is enforced in code: `agent/conversation.py` holds the raw transcripts, `agent/followup.py`
receives copies and can only return a question string — it has no path to mutate stored answers.

## Field mapping (why posting is trivial)

Proof's `post_log` takes `{verb, content, why}`, and the three questions fill them:

| Question | Proof field |
|---|---|
| What did you try today? + What broke? + the follow-up answer | `content` (their words, joined) |
| Why did you choose that? | `why` (their words) |
| inferred from what broke / what they built | `verb` |

## Run it (zero keys, zero cost)

```
pip install -r requirements.txt
copy .env.example .env      # defaults are safe: PROOF_DRY_RUN=1, providers=browser
uvicorn app.main:app --reload
# open http://127.0.0.1:8000
```

With no API keys it runs the full flow using the browser's own mic transcription and speech, and
**dry-run posting** (prints the exact post_log JSON, sends nothing). Add keys in `.env` to switch on
server-side Whisper, a real LLM follow-up, Edge TTS, and live posting.

## Switching on the real stack (each is optional)

| Env var | Off (default) | On |
|---|---|---|
| `STT_PROVIDER` | `browser` (Web Speech API) | `groq` (Groq Whisper) or `faster_whisper` (local) |
| `LLM_PROVIDER` | `rule` (template extractor) | `groq` or `gemini` |
| `TTS_PROVIDER` | `browser` (speechSynthesis) | `edge` (Edge TTS, free, no key) |
| `PROOF_DRY_RUN` | `1` (print JSON only) | `0` (actually POST — needs `PROOF_TOKEN`) |

## The Proof token — read this

Create it at `proof.zeromaintenanceengineer.in/settings/mcp`. It posts ONLY to your own record, is capped
at **20 posts/day**, and must never be committed (it lives in `.env`, which is gitignored). Keep
`PROOF_DRY_RUN=1` while developing so the cap is never touched by accident; flip to `0` only for a
deliberate confirmed test.

## Build phases (also the Proof log arc)

1. Connector + dry-run, text dialogue, contextual follow-up, transcript preservation.  ← scaffolded here
2. Voice in/out (Whisper + Edge TTS), confirmation flow, error handling.
3. Browser UI polish, deploy, public HTTPS URL.
4. Cross-device test: mic permissions, Tamil transcription, "yes" posts, "no" never posts.
5. README + architecture + build logs on Proof + submit.
