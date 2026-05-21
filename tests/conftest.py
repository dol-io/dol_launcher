from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import pytest

from core.root import init_root


@pytest.fixture
def root(tmp_path: Path) -> Path:
    init_root(tmp_path)
    return tmp_path


def _write_zip(path: Path, members: dict[str, bytes]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in members.items():
            zf.writestr(name, data)
    return path


@pytest.fixture
def make_zip(tmp_path: Path):
    def _make(name: str, members: dict[str, bytes]) -> Path:
        return _write_zip(tmp_path / name, members)

    return _make


@pytest.fixture
def make_mod_zip(tmp_path: Path):
    def _make(
        name: str,
        boot: dict | None = None,
        extra: dict[str, bytes] | None = None,
    ) -> Path:
        members: dict[str, bytes] = {}
        if boot is not None:
            members["boot.json"] = json.dumps(boot).encode("utf-8")
        if extra:
            members.update(extra)
        return _write_zip(tmp_path / name, members)

    return _make


@pytest.fixture
def make_version_dir(tmp_path: Path):
    """Return a factory that produces a fake DoL version directory tree."""

    def _make(entry: str = "index.html", body: str = "<html><head></head></html>") -> Path:
        version_dir = tmp_path / "fake_version"
        version_dir.mkdir(parents=True, exist_ok=True)
        (version_dir / entry).write_text(body, encoding="utf-8")
        (version_dir / "game").mkdir(exist_ok=True)
        (version_dir / "game" / "asset.txt").write_text("payload", encoding="utf-8")
        return version_dir

    return _make


@pytest.fixture
def make_version_zip(make_zip):
    """Build a minimal DoL-shaped zip with an index.html and game/ asset."""

    def _make(name: str = "dol.zip", *, entry: str = "index.html") -> Path:
        return make_zip(
            name,
            {
                entry: b"<html><head></head></html>",
                "game/asset.txt": b"payload",
            },
        )

    return _make


# Exposed helper for tests that want to bypass the fixture API
@pytest.fixture
def write_zip():
    return _write_zip


@pytest.fixture
def in_memory_zip():
    """Helper to construct a zip in a BytesIO buffer (used by some assertions)."""

    def _build(members: dict[str, bytes]) -> bytes:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for name, data in members.items():
                zf.writestr(name, data)
        return buf.getvalue()

    return _build
