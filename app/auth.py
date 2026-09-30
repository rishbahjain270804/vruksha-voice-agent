"""Optional account layer: a username + TOTP (an authenticator app) so a person can carry their
recall across devices without a password. If a user never sets this up, the app still works
anonymously (scoped to the browser's random code) — this only adds a way to reclaim memory.

Flow:
  setup(username)  -> reserves the name, returns an otpauth:// URI (rendered as a QR); the secret
                      is held PENDING (in memory) and only persisted once a valid code proves the
                      user actually scanned it, so an abandoned setup never squats a name.
  verify(user,code)-> for a persisted user, checks the code (Connect); for a pending user, checks
                      the code and, if valid, persists (enrolment). One path serves both.

Storage: Postgres when DATABASE_URL is set (survives redeploys), else a local JSON file.
The 6-digit code rotates every 30s in the user's app; we never store or transmit it, only verify."""
from __future__ import annotations
import os, re, json, time
from pathlib import Path

_DB = os.getenv("DATABASE_URL", "").strip()
_UFILE = Path(__file__).resolve().parent.parent / "users.json"
_READY = False
_PENDING: dict[str, tuple[str, float]] = {}   # username -> (secret, created_ts), pre-verification
_ATTEMPTS: dict[str, list[float]] = {}         # username -> recent verify timestamps (throttle)
_PENDING_TTL = 600                             # 10 min to scan + confirm
USERNAME_RE = re.compile(r"^[a-zA-Z0-9_.-]{3,32}$")


def _connect():
    import psycopg
    dsn = _DB
    if dsn.startswith("postgres://"):
        dsn = "postgresql://" + dsn[len("postgres://"):]
    return psycopg.connect(dsn, connect_timeout=10)


def _ensure(conn) -> None:
    global _READY
    if _READY:
        return
    with conn.cursor() as cur:
        cur.execute("CREATE TABLE IF NOT EXISTS vruksha_users ("
                    "username text PRIMARY KEY, secret text, created timestamptz DEFAULT now())")
    conn.commit()
    _READY = True


def _get_secret(username: str) -> str | None:
    if _DB:
        try:
            with _connect() as conn:
                _ensure(conn)
                with conn.cursor() as cur:
                    cur.execute("SELECT secret FROM vruksha_users WHERE username=%s", (username,))
                    row = cur.fetchone()
                    return row[0] if row else None
        except Exception as e:
            print(f"[auth] pg get failed ({e}); using file")
    try:
        return json.loads(_UFILE.read_text(encoding="utf-8")).get(username)
    except Exception:
        return None


def _put_secret(username: str, secret: str) -> bool:
    """Persist a new user; returns False if the name is already taken."""
    if _DB:
        try:
            with _connect() as conn:
                _ensure(conn)
                with conn.cursor() as cur:
                    cur.execute("INSERT INTO vruksha_users (username, secret) VALUES (%s, %s) "
                                "ON CONFLICT (username) DO NOTHING", (username, secret))
                    ok = cur.rowcount > 0
                conn.commit()
                return ok
        except Exception as e:
            print(f"[auth] pg put failed ({e}); using file")
    try:
        d = json.loads(_UFILE.read_text(encoding="utf-8"))
    except Exception:
        d = {}
    if username in d:
        return False
    d[username] = secret
    try:
        _UFILE.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        print(f"[auth] file put failed ({e})")
    return True


def taken(username: str) -> bool:
    return _get_secret(username) is not None


def setup(username: str) -> tuple[bool, str]:
    """Begin enrolment. Returns (ok, otpauth_uri) or (False, error message)."""
    import pyotp
    u = (username or "").strip()
    if not USERNAME_RE.match(u):
        return False, "username must be 3–32 chars (letters, numbers, . _ -)"
    if taken(u):
        return False, "that username is taken — use Connect instead"
    secret = pyotp.random_base32()
    _PENDING[u] = (secret, time.time())
    uri = pyotp.totp.TOTP(secret).provisioning_uri(name=u, issuer_name="Vruksha")
    return True, uri


def verify(username: str, code: str) -> bool:
    """True if the code is valid. Persists a pending enrolment on first success."""
    import pyotp
    u = (username or "").strip()
    c = re.sub(r"\D", "", code or "")
    if not u or len(c) < 6:
        return False
    now = time.time()
    tries = [t for t in _ATTEMPTS.get(u, []) if now - t < 300]
    if len(tries) >= 6:          # max 6 tries / 5 min per username
        return False
    tries.append(now)
    _ATTEMPTS[u] = tries

    stored = _get_secret(u)
    if stored:                                   # Connect: known user
        return pyotp.TOTP(stored).verify(c, valid_window=1)
    pend = _PENDING.get(u)                        # Enrol: pending user
    if pend and now - pend[1] < _PENDING_TTL:
        if pyotp.TOTP(pend[0]).verify(c, valid_window=1):
            _put_secret(u, pend[0])
            _PENDING.pop(u, None)
            return True
    return False
