"""Local JSON API and review UI, on loopback only.

`brain serve` starts it on 127.0.0.1 with a random port and a random token, and
opens the UI. Every /api call must carry the token (header `X-Brain-Token`), so another page
in the browser cannot drive it. It runs as the brain's owner, which is what makes approving
proposals here legitimate: this is the human surface.

The same endpoints are the integration point for an application that embeds the brain over
HTTP instead of importing `brainkit` directly.

    GET  /api/status              counts, health summary
    GET  /api/health              full health report
    GET  /api/inbox               pending proposals
    POST /api/inbox/decide        {"decisions": [{"id", "action", "reason", "edits", "body"}]}
    GET  /api/focus               Focus list;  GET /api/focus/<id>  one Focus
    POST /api/focus               {"name", "summary", "status"}
    POST /api/focus/<id>/update   {"summary", "changes", "evidence"}
    GET  /api/topics              topics with note counts
    GET  /api/notes?q=...         search;  GET /api/notes/<id>  one note
    POST /api/notes               propose {"area","topic","title","summary","kind","text",
                                  "scope",...}; "apply": true also approves it (owner only)
    POST /api/files               {"filename", "content_base64" | "content", "title",
                                  "description", "purpose", "topic"}: propose a document or
                                  asset; "apply": true also approves it (owner only)
    POST /api/skills              {"name", "category", "description", "body", "files", ...}
                                  propose a skill or, with "target", a change to one
    POST /api/sync                sweep the drop and skill folders now
    POST /api/context             {"request", "explain"}: packet preview, not recorded
    GET  /api/decisions           recent governance decisions
    GET  /api/sessions            recent sessions
"""
from __future__ import annotations

import json
import os
import secrets
import threading
import urllib.parse
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

UI_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ui")
# A 10 MB file is about 13.4 MB as base64 in JSON; a skill may carry several.
MAX_BODY = 36 * 1024 * 1024
TOO_LARGE = object()


def _json_default(value):
    if hasattr(value, "__dict__"):
        return value.__dict__
    return str(value)


def make_handler(brain, token):
    from . import health

    class Handler(BaseHTTPRequestHandler):
        server_version = "brain/2"

        def log_message(self, fmt, *args):  # quiet by default
            if os.environ.get("BRAIN_HTTP_LOG"):
                super().log_message(fmt, *args)

        # ---------------------------------------------------------- plumbing
        def _send(self, status, payload, content_type="application/json"):
            body = payload if isinstance(payload, bytes) else json.dumps(
                payload, ensure_ascii=False, default=_json_default).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def _result(self, result):
            status = HTTPStatus.OK if not result.is_error else HTTPStatus.BAD_REQUEST
            self._send(status, result.as_dict())

        def _authorized(self):
            supplied = self.headers.get("X-Brain-Token") or ""
            return secrets.compare_digest(supplied, token)

        def _maybe_apply(self, result, payload):
            """The owner's own upload may be approved in the same step ("apply": true)."""
            if (payload.get("apply") and not result.is_error
                    and result.data.get("status") == "pending"):
                return brain.approve(result.data["proposal_id"])
            return result

        def _body(self):
            length = int(self.headers.get("Content-Length") or 0)
            if length <= 0:
                return {}
            if length > MAX_BODY:
                return TOO_LARGE
            try:
                return json.loads(self.rfile.read(length).decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                return None

        def _static(self, path):
            name = "index.html" if path in ("", "/") else path.lstrip("/")
            if "/" in name or name.startswith("."):
                return self._send(HTTPStatus.NOT_FOUND, {"error": "not found"})
            full = os.path.join(UI_DIR, name)
            if not os.path.isfile(full):
                return self._send(HTTPStatus.NOT_FOUND, {"error": "not found"})
            kind = {"html": "text/html; charset=utf-8", "js": "text/javascript; charset=utf-8",
                    "css": "text/css; charset=utf-8"}.get(name.rsplit(".", 1)[-1],
                                                          "application/octet-stream")
            with open(full, "rb") as handle:
                self._send(HTTPStatus.OK, handle.read(), kind)

        # ---------------------------------------------------------- routes
        def do_GET(self):
            url = urllib.parse.urlparse(self.path)
            if not url.path.startswith("/api/"):
                return self._static(url.path)
            if not self._authorized():
                return self._send(HTTPStatus.UNAUTHORIZED, {"error": "missing or bad token"})
            query = urllib.parse.parse_qs(url.query)
            parts = [urllib.parse.unquote(p) for p in url.path.split("/")[2:] if p]
            try:
                if parts == ["status"]:
                    report = brain.health()
                    st = brain.state()
                    return self._send(HTTPStatus.OK, {
                        "name": st.config.name, "owner": st.config.owner,
                        "line": health.status_line(brain), "ok": report.data.get("ok"),
                        "problems": len(report.data.get("problems") or []),
                        "warnings": len(report.data.get("warnings") or []),
                        "pending": len(st.snapshot.proposals),
                        "notes": len(st.index.notes), "skills": len(st.index.skills),
                        "focuses": len(st.index.focuses),
                        "kernel": report.data.get("kernel_fingerprint")})
                if parts == ["health"]:
                    return self._result(brain.health())
                if parts == ["inbox"]:
                    return self._result(brain.inbox())
                if parts == ["focus"]:
                    return self._result(brain.focus_list())
                if len(parts) == 2 and parts[0] == "focus":
                    return self._result(brain.focus_get(parts[1]))
                if parts == ["topics"]:
                    return self._result(brain.topics())
                if parts == ["notes"]:
                    text = " ".join(query.get("q") or [])
                    topic = (query.get("topic") or [None])[0]
                    if topic:
                        return self._result(brain.topic(topic))
                    return self._result(brain.search(text or "", limit=50,
                                                     include_archived=bool(query.get("archived"))))
                if len(parts) == 2 and parts[0] == "notes":
                    return self._result(brain.note(parts[1], include_archived=True))
                if parts == ["decisions"]:
                    rows = brain.vault.decisions()[-100:][::-1]
                    return self._send(HTTPStatus.OK, {"decisions": rows})
                if parts == ["sessions"]:
                    return self._send(HTTPStatus.OK,
                                      {"sessions": brain.ledger.recent_sessions(30)})
            except Exception as exc:
                return self._send(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
            return self._send(HTTPStatus.NOT_FOUND, {"error": "no such endpoint"})

        def do_POST(self):
            url = urllib.parse.urlparse(self.path)
            if not url.path.startswith("/api/") or not self._authorized():
                return self._send(HTTPStatus.UNAUTHORIZED, {"error": "missing or bad token"})
            payload = self._body()
            if payload is TOO_LARGE:
                return self._send(HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                                  {"error": f"body over {MAX_BODY // (1024 * 1024)} MB"})
            if payload is None:
                return self._send(HTTPStatus.BAD_REQUEST, {"error": "body must be JSON"})
            parts = [urllib.parse.unquote(p) for p in url.path.split("/")[2:] if p]
            try:
                if parts == ["inbox", "decide"]:
                    return self._result(brain.decide(payload.get("decisions")))
                if parts == ["focus"]:
                    return self._result(brain.focus_create(
                        payload.get("name"), payload.get("summary"),
                        status=payload.get("status") or "active"))
                if len(parts) == 3 and parts[0] == "focus" and parts[2] == "update":
                    return self._result(brain.focus_update(
                        parts[1], payload.get("summary"), payload.get("changes") or {},
                        evidence=payload.get("evidence") or ""))
                if parts == ["notes"]:
                    result = brain.propose(
                        area=payload.get("area") or payload.get("layer"),
                        topic=payload.get("topic"), title=payload.get("title"),
                        summary=payload.get("summary"), note_kind=payload.get("kind"),
                        text=payload.get("text"), scope=payload.get("scope"),
                        load=payload.get("load") or "on-demand",
                        evidence=payload.get("evidence") or "", source=payload.get("source")
                        or "owner edit in the local UI", target_id=payload.get("target_id"),
                        archive=bool(payload.get("archive")), reason=payload.get("reason") or "",
                        applies_to=payload.get("applies_to") or None,
                        triggers=payload.get("triggers") or None,
                        must_text=payload.get("must_text") or None,
                        critical=payload.get("critical"),
                        as_of=payload.get("as_of") or None,
                        valid_until=payload.get("valid_until") or None)
                    if (payload.get("apply") and not result.is_error
                            and result.data.get("status") == "pending"):
                        return self._result(brain.approve(result.data["proposal_id"]))
                    return self._result(result)
                if parts == ["files"]:
                    result = brain.add_file(
                        filename=payload.get("filename"), content=payload.get("content"),
                        content_base64=payload.get("content_base64"),
                        title=payload.get("title"), description=payload.get("description") or "",
                        purpose=payload.get("purpose"), topic=payload.get("topic"),
                        source=payload.get("source") or "owner upload in the local UI")
                    return self._result(self._maybe_apply(result, payload))
                if parts == ["skills"]:
                    result = brain.propose_skill(
                        name=payload.get("name"), category=payload.get("category"),
                        description=payload.get("description"), body=payload.get("body"),
                        when_to_use=payload.get("when_to_use"),
                        triggers=payload.get("triggers"), loads=payload.get("loads"),
                        files=payload.get("files"), target=payload.get("target"),
                        scope=payload.get("scope"),
                        source=payload.get("source") or "owner upload in the local UI")
                    return self._result(self._maybe_apply(result, payload))
                if parts == ["sync"]:
                    return self._result(brain.sync())
                if parts == ["context"]:
                    return self._result(brain.context(
                        payload.get("request") or "", explain=bool(payload.get("explain", True)),
                        focus=payload.get("focus"), partition=payload.get("partition"),
                        principal=payload.get("principal"), record=False,
                        include_kernel=bool(payload.get("include_kernel", False))))
            except Exception as exc:
                return self._send(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
            return self._send(HTTPStatus.NOT_FOUND, {"error": "no such endpoint"})

    return Handler


def start(brain, port=0):
    """Start in a background thread. Returns (server, url, token)."""
    token = secrets.token_urlsafe(24)
    server = ThreadingHTTPServer(("127.0.0.1", int(port or 0)), make_handler(brain, token))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_address[1]}/#token={token}"
    return server, url, token


def serve(brain, port=0, open_browser=True) -> int:
    server, url, _token = start(brain, port)
    print(f"Brain UI: {url}", flush=True)
    print("Loopback only. Ctrl+C to stop.", flush=True)
    if open_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
    return 0
