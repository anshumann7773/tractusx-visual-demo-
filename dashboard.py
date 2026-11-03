"""
Live dashboard for the demo: a tiny web server (Python standard library only)
that serves dashboard.html and streams the demo's steps to the browser.

demo.py calls dashboard.start() once and dashboard.emit(...) at every step.
The browser listens on /events (Server-Sent Events) and animates what happens.
"""

import json
import threading
import time
import uuid
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

PORT = 8765
URL = f"http://localhost:{PORT}"
HTML_FILE = Path(__file__).with_name("dashboard.html")

_page = HTML_FILE
_events = []
_cond = threading.Condition()
_clients = 0
_run_id = uuid.uuid4().hex


def emit(kind, **data):
    """Send one event to every open dashboard page."""
    with _cond:
        _events.append({"i": len(_events), "t": time.time(), "type": kind, **data})
        _cond.notify_all()


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass  # keep the terminal clean

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            body = _page.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/events":
            self._stream()
        else:
            self.send_error(404)

    def _stream(self):
        global _clients
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        with _cond:
            _clients += 1
        sent = 0
        try:
            while True:
                with _cond:
                    if sent >= len(_events):
                        _cond.wait(timeout=15)
                    new = _events[sent:]
                if not new:
                    self.wfile.write(b": keep-alive\n\n")  # stops the browser from timing out
                for event in new:
                    payload = json.dumps({"run": _run_id, "page": _page.name, "now": time.time(), **event})
                    self.wfile.write(f"data: {payload}\n\n".encode())
                sent += len(new)
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            with _cond:
                _clients -= 1


def start(open_browser=True, page="dashboard.html"):
    """Start the dashboard in the background. Returns the URL, or None if it could not start.

    page = which screen to serve (each KIT demo can have its own layout)."""
    global _page
    _page = HTML_FILE.with_name(page)
    try:
        server = ThreadingHTTPServer(("127.0.0.1", PORT), _Handler)
    except OSError:
        return None  # port busy: the demo still runs, just without the dashboard
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    emit("hello")
    if open_browser:
        # An already open dashboard tab reconnects by itself within a few seconds.
        # Only open a new tab if none came back.
        def maybe_open():
            time.sleep(4)
            with _cond:
                connected = _clients > 0
            if not connected:
                webbrowser.open(URL)
        threading.Thread(target=maybe_open, daemon=True).start()
    return URL
