from __future__ import annotations

import json
from pathlib import Path
import shutil
import zipfile

import pytest

import providers
from core.launcher import Launcher
from core.models import ConflictError, RemoteVersion, ValidationError


def test_import_reads_metadata_and_hashes_archive(
    launcher: Launcher, make_mod_zip
) -> None:
    mod_id = launcher.install_mod(str(make_mod_zip(mod_name="My Mod", version="2.0")))
    mod = launcher.mod(mod_id)
    assert mod.name == "My Mod"
    assert mod.version == "2.0"
    assert mod.author == "Tester"
    assert len(mod.sha256) == 64


def test_wrapped_mod_is_flattened(launcher: Launcher, make_mod_zip) -> None:
    mod_id = launcher.install_mod(str(make_mod_zip(wrapper="release")))
    archive = launcher.mod(mod_id).path / f"{mod_id}.mod.zip"
    with zipfile.ZipFile(archive) as handle:
        assert "boot.json" in handle.namelist()
        assert "release/boot.json" not in handle.namelist()


def test_missing_boot_json_is_rejected(launcher: Launcher, make_zip) -> None:
    archive = make_zip("invalid.zip", {"script.js": b"x"})
    with pytest.raises(ValidationError, match="boot.json"):
        launcher.install_mod(str(archive))


def test_wrapper_cannot_have_sibling_files(launcher: Launcher, make_zip) -> None:
    archive = make_zip(
        "invalid-wrapper.zip",
        {
            "wrapper/boot.json": json.dumps({"name": "Bad"}).encode(),
            "outside.js": b"x",
        },
    )
    with pytest.raises(ValidationError, match="outside"):
        launcher.install_mod(str(archive))


def test_duplicate_requires_force(launcher: Launcher, make_mod_zip) -> None:
    first = make_mod_zip("first.zip", mod_name="Same", version="1")
    mod_id = launcher.install_mod(str(first), mod_id="same")
    with pytest.raises(ConflictError):
        launcher.install_mod(str(first), mod_id=mod_id)
    second = make_mod_zip("second.zip", mod_name="Same", version="2")
    launcher.install_mod(str(second), mod_id=mod_id, force=True)
    assert launcher.mod(mod_id).version == "2"


def test_remove_mod_detaches_all_instances(launcher: Launcher, make_mod_zip) -> None:
    mod_id = launcher.install_mod(str(make_mod_zip()))
    launcher.enable_mod("default", mod_id)
    launcher.create_instance("other")
    launcher.enable_mod("other", mod_id)
    result = launcher.remove_mod(mod_id)
    assert result.affected_profiles == ("default", "other")
    assert launcher.instance("default").mod_order == []
    assert launcher.instance("other").mod_order == []


def test_remote_mod_install_uses_typed_channel_and_provider(
    launcher: Launcher,
    make_mod_zip,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_zip = make_mod_zip("DOLI.mod.zip", mod_name="DOLI", version="0.2.3")
    release = RemoteVersion(
        id="v0.2.3",
        display_name="DOLI v0.2.3",
        channel="doli",
        published_at="2026-03-28T00:00:00Z",
        asset_name="DOLI.mod.zip",
        download_url="https://example.invalid/DOLI.mod.zip",
        source_ref="https://example.invalid/releases/v0.2.3",
    )
    launcher.add_channel("doli", preset="doli")

    class FakeProvider:
        def list_versions(self) -> list[RemoteVersion]:
            return [release]

        def download(self, _release, destination, *, progress=None) -> str:
            shutil.copy2(source_zip, destination)
            if progress:
                progress(source_zip.stat().st_size, source_zip.stat().st_size)
            return "digest"

    monkeypatch.setattr(providers, "create_provider", lambda *_args: FakeProvider())
    ticks: list[tuple[int, int | None]] = []
    installed = launcher.install_remote_mod(
        "doli",
        progress=lambda done, total: ticks.append((done, total)),
    )
    mod = launcher.mod(installed)
    assert installed == "doli"
    assert mod.version == "0.2.3"
    assert mod.source == "remote"
    assert mod.source_ref == release.source_ref
    assert ticks


def test_remote_mod_listing_rejects_a_game_channel(launcher: Launcher) -> None:
    with pytest.raises(ValidationError, match="provides game archives"):
        launcher.remote_mods("modloader")


def test_absolute_mod_id_cannot_delete_external_directory(
    launcher: Launcher, tmp_path: Path
) -> None:
    outside = tmp_path / "outside-mod"
    outside.mkdir()
    with pytest.raises(ValidationError):
        launcher.remove_mod(str(outside))
    assert outside.is_dir()
