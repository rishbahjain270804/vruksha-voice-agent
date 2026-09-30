"""Generates the ONE contextual follow-up question.

Contract: given the raw answers (as read-only dicts), return a single question
STRING. This module has no access to the ConversationState and cannot alter any
stored transcript — it only reads. That is the 'LLM must not touch the transcript'
rule made structural.

Providers, chosen by LLM_PROVIDER: 'groq' | 'gemini' | 'rule' (default, zero-key).
Any provider failure falls back to the rule engine so the agent never stalls."""
from __future__ import annotations
import os, re
from typing import List, Dict

SYSTEM = (
    "You are interviewing a student about their day's work. Given their answers, ask exactly ONE "
    "short follow-up question about a specific choice or problem THEY mentioned — the way a sharp "
    "interviewer digs in. Reference their own words. Do not summarise, do not add commentary, output "
    "only the question. If they mentioned switching or choosing something, ask why that over the "
    "alternative. Keep it under 20 words. Answer in {lang}."
)


def make_followup(answers: List[Dict], lang: str = "en") -> str:
    provider = os.getenv("LLM_PROVIDER", "rule").lower()
    joined = "\n".join(f"Q: {a['question']}\nA: {a['transcript']}" for a in answers)
    try:
        if provider == "groq":
            return _groq(joined, lang)
        if provider == "gemini":
            return _gemini(joined, lang)
    except Exception as e:  # never stall the conversation on an API hiccup
        print(f"[followup] {provider} failed ({e}); using rule engine")
    return _rule(answers, lang)


def _groq(joined: str, lang: str) -> str:
    from groq import Groq
    c = Groq(api_key=os.environ["GROQ_API_KEY"])
    r = c.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "system", "content": SYSTEM.format(lang="Tamil" if lang == "ta" else "English")},
                  {"role": "user", "content": joined}],
        temperature=0.4, max_tokens=60)
    return r.choices[0].message.content.strip().strip('"')


def _gemini(joined: str, lang: str) -> str:
    import google.generativeai as genai
    genai.configure(api_key=os.environ["GEMINI_API_KEY"])
    m = genai.GenerativeModel("gemini-1.5-flash")
    r = m.generate_content(SYSTEM.format(lang="Tamil" if lang == "ta" else "English") + "\n\n" + joined)
    return r.text.strip().strip('"')


# --- zero-key fallback: extract the decision/object and ask about it -------------

_STOP = set("the a an i my we to of and or but so it that this for on in with was were is are be been "
            "today tried trying built build make made using use used because able".split())


def _rule(answers: List[Dict], lang: str) -> str:
    tried = answers[0]["transcript"] if answers else ""
    broke = answers[1]["transcript"] if len(answers) > 1 else ""
    low = f"{tried} {broke}".lower()

    # 1) explicit choice language -> "why that over the alternative"
    m = re.search(r"\b(switch(?:ed)?|chose|choose|pick(?:ed)?|used|moved to)\s+(?:to\s+|a\s+|an\s+|the\s+)?([a-z][a-z0-9 \-]{2,30})", low)
    if m:
        thing = m.group(2).strip().split(" and ")[0].strip()
        if lang == "ta":
            return f"நீங்கள் {thing} தேர்ந்தெடுத்தீர்கள் — வேறு விருப்பத்தை விட ஏன் அது?"
        return f"You chose {thing} — why that over the other option?"

    # 2) something broke -> what did you change / try when it broke
    if broke and not re.search(r"nothing|didn'?t break|no issue|worked fine", broke.lower()):
        subj = _keyword(broke) or _keyword(tried) or "that"
        if lang == "ta":
            return f"{subj} சிக்கல் வந்தபோது நீங்கள் எதை மாற்ற முயற்சித்தீர்கள்?"
        return f"What did you try changing when {subj} became a problem?"

    # 3) fallback: ask them to go one level deeper on the main thing they built
    subj = _keyword(tried) or "it"
    if lang == "ta":
        return f"{subj} பற்றி ஒரு கடினமான பகுதி எது?"
    return f"What was the hardest part of {subj}?"


def _keyword(text: str) -> str:
    """Pick the most salient term they said, not just the first word.
    Prefer a token that looks technical (has digits/caps/hyphen), else the longest
    non-stopword — so the question anchors on 'the check-in API', not on 'wanted'."""
    words = [w for w in re.findall(r"[a-zA-Z][a-zA-Z0-9\-]{2,}", text or "") if w.lower() not in _STOP]
    if not words:
        return ""
    techy = [w for w in words if re.search(r"[0-9A-Z\-]", w[1:])]   # CamelCase, api-v2, JWT, etc.
    return max(techy or words, key=len)
