import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from tools.loadtest import run_load


class Handler(BaseHTTPRequestHandler):
    def _send(self, code):
        body = b"{}"
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self._send(200)

    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length", 0)))
        self._send(401)

    def log_message(self, *args):
        pass


@pytest.fixture
def server():
    s = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    t = threading.Thread(target=s.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{s.server_address[1]}"
    s.shutdown()
    s.server_close()


def test_light_mode_counts_requests(server):
    stats = run_load(server, mode="light", workers=3, seconds=1)
    assert stats["total"] > 0
    assert stats["errors"] == 0
    assert stats["statuses"].get(200, 0) == stats["total"]
    assert stats["rps"] > 0
    assert stats["p95_ms"] >= stats["p50_ms"]


def test_cpu_mode_sends_wrong_logins_and_gets_401(server):
    stats = run_load(server, mode="cpu", workers=3, seconds=1)
    assert stats["total"] > 0
    assert stats["errors"] == 0
    assert stats["statuses"].get(401, 0) == stats["total"]


def test_dead_server_is_counted_as_errors():
    stats = run_load("http://127.0.0.1:9", mode="light", workers=2, seconds=1)
    assert stats["total"] > 0
    assert stats["errors"] == stats["total"]


@pytest.mark.parametrize(
    "kwargs",
    [{"workers": 0}, {"workers": 1000}, {"seconds": 0}, {"seconds": 5000}, {"mode": "evil"}],
)
def test_unsafe_settings_are_refused(kwargs):
    with pytest.raises(ValueError):
        run_load("http://127.0.0.1:9", **kwargs)