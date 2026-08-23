from __future__ import annotations

from collections.abc import Callable
import itertools
import json
from pathlib import Path
import zipfile

import pytest

from core.launcher import Launcher


@pytest.fixture
def launcher(tmp_path: Path) -> Launcher:
    return Launcher.initialise(tmp_path / "root")


@pytest.fixture
def root(launcher: Launcher) -> Path:
    return launcher.root


@pytest.fixture
def make_version_dir(
    tmp_path: Path,
) -> Callable[..., Path]:
    counter = itertools.count()

    def make(
        *,
        entry: str = "index.html",
        html: str = "<html><head></head><body>game</body></html>",
        asset: str = "payload",
        name: str | None = None,
    ) -> Path:
        directory = tmp_path / (name or f"version-{next(counter)}")
        (directory / "game").mkdir(parents=True, exist_ok=True)
        (directory / entry).write_text(html, encoding="utf-8")
        (directory / "game" / "asset.txt").write_text(asset, encoding="utf-8")
        return directory

    return make


@pytest.fixture
def make_zip(tmp_path: Path) -> Callable[[str, dict[str, bytes]], Path]:
    def make(name: str, members: dict[str, bytes]) -> Path:
        path = tmp_path / name
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
            for member_name, content in members.items():
                archive.writestr(member_name, content)
        return path

    return make


@pytest.fixture
def make_version_zip(
    make_zip: Callable[[str, dict[str, bytes]], Path],
) -> Callable[..., Path]:
    def make(
        name: str = "game.zip",
        *,
        entry: str = "index.html",
        asset: bytes = b"payload",
    ) -> Path:
        return make_zip(
            name,
            {
                entry: b"<html><head></head><body>game</body></html>",
                "game/asset.txt": asset,
            },
        )

    return make


@pytest.fixture
def make_mod_zip(
    make_zip: Callable[[str, dict[str, bytes]], Path],
) -> Callable[..., Path]:
    def make(
        name: str = "sample.mod.zip",
        *,
        mod_name: str = "Sample",
        version: str = "1.0",
        wrapper: str | None = None,
        extra: dict[str, bytes] | None = None,
    ) -> Path:
        prefix = f"{wrapper}/" if wrapper else ""
        members = {
            f"{prefix}boot.json": json.dumps(
                {
                    "name": mod_name,
                    "version": version,
                    "author": "Tester",
                    "description": "Fixture mod",
                }
            ).encode(),
            f"{prefix}script.js": b"console.log('mod')",
        }
        members.update(extra or {})
        return make_zip(name, members)

    return make
