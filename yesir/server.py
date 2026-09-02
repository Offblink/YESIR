"""Web server: ThreadingHTTPServer + NDJSON streaming + static files from web/."""

import json
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from yesir import session
from yesir.agent import SYSTEM_PROMPT
from yesir.config import load_config, save_config
from yesir.tools.ask import resolve_ask
from yesir.trilayer import TriLayer

WEB_DIR = Path(__file__).resolve().parent.parent / "web"

_mime = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json",
}


class WebSink:
    """Thread-safe NDJSON writer over the /chat response stream."""

    def __init__(self, handler: BaseHTTPRequestHandler) -> None:
        self._handler = handler
        self._lock = threading.Lock()
        self.closed = False

    def emit(self, event_type: str, content=None) -> None:
        if self.closed:
            return
        obj: dict = {"type": event_type}
        if content is not None:
            obj["content"] = content
        try:
            with self._lock:
                line = json.dumps(obj, ensure_ascii=False) + "\n"
                self._handler.wfile.write(line.encode("utf-8"))
                self._handler.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError) as exc:
            print(f"[websink] stream write failed: {type(exc).__name__}: {exc}", flush=True)
            self.closed = True


class YesSirHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    # ---- plumbing ---------------------------------------------------------
    def log_message(self, fmt, *args):  # quiet
        pass

    def _send_json(self, payload, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return {}
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return {}

    def _send_static(self, filename: str) -> None:
        path = WEB_DIR / filename
        if not path.is_file():
            self._send_json({"error": "not found"}, status=404)
            return
        body = path.read_bytes()
        mime = _mime.get(path.suffix, "application/octet-stream")
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    # ---- GET --------------------------------------------------------------
    def do_GET(self):
        url = urlparse(self.path)
        route = url.path
        if route == "/":
            self._send_static("index.html")
        elif route in ("/app.js", "/style.css"):
            self._send_static(route.lstrip("/"))
        elif route == "/model":
            self._send_json({"model": load_config().model})
        elif route == "/config-status":
            self._send_json({"configured": load_config().configured})
        elif route == "/sessions":
            self._send_json(session.list_sessions())
        elif route == "/session":
            session_id = (parse_qs(url.query).get("id") or [None])[0]
            data = session.load_session(session_id) if session_id else None
            if data is None:
                self._send_json({"error": "not found"}, status=404)
            else:
                self._send_json(data)
        else:
            self._send_json({"error": "not found"}, status=404)

    # ---- POST -------------------------------------------------------------
    def do_POST(self):
        url = urlparse(self.path)
        if url.path == "/chat":
            self._handle_chat()
        elif url.path == "/answer":
            data = self._read_body()
            value = data.get("value")
            if isinstance(value, list):
                value = [str(v) for v in value]
            else:
                value = str(value or "")
            ok = resolve_ask(str(data.get("id") or ""), value)
            self._send_json({"ok": ok}, status=200 if ok else 404)
        elif url.path == "/configure":
            data = self._read_body()
            cfg = load_config()
            if data.get("api_key"):
                cfg.api_key = data["api_key"]
            if data.get("endpoint"):
                cfg.endpoint = data["endpoint"]
            if data.get("model"):
                cfg.model = data["model"]
            save_config(cfg)
            self._send_json({"ok": True})
        elif url.path == "/save":
            data = self._read_body()
            existing = session.load_session(data.get("id", ""))
            if existing is None:
                self._send_json({"ok": False}, status=400)
                return
            session.save_session(
                data["id"],
                data.get("title") or existing.get("title") or "",
                existing.get("messages", []),
                subagents=existing.get("subagents", []),
                asks=existing.get("asks", []),
            )
            self._send_json({"ok": True})
        elif url.path == "/new":
            session_id = session.new_session_id()
            session.save_session(
                session_id, "(new session)", [{"role": "system", "content": SYSTEM_PROMPT}]
            )
            self._send_json({"id": session_id, "title": "(new session)"})
        elif url.path == "/pickfile":
            self._handle_pickfile()
        else:
            self._send_json({"error": "not found"}, status=404)

    # ---- DELETE -----------------------------------------------------------
    def do_DELETE(self):
        url = urlparse(self.path)
        if url.path == "/session":
            session_id = (parse_qs(url.query).get("id") or [None])[0]
            if session_id:
                session.delete_session(session_id)
            self._send_json({"ok": True})
        else:
            self._send_json({"error": "not found"}, status=404)

    # ---- long-running handlers --------------------------------------------
    def _handle_chat(self) -> None:
        data = self._read_body()
        user_msg = data.get("message", "")
        session_id = data.get("sessionId")

        stored = session.load_session(session_id) if session_id else None
        if stored:
            messages = list(stored["messages"])
        else:
            if not session_id:
                session_id = session.new_session_id()
            messages = [{"role": "system", "content": SYSTEM_PROMPT}]

        cfg = load_config()
        sink = WebSink(self)
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
        self.send_header("Connection", "close")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.close_connection = True
        try:
            messages.append({"role": "user", "content": user_msg})
            trilayer = TriLayer(cfg, sink)
            agent = trilayer.build_orchestrator(sink)
            agent.run(messages)
            prior = (stored or {}).get("subagents", []) if isinstance(stored, dict) else []
            merged = prior + list(trilayer.subagents.values())
            prior_asks = (stored or {}).get("asks", []) if isinstance(stored, dict) else []
            session.save_session(
                session_id,
                session.get_session_title(messages),
                messages,
                subagents=merged,
                asks=prior_asks + list(trilayer.asks),
            )
            sink.emit("sessionId", session_id)
            sink.emit("done", None)
        except Exception as exc:
            sink.emit("error", str(exc))
            sink.emit("done", None)
        finally:
            self.wfile.flush()

    def _handle_pickfile(self) -> None:
        try:
            import tkinter as tk  # noqa: PLC0415 (heavy GUI import, only on demand)
            from tkinter import filedialog  # noqa: PLC0415

            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            path = filedialog.askopenfilename(title="Select a file")
            root.destroy()
            self._send_json({"path": path or None})
        except Exception as exc:
            self._send_json({"path": None, "error": str(exc)})


def _free_port(preferred: int | None) -> int:
    port = preferred or 0
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", port))
        return sock.getsockname()[1]


def run_server(port: int | None = None) -> None:
    import webbrowser  # noqa: PLC0415 (only needed to open the browser)

    bound = _free_port(port)
    server = ThreadingHTTPServer(("127.0.0.1", bound), YesSirHandler)
    url = f"http://localhost:{bound}"
    print(f"  YESIR web UI: {url}")
    print("  Press Ctrl+C to stop")
    webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
