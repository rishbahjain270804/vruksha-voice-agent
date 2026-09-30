"""Proof log connector — POST /api/mcp, tool post_log.

Two safety rails baked in:
  • PROOF_DRY_RUN=1 (default) builds the exact JSON-RPC payload and returns it WITHOUT
    sending, so the 20-posts/day cap is never touched while developing.
  • the token is read from the environment only, never a literal, never logged.
"""
from __future__ import annotations
import os, json
import httpx

# The full enum the server accepts (from tools/list).
VALID_VERBS = {"built", "stuck", "mistake", "thinking", "decided", "nothing", "quiet", "changed",
               "flagged", "thank", "learned", "freely", "assumed", "noticed", "ask", "wonder",
               "figure_out", "interview"}


def _payload(verb: str, content: str, why: str, evidence_url: str = "") -> dict:
    if verb not in VALID_VERBS:
        verb = "built"
    args = {"verb": verb, "content": content, "why": why}
    if evidence_url:
        args["evidence_url"] = evidence_url
    return {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": "post_log", "arguments": args}}


def post_log(verb: str, content: str, why: str, evidence_url: str = "", token: str | None = None) -> dict:
    """Post one log, or, in dry-run, return the payload that WOULD be sent.
    If `token` is given (a signed-in user's own Proof token), post to THEIR record for real,
    regardless of the global dry-run switch; otherwise fall back to env token + dry-run rules."""
    base = os.getenv("PROOF_BASE", "https://proof.zeromaintenanceengineer.in")
    body = _payload(verb, content, why, evidence_url)
    if token:
        token, dry = token.strip(), False
    else:
        token = os.getenv("PROOF_TOKEN", "").strip()
        dry = os.getenv("PROOF_DRY_RUN", "1") != "0"

    if dry or not token:
        return {"dry_run": True, "reason": "PROOF_DRY_RUN" if dry else "no PROOF_TOKEN",
                "would_send": body, "endpoint": f"{base}/api/mcp"}

    try:
        r = httpx.post(f"{base}/api/mcp", json=body, timeout=30,
                       headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
        r.raise_for_status()
        return {"dry_run": False, "status": r.status_code, "response": _safe_json(r)}
    except Exception as e:
        # a wrong/expired token or a network blip shouldn't 500 the confirm — report it instead
        return {"dry_run": False, "ok": False, "error": str(e)[:160]}


def tools_list() -> dict:
    """One-off helper to see the real tool + verb list. Honours dry-run/token like post_log."""
    base = os.getenv("PROOF_BASE", "https://proof.zeromaintenanceengineer.in")
    token = os.getenv("PROOF_TOKEN", "").strip()
    if not token:
        return {"error": "set PROOF_TOKEN to call tools/list"}
    r = httpx.post(f"{base}/api/mcp", timeout=30,
                   headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                   json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    r.raise_for_status()
    return _safe_json(r)


def _safe_json(r) -> dict:
    try:
        return r.json()
    except Exception:
        return {"text": r.text[:500]}
