from __future__ import annotations

import hashlib
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from infra.net import download_file


@pytest.fixture
def http_server(tmp_path: Path):
    """Spin up a localhost HTTP server that serves a fixed payload with
    a Content-Length header and yields chunks small enough that the
    progress callback fires more than once."""
    payload = b"A" * (1024 * 64)  # 64 KiB

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            self.send_response(200)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            # Stream in 4 KiB chunks so iter_bytes() yields several times.
            for i in range(0, len(payload), 4096):
                self.wfile.write(payload[i : i + 4096])

        def log_message(self, *_a, **_kw):  # silence stderr
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield port, payload
    finally:
        server.shutdown()
        server.server_close()


class TestDownloadFileProgress:
    def test_callback_receives_total_and_grows_monotonically(
        self, http_server, tmp_path
    ) -> None:
        port, payload = http_server
        ticks: list[tuple[int, int | None]] = []

        sha = download_file(
            f"http://127.0.0.1:{port}/x.bin",
            tmp_path / "x.bin",
            progress=lambda d, t: ticks.append((d, t)),
        )

        assert (tmp_path / "x.bin").read_bytes() == payload
        assert sha == hashlib.sha256(payload).hexdigest()
        assert ticks, "progress callback never fired"
        # All ticks should know the total (server sent Content-Length)
        assert all(t == len(payload) for _, t in ticks)
        # Final downloaded byte count matches the payload size
        assert ticks[-1][0] == len(payload)
        # Monotonically non-decreasing
        for a, b in zip(ticks, ticks[1:]):
            assert a[0] <= b[0]

    def test_no_callback_still_works(self, http_server, tmp_path) -> None:
        """Regression guard: a missing progress callback must not raise."""
        port, payload = http_server
        download_file(f"http://127.0.0.1:{port}/x.bin", tmp_path / "y.bin")
        assert (tmp_path / "y.bin").read_bytes() == payload
