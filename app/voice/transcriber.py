"""Speech-to-text. Returns the transcript as the recogniser heard it. Providers by STT_PROVIDER:
  browser         -> return None; the frontend's Web Speech API already produced text (zero cost, noisy)
  groq            -> Groq-hosted Whisper large-v3 (needs GROQ_API_KEY; best quality + Tamil)
  faster_whisper  -> local Whisper model (offline, zero-key)
On any provider error, returns None so the caller can fall back to the browser transcript.

On fillers: Whisper is trained on clean transcripts and already omits most 'uh/um/hmm'. That is why
switching off browser STT fixes the noise without us editing the words. STRIP_FILLERS=1 removes any that
remain — off by default because the brief says word-for-word, so leave it off unless you decide otherwise."""
from __future__ import annotations
import os, re, tempfile

_FILLERS = re.compile(r"\b(uh+|um+|hmm+|erm*|ah+|uhh+|mm+|er)\b[\s,.]*", re.I)


def _whisper_lang(lang: str) -> str:
    from ..models.schemas import lang_cfg
    return lang_cfg(lang)["whisper"]


def _clean(text: str) -> str:
    """Always safe: trim + collapse whitespace. Never changes words. Optional filler removal on top."""
    if not text:
        return ""
    if os.getenv("STRIP_FILLERS", "0") == "1":
        text = _FILLERS.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


def transcribe(audio_bytes: bytes, lang: str = "en") -> str | None:
    provider = os.getenv("STT_PROVIDER", "browser").lower()
    if provider == "browser" or not audio_bytes:
        return None
    try:
        if provider == "groq":
            return _clean(_groq(audio_bytes, lang))
        if provider == "faster_whisper":
            return _clean(_faster_whisper(audio_bytes, lang))
    except Exception as e:
        print(f"[transcriber] {provider} failed ({e})")
        if provider == "groq":            # network/key issue — don't strand the user, decode locally
            try:
                print("[transcriber] falling back to local faster-whisper")
                return _clean(_faster_whisper(audio_bytes, lang))
            except Exception as e2:
                print(f"[transcriber] local fallback failed ({e2})")
    return None


def _groq(audio_bytes: bytes, lang: str) -> str:
    from groq import Groq
    c = Groq(api_key=os.environ["GROQ_API_KEY"])
    with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as f:
        f.write(audio_bytes); path = f.name
    try:
        with open(path, "rb") as fh:
            r = c.audio.transcriptions.create(
                file=(os.path.basename(path), fh.read()),
                model="whisper-large-v3",
                language=_whisper_lang(lang),
                # a light vocabulary hint so proper nouns survive (e.g. 'Vruksha', not 'ruksha').
                # It biases spelling only; it never adds words the speaker didn't say.
                prompt=os.getenv("STT_PROMPT",
                                 "An engineering work log. Terms may include: Vruksha, Proof, "
                                 "Groq, Whisper, Gemini, API, LLM, token, reasoning, transcription."),
                response_format="text")
        return (r if isinstance(r, str) else getattr(r, "text", "")).strip()
    finally:
        os.unlink(path)


_FW_MODEL = None


def _faster_whisper(audio_bytes: bytes, lang: str) -> str:
    global _FW_MODEL
    from faster_whisper import WhisperModel
    if _FW_MODEL is None:                       # load once, reuse (first call downloads the model)
        size = os.getenv("WHISPER_SIZE", "small")
        # CPU by default — GPU needs CUDA 12 + cuBLAS/cuDNN on PATH. Set WHISPER_DEVICE=cuda if you have them.
        dev = os.getenv("WHISPER_DEVICE", "cpu")
        try:
            _FW_MODEL = WhisperModel(size, device=dev, compute_type=("float16" if dev == "cuda" else "int8"))
            print(f"[transcriber] faster-whisper '{size}' on {dev}")
        except Exception:
            _FW_MODEL = WhisperModel(size, device="cpu", compute_type="int8")
            print(f"[transcriber] faster-whisper '{size}' on cpu (fallback)")
    with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as f:
        f.write(audio_bytes); path = f.name
    try:
        # condition_on_previous_text=False + a small no-speech guard trims hallucinated filler on short clips
        segments, _ = _FW_MODEL.transcribe(path, language=_whisper_lang(lang),
                                            vad_filter=True, condition_on_previous_text=False)
        return " ".join(s.text for s in segments).strip()
    finally:
        os.unlink(path)
