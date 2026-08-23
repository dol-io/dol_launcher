from __future__ import annotations

from pathlib import Path
import shutil

import pytest

import providers
from core.launcher import Launcher
from core.models import (
    ConflictError,
    ExternalError,
    NotFoundError,
    RemoteVersion,
    ValidationError,
)
from core.root import load_config, save_config
from core.versions import _make_version_id, _select_remote_version


def test_install_directory_and_list(launcher: Launcher, make_version_dir) -> None:
    version_id = launcher.install_version_directory(
        make_version_dir(entry="Degrees of Lewdity.html"),
        version_id="game",
    )
    assert version_id == "game"
    installed = launcher.version("game")
    assert installed.entry == "Degrees of Lewdity.html"
    assert [item.id for item in launcher.versions()] == ["game"]


def test_install_zip_strips_wrapper(launcher: Launcher, make_zip) -> None:
    archive = make_zip(
        "wrapped.zip",
        {
            "release/index.html": b"<html></html>",
            "release/game/asset.txt": b"payload",
        },
    )
    launcher.install_version_file(archive, version_id="wrapped")
    assert (launcher.version("wrapped").path / "index.html").is_file()


def test_local_filename_is_safely_normalised(
    launcher: Launcher, make_version_zip
) -> None:
    archive = make_version_zip("Degrees of Lewdity 1.2.zip")
    version_id = launcher.install_version_file(archive)
    assert "/" not in version_id
    assert " " not in version_id


def test_duplicate_requires_force_and_force_changes_revision(
    launcher: Launcher, make_version_dir
) -> None:
    first_source = make_version_dir(asset="old", name="old-source")
    launcher.install_version_directory(first_source, version_id="game")
    first_revision = launcher.version("game").revision
    with pytest.raises(ConflictError):
        launcher.install_version_directory(first_source, version_id="game")

    second_source = make_version_dir(asset="new", name="new-source")
    launcher.install_version_directory(second_source, version_id="game", force=True)
    assert launcher.version("game").revision != first_revision
    assert (launcher.version("game").path / "game" / "asset.txt").read_text() == "new"


def test_remove_referenced_version_requires_force(
    launcher: Launcher, make_version_dir
) -> None:
    launcher.install_version_directory(make_version_dir(), version_id="game")
    launcher.configure_instance("default", version_id="game")
    with pytest.raises(ConflictError, match="default"):
        launcher.remove_version("game")
    result = launcher.remove_version("game", force=True)
    assert result.affected_profiles == ("default",)
    assert launcher.instance("default").version_id == ""


def test_absolute_version_id_cannot_delete_external_directory(
    launcher: Launcher, tmp_path: Path
) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    with pytest.raises(ValidationError):
        launcher.remove_version(str(outside), force=True)
    assert outside.is_dir()


def test_prefixed_remote_selector_is_supported() -> None:
    release = RemoteVersion(
        id="v0.5.3",
        display_name="0.5.3",
        channel="vanilla",
        published_at="2026-01-01T00:00:00Z",
        asset_name="game.zip",
        download_url="https://example.invalid/game.zip",
        source_ref="https://example.invalid/release",
    )
    assert _select_remote_version([release], "vanilla-0.5.3", "vanilla") is release
    with pytest.raises(NotFoundError):
        _select_remote_version([release], "0.6.0", "vanilla")


def test_long_remote_ids_are_stably_shortened() -> None:
    remote_id = "release-" + "x" * 200
    first = _make_version_id("vanilla", remote_id)
    second = _make_version_id("vanilla", remote_id)
    assert first == second
    assert len(first) <= 128
    assert first.startswith("vanilla-release-")


def test_remote_listing_is_cached(
    launcher: Launcher, monkeypatch: pytest.MonkeyPatch
) -> None:
    release = RemoteVersion(
        id="1",
        display_name="One",
        channel="modloader",
        published_at="2026-01-01T00:00:00Z",
        asset_name="game.zip",
        download_url="https://example.invalid/game.zip",
        source_ref="https://example.invalid/release",
    )
    calls = 0

    class FakeProvider:
        def list_versions(self) -> list[RemoteVersion]:
            nonlocal calls
            calls += 1
            return [release]

    monkeypatch.setattr(providers, "create_provider", lambda *_args: FakeProvider())
    assert launcher.remote_versions("modloader") == [release]
    assert launcher.remote_versions("modloader") == [release]
    assert calls == 1

    config = load_config(launcher.root)
    config.channels["modloader"].repo = "example/changed"
    save_config(launcher.root, config)
    assert launcher.remote_versions("modloader") == [release]
    assert calls == 2


def test_remote_install_uses_provider_contract(
    launcher: Launcher,
    make_version_zip,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_zip = make_version_zip("remote.zip", asset=b"remote")
    release = RemoteVersion(
        id="v1.0",
        display_name="Remote 1.0",
        channel="modloader",
        published_at="2026-01-01T00:00:00Z",
        asset_name="remote.zip",
        download_url="https://example.invalid/remote.zip",
        source_ref="https://example.invalid/release",
    )

    class FakeProvider:
        def list_versions(self) -> list[RemoteVersion]:
            return [release]

        def download(self, _version, destination, *, progress=None) -> str:
            shutil.copy2(source_zip, destination)
            if progress:
                progress(source_zip.stat().st_size, source_zip.stat().st_size)
            return "digest"

    monkeypatch.setattr(providers, "create_provider", lambda *_args: FakeProvider())
    ticks: list[tuple[int, int | None]] = []
    installed = launcher.install_remote_version(
        "modloader",
        "modloader-1.0",
        progress=lambda done, total: ticks.append((done, total)),
    )
    assert installed == "modloader-v1.0"
    assert ticks
    assert (
        launcher.version(installed).path / "game" / "asset.txt"
    ).read_bytes() == b"remote"


def test_invalid_zip_has_user_facing_error(launcher: Launcher, tmp_path: Path) -> None:
    invalid = tmp_path / "bad.zip"
    invalid.write_bytes(b"not a zip")
    with pytest.raises(ExternalError, match="Could not install"):
        launcher.install_version_file(invalid, version_id="bad")
