"""SPEAKLOG FastAPI app. Orchestrates: start -> answer (xN) -> confirm -> post.

Endpoints
  GET  /                       the tester UI
  POST /api/session/start      -> {session_id, stage, say}      (optionally ?lang=ta)
  POST /api/session/{id}/answer  form: transcript= OR audio=@   -> {stage, say, transcript, draft?}
  POST /api/session/{id}/confirm  json: {utterance}             -> posts on yes, stops on no
  GET  /api/session/{id}       -> full state (debugging)
  GET  /api/tts?text=&lang=    -> mp3 if a server TTS provider is on, else 204 (browser speaks)

Session state is in-memory (one process). For the tester that's fine; note it in the README."""
from __future__ import annotations
import os, uuid
from dotenv import load_dotenv
from fastapi import FastAPI, UploadFile, Form, HTTPException, Response
from fastapi.responses import HTMLResponse, JSONResponse
from pathlib import Path

load_dotenv()
from .models.schemas import ConversationState, LANGUAGES
from .agent import conversation as conv
from .agent import history
from .voice.transcriber import transcribe
from .voice.speaker import synth
from .proof.client import post_log

app = FastAPI(title="SPEAKLOG")
SESSIONS: dict[str, ConversationState] = {}
FRONTEND = Path(__file__).resolve().parent.parent / "frontend"


def _page(name: str) -> HTMLResponse:
    f = FRONTEND / name
    return HTMLResponse(f.read_text(encoding="utf-8") if f.exists() else f"<h1>{name} missing</h1>")


def _get(sid: str) -> ConversationState:
    st = SESSIONS.get(sid)
    if not st:
        raise HTTPException(404, "unknown session")
    return st


def _view(st: ConversationState) -> dict:
    d = {"session_id": st.session_id, "stage": st.stage, "lang": st.lang,
         "say": conv.next_prompt(st), "answers": [a.model_dump() for a in st.answers]}
    if st.stage in ("confirm", "posted", "cancelled"):
        d["draft"] = {"verb": st.draft_verb, "content": st.draft_content, "why": st.draft_why}
    if st.continues:
        d["continues"] = st.continues
    if st.post_result is not None:
        d["post_result"] = st.post_result
    return d


@app.get("/", response_class=HTMLResponse)
def home():
    return _page("home.html")


@app.get("/talk", response_class=HTMLResponse)
def talk():
    return _page("talk.html")


@app.get("/how", response_class=HTMLResponse)
def how():
    return _page("how.html")


@app.get("/account", response_class=HTMLResponse)
def account():
    return _page("account.html")


@app.get("/app.css")
def app_css():
    f = FRONTEND / "app.css"
    return Response(content=f.read_text(encoding="utf-8") if f.exists() else "", media_type="text/css")


@app.get("/api/logs")
def api_logs(client: str = ""):
    from .agent import history
    return history.list_logs((client or "").strip().lower()[:64])


@app.post("/api/auth/setup")
def auth_setup(body: dict):
    from . import auth
    ok, res = auth.setup(body.get("username", ""))
    if not ok:
        raise HTTPException(400, res)
    return {"otpauth": res}


@app.post("/api/auth/verify")
def auth_verify(body: dict):
    from . import auth
    user = (body.get("username", "") or "").strip()
    if auth.verify(user, body.get("code", "")):
        return {"ok": True, "client": user}
    raise HTTPException(400, "invalid or expired code")


@app.post("/api/auth/proof")
def auth_proof(body: dict):
    """Store the signed-in user's own Proof token. Requires a valid current code to authorize."""
    from . import auth
    user = (body.get("username", "") or "").strip()
    if not auth.verify(user, body.get("code", "")):
        raise HTTPException(400, "invalid or expired code")
    auth.set_proof_token(user, body.get("token", ""))
    return {"ok": True, "connected": bool((body.get("token", "") or "").strip())}


@app.get("/api/auth/proof_status")
def auth_proof_status(username: str = ""):
    from . import auth
    return {"connected": bool(auth.get_proof_token((username or "").strip()))}


@app.get("/api/languages")
def languages():
    return [{"code": k, "native": v["native"], "sr": v["sr"]} for k, v in LANGUAGES.items()]


@app.post("/api/session/start")
def start(lang: str = "en", client: str = ""):
    lang = lang if lang in LANGUAGES else "en"
    sid = uuid.uuid4().hex[:12]
    SESSIONS[sid] = ConversationState(session_id=sid, client=(client or "").strip().lower()[:64], lang=lang, stage="greet")
    return _view(SESSIONS[sid])


@app.post("/api/session/{sid}/answer")
async def answer(sid: str, transcript: str = Form(default=""), audio: UploadFile | None = None):
    st = _get(sid)
    if st.stage not in ("greet", "pick", "ask", "link"):
        raise HTTPException(409, f"not accepting answers at stage '{st.stage}'")
    text = (transcript or "").strip()
    if audio is not None:
        server_text = transcribe(await audio.read(), st.lang)
        if server_text:            # server STT wins when a provider is on
            text = server_text
    if not text:
        raise HTTPException(400, "no transcript (browser STT empty and no server provider)")
    if st.stage == "pick":         # "which earlier project is this?"
        conv.resolve_pick(st, text)
        return {**_view(st), "transcript": text}
    if st.stage == "link":         # the continuation yes/no
        d = conv.classify_confirm(text, st.lang)
        if d == "unclear":
            return {**_view(st), "transcript": text, "needs": "link"}
        conv.resolve_link(st, d == "yes")
        return {**_view(st), "transcript": text}
    conv.record_answer(st, text)   # stored RAW, unchanged
    return {**_view(st), "transcript": text}


@app.post("/api/session/{sid}/confirm")
def confirm(sid: str, body: dict):
    st = _get(sid)
    if st.stage != "confirm":
        raise HTTPException(409, "nothing awaiting confirmation")
    decision = conv.classify_confirm(body.get("utterance", ""), st.lang)
    if decision == "no":
        st.stage = "cancelled"
        return {**_view(st), "message": "Not posted. You can start again."}
    if decision != "yes":
        return {**_view(st), "message": "Please say yes or no.", "needs": "confirm"}
    from . import auth
    user_token = auth.get_proof_token(st.client)   # signed-in user's own Proof token, if they set one
    st.post_result = post_log(st.draft_verb, st.draft_content, st.draft_why, token=user_token)
    # remember this log so a future session can thread onto it (the 'next page of the story')
    log_id = ""
    try:
        log_id = (st.post_result.get("response", {}).get("result", {}) or {}).get("id", "")
    except Exception:
        pass
    history.record(st.draft_content, st.draft_verb, log_id, client=st.client)
    st.stage = "posted"
    return _view(st)


@app.get("/api/session/{sid}")
def get_session(sid: str):
    return _view(_get(sid))


@app.get("/api/tts")
def tts(text: str, lang: str = "en"):
    audio = synth(text, "ta" if lang == "ta" else "en")
    if audio is None:
        return Response(status_code=204)  # frontend uses speechSynthesis
    return Response(content=audio, media_type="audio/mpeg")


@app.get("/healthz")
def health():
    from .agent import history
    return {"ok": True, "posting": "per-user token only",
            "stt": os.getenv("STT_PROVIDER", "browser"), "llm": os.getenv("LLM_PROVIDER", "rule"),
            "tts": os.getenv("TTS_PROVIDER", "browser"), "db": history.db_status()}
