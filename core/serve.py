from __future__ import annotations

from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote

from infra.net import find_available_port, is_port_available
from core.models import DolCtlError


class _GameHandler(SimpleHTTPRequestHandler):
    """HTTP handler that maps ``/`` to the real entry HTML file.

    Also supports LAN access restriction: when *allow_lan* is ``False``
    (the default) only requests from ``127.0.0.1`` / ``::1`` are served;
    everything else gets a **403 Forbidden**.
    """

    # Set via functools.partial in create_server
    entry_name: str = "index.html"
    allow_lan: bool = False

    # ---- access control ----

    _LOCAL_ADDRS = {"127.0.0.1", "::1"}

    def _is_local(self) -> bool:
        addr = self.client_address[0]
        return addr in self._LOCAL_ADDRS

    def do_GET(self) -> None:  # noqa: N802
        if not self.allow_lan and not self._is_local():
            self.send_error(403, "Forbidden: LAN access is disabled")
            return
        super().do_GET()

    def do_HEAD(self) -> None:  # noqa: N802
        if not self.allow_lan and not self._is_local():
            self.send_error(403, "Forbidden: LAN access is disabled")
            return
        super().do_HEAD()

    # ---- URL rewrite: / → /entry.html ----

    def translate_path(self, path: str) -> str:
        # Redirect bare "/" to the actual entry file so the user sees a
        # clean URL instead of e.g. /Degrees%20of%20Lewdity.html
        if path == "/" or path == "":
            path = "/" + quote(self.entry_name)
        return super().translate_path(path)

    # ---- quiet logging ----

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return


def create_server(
    directory: Path,
    host: str = "127.0.0.1",
    port: int = 8799,
    allow_fallback: bool = False,
    entry_name: str = "index.html",
    allow_lan: bool = False,
) -> tuple[ThreadingHTTPServer, int]:
    if allow_fallback:
        chosen = find_available_port(host, port)
        if chosen is None:
            raise DolCtlError("No available port found")
    else:
        if not is_port_available(host, port):
            raise DolCtlError(f"Port is already in use: {port}")
        chosen = port

    # Create a handler subclass with the correct class-level settings.
    # functools.partial cannot be used for entry_name / allow_lan because
    # SimpleHTTPRequestHandler.__init__ does not accept extra kwargs.
    handler_cls = type(
        "_ConfiguredHandler",
        (_GameHandler,),
        {"entry_name": entry_name, "allow_lan": allow_lan},
    )
    handler = partial(handler_cls, directory=str(directory))
    server = ThreadingHTTPServer((host, chosen), handler)
    return server, chosen
