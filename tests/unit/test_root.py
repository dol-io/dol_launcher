from __future__ import annotations

import os
from pathlib import Path

import pytest

from core.launcher import Launcher
from core.models import DataError, ValidationError
from core.root import load_config, resolve_root, validate_resource_name
from infra.fs import (
    atomic_write_text,
    remove_tree,
    replace_directory,
    staging_directory,
)
from infra.toml import write_toml


def test_initialise_creates_compatible_layout(launcher: Launcher) -> None:
    root = launcher.root
    for relative in (".dolctl", "versions", "mods", "profiles", "runtime"):
        assert (root / relative).is_dir()
    assert (root / "profiles" / "default" / "profile.toml").is_file()
    config = load_config(root)
    assert set(config.channels) == {"modloader"}
    assert config.channels["modloader"].kind == "game"
    assert config.default_port == 8799


def test_legacy_channel_without_kind_defaults_to_game(launcher: Launcher) -> None:
    write_toml(
        launcher.root / ".dolctl" / "config.toml",
        {
            "schema_version": 1,
            "channels": {
                "legacy": {
                    "provider": "github",
                    "repo": "owner/repository",
                    "asset_regex": r".*\.zip",
                }
            },
        },
    )
    assert load_config(launcher.root).channels["legacy"].kind == "game"


def test_resolve_root_walks_parents(
    launcher: Launcher, monkeypatch: pytest.MonkeyPatch
) -> None:
    nested = launcher.root / "one" / "two"
    nested.mkdir(parents=True)
    monkeypatch.chdir(nested)
    assert resolve_root() == launcher.root


def test_explicit_uninitialised_root_is_rejected(tmp_path: Path) -> None:
    candidate = tmp_path / "plain"
    candidate.mkdir()
    with pytest.raises(DataError, match="Not a dolctl root"):
        resolve_root(candidate)


@pytest.mark.parametrize(
    "value",
    [
        "",
        ".",
        "..",
        ".hidden",
        "../escape",
        "a/b",
        r"a\b",
        "/tmp/x",
        "C:drive",
        " x",
        "x ",
        "x\0y",
    ],
)
def test_resource_names_reject_unsafe_components(value: str) -> None:
    with pytest.raises(ValidationError):
        validate_resource_name(value)


@pytest.mark.parametrize("value", ["default", "my instance", "中文实例", "v1.2-rc1"])
def test_resource_names_accept_single_components(value: str) -> None:
    assert validate_resource_name(value) == value


def test_atomic_text_write_preserves_old_file_on_replace_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "state.toml"
    target.write_text("old", encoding="utf-8")

    def fail(_source: Path, _destination: Path) -> None:
        raise OSError("injected")

    monkeypatch.setattr(os, "replace", fail)
    with pytest.raises(OSError, match="injected"):
        atomic_write_text(target, "new")
    assert target.read_text(encoding="utf-8") == "old"
    assert list(tmp_path.glob(".state.toml.*.tmp")) == []


def test_directory_replacement_rolls_back(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    collection = tmp_path / "collection"
    destination = collection / "game"
    destination.mkdir(parents=True)
    (destination / "value").write_text("old", encoding="utf-8")
    staged = tmp_path / "staging" / "work" / "payload"
    staged.mkdir(parents=True)
    (staged / "value").write_text("new", encoding="utf-8")

    real_replace = os.replace
    calls = 0

    def flaky(source: Path, target: Path) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("publish failed")
        real_replace(source, target)

    monkeypatch.setattr(os, "replace", flaky)
    with pytest.raises(OSError, match="publish failed"):
        replace_directory(staged, destination, collection=collection, force=True)
    assert (destination / "value").read_text(encoding="utf-8") == "old"


def test_remove_tree_rejects_symlink_to_sibling(tmp_path: Path) -> None:
    collection = tmp_path / "collection"
    sibling = collection / "real"
    sibling.mkdir(parents=True)
    alias = collection / "alias"
    alias.symlink_to(sibling, target_is_directory=True)
    with pytest.raises(ValueError, match="symlinked"):
        remove_tree(alias, within=collection)
    assert sibling.is_dir()
    assert alias.is_symlink()


def test_replace_directory_rejects_symlink_destination(tmp_path: Path) -> None:
    collection = tmp_path / "collection"
    sibling = collection / "real"
    sibling.mkdir(parents=True)
    alias = collection / "alias"
    alias.symlink_to(sibling, target_is_directory=True)
    staged = tmp_path / "staging" / "work" / "payload"
    staged.mkdir(parents=True)
    with pytest.raises(ValueError, match="symlinked"):
        replace_directory(staged, alias, collection=collection, force=True)
    assert sibling.is_dir()


def test_launcher_rejects_symlinked_collection_and_doctor_reports_it(
    launcher: Launcher, tmp_path: Path
) -> None:
    profiles = launcher.root / "profiles"
    outside = tmp_path / "outside-profiles"
    profiles.rename(outside)
    profiles.symlink_to(outside, target_is_directory=True)

    with pytest.raises(DataError, match="cannot be a symlink"):
        launcher.configure_instance("default", port=9000)
    assert "port" not in (outside / "default" / "profile.toml").read_text()

    report = launcher.doctor()
    check = next(item for item in report.checks if item.key == "directory.profiles")
    assert not check.ok


def test_staging_rejects_symlinked_parent(launcher: Launcher, tmp_path: Path) -> None:
    staging = launcher.root / ".dolctl" / "staging"
    staging.rmdir()
    outside = tmp_path / "outside-staging"
    outside.mkdir()
    staging.symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="cannot be a symlink"):
        with staging_directory(launcher.root, "builds"):
            pass
    assert list(outside.iterdir()) == []
