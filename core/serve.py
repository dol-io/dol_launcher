from __future__ import annotations

from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote

from infra.net import find_available_port, is_port_available
from core.models import DolCtlError


# Loopback addresses considered "local" for LAN access control.
_LOCAL_ADDRS = frozenset({"127.0.0.1", "::1"})


class _GameHandler(SimpleHTTPRequestHandler):
    """HTTP handler that maps ``/`` to the real entry HTML file and,
    unless explicitly opted-in via ``allow_lan``, rejects non-loopback
    requests with **403 Forbidden**.

    ``entry_name`` and ``allow_lan`` must be set on each concrete subclass
    before serving — see :func:`_build_handler_class`.
    """

    # Placeholders documenting the per-server configuration that
    # _build_handler_class supplies. Do *not* rely on these defaults at
    # runtime; the factory always provides the real values.
    entry_name: str
    allow_lan: bool

    def _is_local(self) -> bool:
        return self.client_address[0] in _LOCAL_ADDRS

    def _check_access(self) -> bool:
        if self.allow_lan or self._is_local():
            return True
        self.send_error(403, "Forbidden: LAN access is disabled")
        return False

    def do_GET(self) -> None:  # noqa: N802
        if self._check_access():
            super().do_GET()

    def do_HEAD(self) -> None:  # noqa: N802
        if self._check_access():
            super().do_HEAD()

    def translate_path(self, path: str) -> str:
        # Redirect bare "/" to the actual entry file so the user sees a
        # clean URL instead of e.g. /Degrees%20of%20Lewdity.html.
        if path in ("/", ""):
            path = "/" + quote(self.entry_name)
        return super().translate_path(path)

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return


def _build_handler_class(entry_name: str, allow_lan: bool) -> type[_GameHandler]:
    """Produce a per-server _GameHandler subclass with the right config.

    BaseHTTPServer instantiates the handler with a fixed
    ``(request, client_address, server)`` signature, so per-server
    configuration cannot be threaded through ``__init__`` arguments.
    ``functools.partial`` would handle the ``directory`` kwarg that
    ``SimpleHTTPRequestHandler.__init__`` *does* accept, but anything
    custom must live on the class.
    """
    return type(
        "_ConfiguredHandler",
        (_GameHandler,),
        {"entry_name": entry_name, "allow_lan": allow_lan},
    )


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

    handler_cls = _build_handler_class(entry_name, allow_lan)
    handler = partial(handler_cls, directory=str(directory))
    server = ThreadingHTTPServer((host, chosen), handler)
    return server, chosen
