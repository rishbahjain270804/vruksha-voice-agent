"""The conversation engine. It OWNS the raw transcripts and is the only thing that
writes them. The LLM (followup.py) is handed copies and can only return a question
string — there is no method here that lets anything but record_answer() change an
answer's transcript. That is how the 'LLM must not touch the transcript' rule is
enforced structurally, not by convention."""
from __future__ import annotations
import re
from .planner import plan_next, DONE
from . import history
from ..models.schemas import ConversationState, Answer, QUESTIONS, YES_WORDS, NO_WORDS

# Phrases that mean "you already know what I'm talking about" — a reference back to earlier work.
_BACKREF = re.compile(
    r"\b(last|previous(?:ly)?|earlier|before|again|same|that (?:project|one|thing|app)|"
    r"the (?:project|one|app)|we (?:talk|discuss)|talk(?:ed|ing)? about|continu|already|like i said|you know)\b",
    re.I)


def next_prompt(st: ConversationState) -> str:
    """What the agent should SAY now, for the current stage."""
    if st.stage == "greet":
        return QUESTIONS[st.lang][0]          # the one fixed opener; everything after is planned
    if st.stage == "ask":
        return st.followup_question or ""     # the planner's next question
    if st.stage == "pick":
        cands = st.topic_candidates or []
        names = [c.get("topic", "") for c in cands][:3]
        if st.lang == "ta":
            if len(names) == 1:
                return f"“{names[0]}” என்ற வேலையின் தொடர்ச்சியா, அல்லது புதிதா?"
            return "எந்த வேலை இது — " + ", ".join(names) + "? அல்லது புதிது?"
        if len(names) == 1:
            return f"Is this a continuation of “{names[0]}”, or something new?"
        return "Which project is this — " + ", or ".join(names) + "? Or say it's something new."
    if st.stage == "link":
        topic = (st.related_topic or {}).get("topic", "something earlier")
        if st.lang == "ta":
            return f"முன்பு நீங்கள் {topic} பற்றி பதிவு செய்தீர்கள். இது அதன் தொடர்ச்சியா? ஆம் அல்லது இல்லை."
        return f"Earlier you logged about {topic}. Is today part of that same work? Say yes or no."
    if st.stage == "confirm":
        pre = "Here is what I will post. " if st.lang == "en" else "நான் இதை பதிவு செய்யப் போகிறேன். "
        ask = " Should I post it? Say yes or no." if st.lang == "en" else " பதிவு செய்யட்டுமா? ஆம் அல்லது இல்லை என்று சொல்லுங்கள்."
        return pre + _read_back(st) + ask
    return ""


def record_answer(st: ConversationState, transcript: str) -> None:
    """Store one raw answer and advance. transcript goes in UNCHANGED.

    Stage names describe the question just ASKED, so answering at stage 'greet'
    records the answer to Q1, and so on. Explicit rather than clever on purpose."""
    transcript = (transcript or "").strip()
    if st.stage == "greet":       # student just answered the opener ("what did you work on")
        st.answers.append(Answer(question=QUESTIONS[st.lang][0], transcript=transcript))
        # Did they refer back to earlier work? If so, and we have earlier projects on file,
        # stop and ask WHICH one before going on — the human thing to do.
        cands = history.recent_topics()
        if cands and _BACKREF.search(transcript):
            st.topic_candidates = cands
            st.stage = "pick"
        else:
            _plan(st)             # let the interviewer choose the next question
    elif st.stage == "ask":       # answered a planned question
        st.answers.append(Answer(question=st.followup_question or "Follow-up", transcript=transcript))
        _plan(st)


def _plan(st: ConversationState) -> None:
    """Ask the planner for the next question, or wrap up if it says we have enough."""
    q = plan_next([a.model_dump() for a in st.answers], st.lang)
    if q and q != DONE:
        st.followup_question = q
        st.stage = "ask"
        return
    _build_draft(st)
    if st.continues:              # already tied to a project up front (the 'which one?' step)
        st.stage = "confirm"
    else:                         # maybe it silently continues an earlier log — offer to thread it
        st.related_topic = history.related(st.draft_content)
        st.stage = "link" if st.related_topic else "confirm"


def resolve_pick(st: ConversationState, said: str) -> None:
    """Answer to 'which earlier project is this?' — bind the chosen one, then keep interviewing."""
    chosen = history.match_topic(said, st.topic_candidates or [])
    if chosen:
        st.related_topic = chosen
        st.continues = chosen          # today's log threads onto this project
    st.topic_candidates = None
    _plan(st)


def resolve_link(st: ConversationState, said_yes: bool) -> None:
    """Answer to the 'is this a continuation?' question."""
    if said_yes and st.related_topic:
        st.continues = st.related_topic
        # a clear, consented continuation marker — the student hears it in the read-back.
        tag = f"(Continuing: {st.related_topic.get('topic')}) " if st.lang == "en" \
              else f"({st.related_topic.get('topic')} தொடர்ச்சி) "
        st.draft_content = tag + (st.draft_content or "")
    st.stage = "confirm"


def classify_confirm(utterance: str) -> str:
    u = (utterance or "").strip().lower()
    if any(w in u for w in NO_WORDS):  # check NO first — "no, don't post" contains 'post'
        return "no"
    if any(w in u for w in YES_WORDS):
        return "yes"
    return "unclear"


# ---- draft assembly: from RAW transcripts only, no LLM ----

# gpt-oss phrases the reason question freely ("what made you…", "what led you…"), so match intent,
# not just the word "why", or the reason falls through into the content blob.
_WHY_Q = re.compile(r"\b(why|reason|what made you|what led you|led you to|made you (?:choose|decide|pick|go)|"
                    r"drove you|ஏன்)\b", re.I)


def _is_why_question(q: str) -> bool:
    return bool(_WHY_Q.search(q or ""))


def _read_back(st: ConversationState) -> str:
    return st.draft_content or ""


def _infer_verb(what_tried: str, what_broke: str) -> str:
    """Cheap, transparent verb inference. Never fabricates content — only labels it."""
    b = what_broke.lower()
    if any(w in b for w in ("nothing", "didn't break", "did not break", "no issue", "worked")):
        return "built"
    if any(w in b for w in ("crash", "error", "broke", "fail", "bug", "not work", "didn't work")):
        return "stuck"
    t = what_tried.lower()
    if any(w in t for w in ("decided", "chose", "picked", "switched")):
        return "decided"
    return "built"


def _build_draft(st: ConversationState) -> None:
    """content/why/verb built ONLY from stored raw transcripts, in the student's words.
    Questions are planned, not fixed, so 'why' is found by meaning (the question that asks
    why), not by position — everything else becomes the content, in the order they said it."""
    why, content_parts = "", []
    for a in st.answers:
        if not why and _is_why_question(a.question):
            why = a.transcript                 # the answer to the why-question
        elif a.transcript:
            content_parts.append(a.transcript)
    content = "  ".join(content_parts)
    if st.continues:                    # project was chosen up front — mark the continuation
        topic = st.continues.get("topic")
        tag = f"(Continuing: {topic}) " if st.lang == "en" else f"({topic} தொடர்ச்சி) "
        content = tag + content
    st.draft_content = content
    st.draft_why = why
    # verb inferred from everything they said (their words scanned for broke/chose/etc.)
    st.draft_verb = _infer_verb(content, content)
