"""The conversation engine. It OWNS the raw transcripts and is the only thing that
writes them. The LLM (followup.py) is handed copies and can only return a question
string — there is no method here that lets anything but record_answer() change an
answer's transcript. That is how the 'LLM must not touch the transcript' rule is
enforced structurally, not by convention."""
from __future__ import annotations
import re
from .planner import plan_next, choose_verb, DONE
from . import history
from ..models.schemas import ConversationState, Answer, lang_cfg

# Phrases that mean "you already know what I'm talking about" — a reference back to earlier work.
_BACKREF = re.compile(
    r"\b(last|previous(?:ly)?|earlier|before|again|same|that (?:project|one|thing|app)|"
    r"the (?:project|one|app)|we (?:talk|discuss)|talk(?:ed|ing)? about|continu|already|like i said|you know)\b",
    re.I)


def next_prompt(st: ConversationState) -> str:
    """What the agent should SAY now, for the current stage."""
    cfg = lang_cfg(st.lang)
    if st.stage == "greet":
        return cfg["opener"]                  # the one fixed opener; everything after is planned
    if st.stage == "ask":
        return st.followup_question or ""     # the planner's next question
    if st.stage == "pick":
        names = [c.get("topic", "") for c in (st.topic_candidates or [])][:3]
        if len(names) == 1:
            return cfg["pick_one"].format(t=names[0])
        return cfg["pick_many"].format(list=", ".join(names))
    if st.stage == "link":
        topic = (st.related_topic or {}).get("topic", "something earlier")
        return cfg["link"].format(t=topic)
    if st.stage == "confirm":
        return cfg["confirm_pre"] + _read_back(st) + cfg["confirm_post"]
    return ""


def record_answer(st: ConversationState, transcript: str) -> None:
    """Store one raw answer and advance. transcript goes in UNCHANGED.

    Stage names describe the question just ASKED, so answering at stage 'greet'
    records the answer to Q1, and so on. Explicit rather than clever on purpose."""
    transcript = (transcript or "").strip()
    if st.stage == "greet":       # student just answered the opener ("what did you work on")
        st.answers.append(Answer(question=lang_cfg(st.lang)["opener"], transcript=transcript))
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
        tag = lang_cfg(st.lang)["cont_tag"].format(t=st.related_topic.get("topic"))
        st.draft_content = tag + (st.draft_content or "")
    st.stage = "confirm"


def classify_confirm(utterance: str, lang: str = "en") -> str:
    u = (utterance or "").strip().lower()
    cfg = lang_cfg(lang)
    if any(w.lower() in u for w in cfg["no"]):  # check NO first — "no, don't post" contains 'post'
        return "no"
    if any(w.lower() in u for w in cfg["yes"]):
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
        tag = lang_cfg(st.lang)["cont_tag"].format(t=st.continues.get("topic"))
        content = tag + content
    st.draft_content = content
    st.draft_why = why
    # verb chosen by the model from Proof's enum (labels the log; never edits the transcript),
    # with a transparent rule fallback.
    st.draft_verb = choose_verb([a.model_dump() for a in st.answers], st.lang)
