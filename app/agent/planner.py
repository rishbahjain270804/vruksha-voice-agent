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
MAX_QUESTIONS = 5          # opener + up to 4 follow-ups; it usually stops earlier

# The interview targets exactly what Proof's curators reward (measured against the public corpus):
# a reason next to the decision, the alternative it was chosen OVER, one honest/skipped/risked thing,
# and a concrete artefact (file/error/number). Those markers are what separate a picked log from an
# ignored one — so we elicit them in the SPEAKER'S words; nothing is fabricated.
SYSTEM = (
    "You are a sharp, warm engineer interviewing a peer about ONE day of their work, for a public "
    "engineering log that founders read to judge how someone thinks. Read everything said so far and "
    "ask the SINGLE best next question, following their thread and quoting their own words — never a "
    "script. Across this short interview you are trying to surface what a strong log needs: "
    "(1) what they did, (2) the reason behind it (the 'because'), (3) what they chose it OVER (the "
    "alternative they rejected), and (4) one honest thing — what they skipped, what it cost, a risk, "
    "or a mistake. If an answer is vague, ask instead for ONE concrete detail: a file, an error, a "
    "number. One question, under 18 words, no preamble, no numbering. You have asked {n} of at most "
    "{maxq}. Reply with exactly DONE once you have the reason AND either the alternative or the honest/"
    "skipped part — do not pad. Reply in {lang}. Output only the question, or DONE."
)

# Proof's verb enum (from tools/list). The model labels the log; it never edits the transcript.
VERBS = ["built", "decided", "stuck", "mistake", "figure_out", "learned", "changed", "noticed",
         "thinking", "flagged", "thank", "assumed", "wonder", "ask", "freely", "nothing", "quiet"]


def choose_verb(answers: List[Dict], lang: str = "en") -> str:
    """Pick the Proof verb that best fits the log. LLM when available, else a transparent rule."""
    provider = os.getenv("LLM_PROVIDER", "rule").lower()
    text = " ".join(a.get("transcript", "") for a in answers)
    if provider in ("groq", "gemini"):
        try:
            v = _verb_llm(answers, provider)
            if v in VERBS:
                return v
        except Exception as e:
            print(f"[planner] verb {provider} failed ({e}); using rule")
    return _verb_rule(text)


def _verb_rule(text: str) -> str:
    t = text.lower()
    if re.search(r"\b(chose|choose|decided|instead of|over the|picked|went with|rather than)\b", t):
        return "decided"
    if re.search(r"\b(mistake|wrong|my bad|shouldn'?t have|messed up|broke it)\b", t):
        return "mistake"
    if re.search(r"\b(figured out|figured it|worked it out|cracked|got it working|fixed)\b", t):
        return "figure_out"
    if re.search(r"\b(stuck|blocked|can'?t get|couldn'?t|failing|error|crash|broke|not working)\b", t):
        return "stuck"
    if re.search(r"\b(learned|realis|realiz|understood|turns out|til\b)\b", t):
        return "learned"
    return "built"


def _verb_llm(answers: List[Dict], provider: str) -> str:
    convo = "\n".join(f"{a.get('question','')} -> {a.get('transcript','')}" for a in answers)
    prompt = ("Pick the ONE verb from this list that best fits the engineering log below: "
              + ", ".join(VERBS) + ". Reply with only the verb, lowercase, nothing else.\n\n" + convo)
    if provider == "groq":
        from groq import Groq
        c = Groq(api_key=os.environ["GROQ_API_KEY"])
        r = c.chat.completions.create(model=os.getenv("GROQ_MODEL", "openai/gpt-oss-120b"),
            messages=[{"role": "user", "content": prompt}],
            temperature=0, max_tokens=120, reasoning_effort="low")
        return r.choices[0].message.content.strip().lower().strip(".")
    import google.generativeai as genai
    genai.configure(api_key=os.environ["GEMINI_API_KEY"])
    m = genai.GenerativeModel("gemini-1.5-flash")
    return m.generate_content(prompt).text.strip().lower().strip(".")


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
    if not _asked(answers, "why", "reason"):
        return ("அதை ஏன் அப்படிச் செய்தீர்கள்?" if ta else "Why did you do it that way?")
    # 3) the alternative — what did you pick it over? (Proof rewards naming this)
    if not _asked(answers, "over", "instead", "alternative", "விட"):
        m = re.search(r"\b(switch(?:ed)?|chose|choose|pick(?:ed)?|used|moved to|went with)\s+(?:to\s+|a\s+|an\s+|the\s+)?([a-z][a-z0-9 \-]{2,30})",
                      " ".join(a["transcript"] for a in answers).lower())
        if m:
            thing = re.split(r"\s+(?:because|since|and|so|to|for|which|that|when|but)\b",
                             m.group(2).strip())[0].strip()
            return (f"{thing} — வேறு எதை விட அதைத் தேர்ந்தெடுத்தீர்கள்?" if ta else f"You went with {thing} — what did you pick it over?")
        return ("வேறு எந்த வழியை நீங்கள் தேர்ந்தெடுக்கவில்லை?" if ta else "What approach did you choose this over?")
    # 4) the honest/skipped line — what did it cost, or what did you leave out?
    if len(answers) < maxq:
        return ("நீங்கள் எதை விட்டுவிட்டீர்கள், அல்லது அது என்ன விலை கொடுத்தது?" if ta
                else "What did you skip or leave for later, or what did it cost?")
    return DONE
