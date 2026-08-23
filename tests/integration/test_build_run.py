from __future__ import annotations

import base64
import json
from pathlib import Path
import re
import socket
import urllib.request

import pytest

import core.build as build_module
from core.launcher import Launcher
from core.models import ConflictError, DataError, ExternalError
from core.serve import create_server


def _prepare_game(launcher: Launcher, source: Path) -> None:
    launcher.install_version_directory(source, version_id="game")
    launcher.configure_instance("default", version_id="game")


def test_build_is_full_then_cache_hit(launcher: Launcher, make_version_dir) -> None:
    _prepare_game(launcher, make_version_dir())
    first = launcher.build("default")
    second = launcher.build("default")
    assert first.status == "full"
    assert second.status == "cache-hit"
    assert first.build_key == second.build_key


def test_build_injects_mods_in_instance_order(
    launcher: Launcher, make_version_dir, make_mod_zip
) -> None:
    base_html = (
        "<html><head><script>window.modDataValueZipList = "
        '["YnVpbHQtaW4="];</script></head></html>'
    )
    _prepare_game(launcher, make_version_dir(html=base_html))
    alpha = launcher.install_mod(str(make_mod_zip("alpha.zip", mod_name="Alpha")))
    beta = launcher.install_mod(str(make_mod_zip("beta.zip", mod_name="Beta")))
    launcher.enable_mod("default", alpha)
    launcher.enable_mod("default", beta)
    launcher.build("default")

    html = (launcher.root / "runtime" / "default" / "merged" / "index.html").read_text(
        encoding="utf-8"
    )
    match = re.search(r"window\.modDataValueZipList\s*=\s*(\[.*?\]);", html)
    assert match is not None
    values = json.loads(match.group(1))
    assert base64.b64decode(values[0]) == b"built-in"
    assert (
        base64.b64decode(values[1])
        == (launcher.mod(alpha).path / f"{alpha}.mod.zip").read_bytes()
    )
    assert (
        base64.b64decode(values[2])
        == (launcher.mod(beta).path / f"{beta}.mod.zip").read_bytes()
    )


def test_force_reinstall_same_id_invalidates_runtime(
    launcher: Launcher, make_version_dir
) -> None:
    _prepare_game(launcher, make_version_dir(asset="OLD", name="old"))
    launcher.build("default")
    launcher.install_version_directory(
        make_version_dir(asset="NEW", name="new"),
        version_id="game",
        force=True,
    )
    rebuilt = launcher.build("default")
    asset = launcher.root / "runtime" / "default" / "merged" / "game" / "asset.txt"
    assert rebuilt.status == "full"
    assert asset.read_text(encoding="utf-8") == "NEW"


def test_failed_rebuild_preserves_previous_runtime(
    launcher: Launcher,
    make_version_dir,
    make_mod_zip,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _prepare_game(launcher, make_version_dir(asset="stable"))
    launcher.build("default")
    mod_id = launcher.install_mod(str(make_mod_zip()))
    launcher.enable_mod("default", mod_id)

    def fail(_html: Path, _mods: list[Path]) -> None:
        raise OSError("injected build failure")

    monkeypatch.setattr(build_module, "_inject_mods_into_html", fail)
    with pytest.raises(ExternalError, match="injected build failure"):
        launcher.build("default")
    asset = launcher.root / "runtime" / "default" / "merged" / "game" / "asset.txt"
    assert asset.read_text(encoding="utf-8") == "stable"


def test_local_server_maps_root_to_real_entry(
    launcher: Launcher, make_version_dir
) -> None:
    _prepare_game(
        launcher,
        make_version_dir(entry="Degrees of Lewdity.html", html="<html>served</html>"),
    )
    launcher.build("default")
    session = launcher.prepare_serve("default", port=_free_port())
    session.start()
    try:
        body = urllib.request.urlopen(session.url, timeout=2).read().decode()
        assert "served" in body
    finally:
        session.stop()


def test_serve_rejects_stale_runtime(launcher: Launcher, make_version_dir) -> None:
    _prepare_game(launcher, make_version_dir(asset="old", name="old"))
    launcher.build("default")
    launcher.install_version_directory(
        make_version_dir(asset="new", name="new"),
        version_id="game",
        force=True,
    )
    with pytest.raises(DataError, match="stale"):
        launcher.prepare_serve("default", port=_free_port())


def test_server_falls_forward_only_when_allowed(tmp_path: Path) -> None:
    directory = tmp_path / "web"
    directory.mkdir()
    (directory / "index.html").write_text("ok", encoding="utf-8")
    occupied = socket.socket()
    occupied.bind(("127.0.0.1", 0))
    port = occupied.getsockname()[1]
    try:
        with pytest.raises(ConflictError, match="Port is already in use"):
            create_server(directory, port=port)
        handle = create_server(directory, port=port, allow_fallback=True)
        assert handle.port > port
        handle.close()
    finally:
        occupied.close()


def test_instance_launch_preferences_are_resolved(
    launcher: Launcher, make_version_dir
) -> None:
    _prepare_game(launcher, make_version_dir())
    port = _free_port()
    launcher.configure_instance("default", port=port, open_browser=False)
    session = launcher.prepare_run("default")
    try:
        assert session.port == port
        assert session.should_open_browser is False
    finally:
        session.close()


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])
