"""Text-to-speech. Returns MP3 bytes, or None to tell the frontend to speak it itself
with the browser's speechSynthesis (zero cost). Providers by TTS_PROVIDER:
  browser     -> None (frontend speaks)
  edge        -> Edge TTS (free, no key), Tamil + English voices
  elevenlabs  -> ElevenLabs neural TTS (needs ELEVENLABS_API_KEY); best quality + multilingual."""
from __future__ import annotations
import os, asyncio

_VOICE = {"en": "en-US-AriaNeural", "ta": "ta-IN-PallaviNeural"}


def synth(text: str, lang: str = "en") -> bytes | None:
    provider = os.getenv("TTS_PROVIDER", "browser").lower()
    if provider == "browser" or not text:
        return None
    try:
        if provider in ("elevenlabs", "eleven", "11labs"):
            return _eleven(text, lang)
        if provider == "edge":
            return asyncio.run(_edge(text, lang))
    except Exception as e:
        print(f"[speaker] {provider} failed ({e}); frontend will speak")
    return None


def _eleven(text: str, lang: str) -> bytes:
    """ElevenLabs REST TTS -> mp3 bytes. Multilingual model handles English and Tamil;
    the same voice speaks both, so no per-language voice switch is needed."""
    import httpx
    voice = os.getenv("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")   # 'Rachel', a default preset voice
    model = os.getenv("ELEVENLABS_MODEL", "eleven_multilingual_v2")
    r = httpx.post(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice}",
        headers={"xi-api-key": os.environ["ELEVENLABS_API_KEY"],
                 "accept": "audio/mpeg", "content-type": "application/json"},
        json={"text": text, "model_id": model,
              "voice_settings": {"stability": 0.5, "similarity_boost": 0.75}},
        timeout=30)
    r.raise_for_status()
    return r.content


async def _edge(text: str, lang: str) -> bytes:
    import edge_tts
    comm = edge_tts.Communicate(text, _VOICE.get(lang, _VOICE["en"]))
    out = bytearray()
    async for chunk in comm.stream():
        if chunk["type"] == "audio":
            out.extend(chunk["data"])
    return bytes(out)
