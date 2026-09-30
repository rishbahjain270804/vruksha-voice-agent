"""The adaptive interviewer. After each answer, it reads EVERYTHING the student has said
and decides the single best next question — or that it has learned enough (DONE).

This is the part that makes the agent 'think' instead of reading a fixed script. With
LLM_PROVIDER=groq|gemini a real model plans the questions and genuinely understands the
answers. With no key it falls back to a rule planner that still references the student's
own words, but cannot truly reason — that is the ceiling of a keyless build.

Hard rule preserved from the rest of the app: this module only ever returns a QUESTION
string (or the DONE sentinel). It never sees a way to rewrite a stored transcript."""
from __future__ import annotations
import os, re
from typing import List, Dict
from .followup import _keyword, _STOP
from ..models.schemas import lang_cfg

DONE = "__DONE__"
MAX_QUESTIONS = 4          # including the opening question, to keep it ~2 minutes

SYSTEM = (
    "You are a sharp, warm engineer talking to a peer about ONE day of their work, for a public "
    "engineering log. Read everything they have said so far and ask the SINGLE best next question "
    "that digs into what THEY actually said — quote their own words, follow their thread, do not "
    "read from a script. Before you are allowed to finish you must have learned three things: "
    "(1) what they worked on, (2) what was hard or what broke, (3) WHY they did it that way. "
    "One question only, under 18 words, no preamble, no numbering. You have already asked {n} "
    "question(s); you may ask at most {maxq}. If you already know the WHY and have enough for a "
    "real log, reply with exactly DONE. Reply in {lang}. Output only the question, or DONE."
)


def plan_next(answers: List[Dict], lang: str = "en", maxq: int = MAX_QUESTIONS) -> str:
    """Given the Q&A so far, return the next question — or DONE to move to the read-back."""
    if len(answers) >= maxq:
        return DONE
    provider = os.getenv("LLM_PROVIDER", "rule").lower()
    convo = "\n".join(f"Q{i+1}: {a['question']}\nA{i+1}: {a['transcript']}" for i, a in enumerate(answers))
    try:
        if provider == "groq":
            return _norm(_groq(convo, lang, len(answers), maxq))
        if provider == "gemini":
            return _norm(_gemini(convo, lang, len(answers), maxq))
    except Exception as e:
        print(f"[planner] {provider} failed ({e}); using rule planner")
    return _rule(answers, lang, maxq)


def _norm(q: str) -> str:
    q = (q or "").strip().strip('"').strip()
    return DONE if q.upper().replace(".", "").strip() == "DONE" else q


def _groq(convo: str, lang: str, n: int, maxq: int) -> str:
    from groq import Groq
    c = Groq(api_key=os.environ["GROQ_API_KEY"])
    r = c.chat.completions.create(
        model=os.getenv("GROQ_MODEL", "openai/gpt-oss-120b"),
        messages=[{"role": "system", "content": SYSTEM.format(n=n, maxq=maxq, lang=lang_cfg(lang)["llm"])},
                  {"role": "user", "content": convo}],
        # gpt-oss reasons before answering; without headroom + low effort the answer comes back empty
        temperature=0.5, max_tokens=300, reasoning_effort="low")
    return r.choices[0].message.content.strip()


def _gemini(convo: str, lang: str, n: int, maxq: int) -> str:
    import google.generativeai as genai
    genai.configure(api_key=os.environ["GEMINI_API_KEY"])
    m = genai.GenerativeModel("gemini-1.5-flash")
    r = m.generate_content(SYSTEM.format(n=n, maxq=maxq, lang=lang_cfg(lang)["llm"]) + "\n\n" + convo)
    return r.text.strip()


# ---- keyless fallback: references their words, but cannot truly reason ----

def _asked(answers: List[Dict], *needles: str) -> bool:
    qs = " ".join(a.get("question", "").lower() for a in answers)
    return any(nl in qs for nl in needles)


def _rule(answers: List[Dict], lang: str, maxq: int) -> str:
    last = answers[-1]["transcript"] if answers else ""
    term = _keyword(last) or _keyword(answers[0]["transcript"] if answers else "") or "that"
    ta = lang == "ta"

    # 1) learn what was hard / what broke, anchored on the thing they just named
    if not _asked(answers, "broke", "hard"):
        return (f"{term} பற்றி கடினமான பகுதி என்ன, அல்லது எது வேலை செய்யவில்லை?" if ta
                else f"What was the hard part of {term}, or what broke?")
    # 2) learn the why
    if not _asked(answers, "why"):
        return ("அதை ஏன் அப்படிச் செய்தீர்கள்?" if ta else "Why did you do it that way?")
    # 3) one dig-in on a decision they mentioned, then finish
    if len(answers) < maxq:
        m = re.search(r"\b(switch(?:ed)?|chose|choose|pick(?:ed)?|used|moved to|went with)\s+(?:to\s+|a\s+|an\s+|the\s+)?([a-z][a-z0-9 \-]{2,30})",
                      " ".join(a["transcript"] for a in answers).lower())
        if m:
            thing = re.split(r"\s+(?:because|since|and|so|to|for|which|that|when|but)\b",
                             m.group(2).strip())[0].strip()
            return (f"{thing} — வேறு விருப்பத்தை விட ஏன் அது?" if ta else f"You went with {thing} — why that over the other option?")
        return (f"{term} பற்றி இன்னும் ஒரு விஷயம் சொல்ல முடியுமா?" if ta else f"What's one more thing that mattered about {term}?")
    return DONE
