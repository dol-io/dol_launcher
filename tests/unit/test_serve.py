from __future__ import annotations

from urllib.parse import quote

import pytest

from core.serve import _build_handler_class


class _ResponseSpy:
    """Captures send_error / super().do_GET calls without a real socket."""

    def __init__(self, addr: str) -> None:
        self.client_address = (addr, 0)
        self.sent: list[tuple[int, str]] = []
        self.served: list[str] = []

    def send_error(self, code: int, message: str = "") -> None:
        self.sent.append((code, message))


def _make_handler(entry_name: str, allow_lan: bool, addr: str):
    cls = _build_handler_class(entry_name=entry_name, allow_lan=allow_lan)
    # Bypass __init__ (which would try to handle a request); construct
    # bare and graft the spy state on so the access-check methods can run.
    handler = cls.__new__(cls)
    spy = _ResponseSpy(addr)
    handler.client_address = spy.client_address
    handler.send_error = spy.send_error  # type: ignore[method-assign]
    return handler, spy


class TestAccessControl:
    @pytest.mark.parametrize("addr", ["127.0.0.1", "::1"])
    def test_local_allowed_when_lan_disabled(self, addr: str) -> None:
        handler, spy = _make_handler("index.html", allow_lan=False, addr=addr)
        assert handler._check_access() is True
        assert spy.sent == []

    @pytest.mark.parametrize("addr", ["192.168.1.5", "10.0.0.1", "fe80::1"])
    def test_remote_rejected_when_lan_disabled(self, addr: str) -> None:
        handler, spy = _make_handler("index.html", allow_lan=False, addr=addr)
        assert handler._check_access() is False
        assert spy.sent == [(403, "Forbidden: LAN access is disabled")]

    @pytest.mark.parametrize("addr", ["127.0.0.1", "192.168.1.5"])
    def test_lan_enabled_allows_anyone(self, addr: str) -> None:
        handler, spy = _make_handler("index.html", allow_lan=True, addr=addr)
        assert handler._check_access() is True
        assert spy.sent == []


class TestTranslatePath:
    def test_root_rewrites_to_entry(self, tmp_path) -> None:
        cls = _build_handler_class(entry_name="Degrees of Lewdity.html", allow_lan=False)
        # SimpleHTTPRequestHandler.translate_path needs the `directory` attr
        handler = cls.__new__(cls)
        handler.directory = str(tmp_path)
        # Build the expected filesystem path that translate_path would produce
        expected = str(tmp_path / "Degrees of Lewdity.html")
        translated = handler.translate_path("/")
        assert translated == expected

    def test_non_root_path_unchanged(self, tmp_path) -> None:
        cls = _build_handler_class(entry_name="index.html", allow_lan=False)
        handler = cls.__new__(cls)
        handler.directory = str(tmp_path)
        translated = handler.translate_path("/game/asset.txt")
        assert translated.endswith("/game/asset.txt")

    def test_entry_name_url_encoded_before_translation(self, tmp_path) -> None:
        # The entry name with spaces should be quoted before being fed to
        # the base class' translate_path implementation.
        cls = _build_handler_class(entry_name="space name.html", allow_lan=False)
        handler = cls.__new__(cls)
        handler.directory = str(tmp_path)
        translated = handler.translate_path("/")
        # The %20 url-encoding gets decoded by the base class when mapping
        # to the local filesystem, so we should see the literal space.
        assert translated.endswith("space name.html")
        # Sanity: confirm the quote helper actually encoded the input
        assert quote("space name.html") == "space%20name.html"
