"""Text-to-speech. Returns MP3 bytes, or None to tell the frontend to speak it itself
with the browser's speechSynthesis (zero cost). Providers by TTS_PROVIDER:
  browser -> None (frontend speaks)
  edge    -> Edge TTS (free, no key), Tamil + English voices."""
from __future__ import annotations
import os, asyncio

_VOICE = {"en": "en-US-AriaNeural", "ta": "ta-IN-PallaviNeural"}


def synth(text: str, lang: str = "en") -> bytes | None:
    provider = os.getenv("TTS_PROVIDER", "browser").lower()
    if provider == "browser" or not text:
        return None
    try:
        if provider == "edge":
            return asyncio.run(_edge(text, lang))
    except Exception as e:
        print(f"[speaker] {provider} failed ({e}); frontend will speak")
    return None


async def _edge(text: str, lang: str) -> bytes:
    import edge_tts
    comm = edge_tts.Communicate(text, _VOICE.get(lang, _VOICE["en"]))
    out = bytearray()
    async for chunk in comm.stream():
        if chunk["type"] == "audio":
            out.extend(chunk["data"])
    return bytes(out)
