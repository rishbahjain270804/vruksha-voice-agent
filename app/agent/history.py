"""Recent-topic memory, so a new answer can be threaded onto an ongoing story instead of
always starting a fresh, disconnected log.

Source of 'recent topics': logs this agent has posted (persisted to sessions.json). Reading the
person's FULL Proof history would need a Proof read tool — call proof.client.tools_list() with a
token to see if one exists; if it does, feed it into recent() and this threads onto real logs too.
For now it threads onto what the agent itself recorded, which is enough to demo the flow."""
from __future__ import annotations
import json, re, os
from pathlib import Path
from typing import Optional

_STORE = Path(__file__).resolve().parent.parent.parent / "sessions.json"
_DB = os.getenv("DATABASE_URL", "").strip()   # Render Postgres when set; JSON file otherwise
_TABLE_READY = False
_STOP = set("the a an i we to of and or but so it that this for on in with was were is are be been my "
            "today tried trying built build make made using use used because able did do done my me you "
            "not no yes".split())


def _keywords(text: str) -> set[str]:
    return {w.lower() for w in re.findall(r"[a-zA-Z][a-zA-Z0-9\-]{3,}", text or "") if w.lower() not in _STOP}


# ---- storage: Postgres (persists across Render deploys) with a JSON-file fallback ----

def _connect():
    import psycopg
    dsn = _DB
    if dsn.startswith("postgres://"):            # normalise the scheme psycopg expects
        dsn = "postgresql://" + dsn[len("postgres://"):]
    return psycopg.connect(dsn, connect_timeout=10)


def _ensure(conn) -> None:
    global _TABLE_READY
    if _TABLE_READY:
        return
    with conn.cursor() as cur:
        cur.execute("""CREATE TABLE IF NOT EXISTS vruksha_logs (
            id bigserial PRIMARY KEY, topic text, keywords jsonb,
            verb text, snippet text, log_id text, client text, ts timestamptz DEFAULT now())""")
        cur.execute("ALTER TABLE vruksha_logs ADD COLUMN IF NOT EXISTS client text")  # for older tables
        cur.execute("UPDATE vruksha_logs SET client=lower(client) WHERE client <> lower(client)")  # case-fold
    conn.commit()
    _TABLE_READY = True


def db_status() -> str:
    """For /healthz: 'postgres' if the DB is wired and reachable, else 'file' (with the reason)."""
    if not _DB:
        return "file (no DATABASE_URL)"
    try:
        with _connect() as conn:
            _ensure(conn)
            with conn.cursor() as cur:
                cur.execute("SELECT count(*) FROM vruksha_logs")
                n = cur.fetchone()[0]
        return f"postgres ({n} logs)"
    except Exception as e:
        return f"file (pg error: {str(e)[:60]})"


def _file_load() -> list[dict]:
    try:
        return json.loads(_STORE.read_text(encoding="utf-8"))
    except Exception:
        return []


def _save(rows: list[dict]) -> None:
    try:
        _STORE.write_text(json.dumps(rows[-100:], ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception as e:
        print(f"[history] file save failed: {e}")


def _load() -> list[dict]:
    """All stored logs, oldest first. Postgres when configured, else the JSON file."""
    if _DB:
        try:
            with _connect() as conn:
                _ensure(conn)
                with conn.cursor() as cur:
                    cur.execute("SELECT topic, keywords, verb, snippet, log_id, client, ts "
                                "FROM vruksha_logs ORDER BY id ASC LIMIT 400")
                    return [{"topic": t, "keywords": kw or [], "verb": v, "snippet": s,
                             "id": lid or "", "client": cl or "", "ts": str(ts) if ts else ""}
                            for (t, kw, v, s, lid, cl, ts) in cur.fetchall()]
        except Exception as e:
            print(f"[history] pg load failed ({e}); using file")
    return _file_load()


def record(content: str, verb: str, log_id: str = "", ts: str = "", client: str = "") -> None:
    row = {"topic": topic_of(content), "keywords": sorted(_keywords(content)),
           "verb": verb, "snippet": content[:90], "id": log_id, "client": client, "ts": ts}
    if _DB:
        try:
            with _connect() as conn:
                _ensure(conn)
                with conn.cursor() as cur:
                    cur.execute("INSERT INTO vruksha_logs (topic, keywords, verb, snippet, log_id, client) "
                                "VALUES (%s, %s::jsonb, %s, %s, %s, %s)",
                                (row["topic"], json.dumps(row["keywords"]), verb, row["snippet"], log_id, client))
                conn.commit()
            return
        except Exception as e:
            print(f"[history] pg insert failed ({e}); using file")
    rows = _file_load()
    rows.append(row)
    _save(rows)


def topic_of(content: str) -> str:
    """A short human label for the log — the first salient noun-ish phrase."""
    kws = [w for w in re.findall(r"[a-zA-Z][a-zA-Z0-9\-]{3,}", content or "") if w.lower() not in _STOP]
    return " ".join(kws[:3]) if kws else "your work"


def _mine(rows: list[dict], client: str) -> list[dict]:
    """Only this browser's rows, so one tester's recall never leaks into another's."""
    return [r for r in rows if (r.get("client") or "") == (client or "")]


def list_logs(client: str, limit: int = 20) -> list[dict]:
    """This identity's logs, newest first, for the Account page's 'your recent logs' list."""
    return list(reversed(_mine(_load(), client)))[:limit]


def recent_topics(limit: int = 4, client: str = "") -> list[dict]:
    """The most recent DISTINCT projects THIS browser has logged, newest first.
    Used to ask 'which project do you mean?' when they refer back to earlier work."""
    out, seen = [], set()
    for row in reversed(_mine(_load(), client)):
        t = (row.get("topic") or "").strip()
        if t and t.lower() not in seen:
            seen.add(t.lower()); out.append(row)
        if len(out) >= limit:
            break
    return out


def match_topic(said: str, candidates: list[dict]) -> Optional[dict]:
    """Map what the student said ('the attendance one', 'the first', a project name) to a candidate.
    Returns None if they clearly mean something new / nothing matches."""
    low = (said or "").lower()
    if not candidates:
        return None
    if re.search(r"\b(new|different|another|fresh|none|neither|not that)\b", low):
        return None
    # ordinal / positional picks
    # note: NOT "one" — "the attendance one" means the attendance project, not position #1
    order = {0: ("first", "1st"), 1: ("second", "2nd"), 2: ("third", "3rd")}
    for idx, words in order.items():
        if idx < len(candidates) and any(re.search(rf"\b{w}\b", low) for w in words):
            return candidates[idx]
    if re.search(r"\b(last|previous|recent|latest)\b", low):
        return candidates[0]                      # newest
    # keyword / name overlap
    said_kw = _keywords(low)
    best, best_score = None, 0
    for c in candidates:
        score = len(said_kw & set(c.get("keywords", []))) \
                + sum(1 for w in c.get("topic", "").lower().split() if w in low)
        if score > best_score:
            best, best_score = c, score
    if best_score >= 1:
        return best
    # single candidate + a plain 'yes' -> they mean that one
    if len(candidates) == 1 and re.search(r"\b(yes|yeah|yep|same|that one|continue|continuing)\b", low):
        return candidates[0]
    return None


def related(content: str, min_overlap: int = 1, client: str = "") -> Optional[dict]:
    """Return the most-recent past log (THIS browser's) that shares a keyword with this answer.
    Threshold is 1 on purpose: asking 'is this the same X?' is cheap and the student can say no,
    so a near-miss that offers to thread is better UX than silently starting a disconnected log."""
    now = _keywords(content)
    best, best_score = None, 0
    for row in reversed(_mine(_load(), client)):   # most recent first
        overlap = len(now & set(row.get("keywords", [])))
        if overlap >= min_overlap and overlap > best_score:
            best, best_score = row, overlap
    return best
