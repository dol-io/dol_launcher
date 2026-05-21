from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from infra.zip import extract_zip, _safe_member_path


class TestSafeMemberPath:
    def test_normal_path_resolves_under_dest(self, tmp_path: Path) -> None:
        target = _safe_member_path(tmp_path, "a/b/c.txt")
        assert target == (tmp_path / "a" / "b" / "c.txt").resolve()

    def test_normalises_backslashes(self, tmp_path: Path) -> None:
        target = _safe_member_path(tmp_path, "a\\b.txt")
        assert target == (tmp_path / "a" / "b.txt").resolve()

    @pytest.mark.parametrize(
        "name",
        [
            "../escape.txt",
            "a/../../escape.txt",
            "/etc/passwd",
            "C:/Windows/system32",
        ],
    )
    def test_rejects_traversal_and_absolute(self, tmp_path: Path, name: str) -> None:
        with pytest.raises(ValueError):
            _safe_member_path(tmp_path, name)


class TestExtractZip:
    def test_extracts_files(self, tmp_path: Path) -> None:
        src = tmp_path / "in.zip"
        with zipfile.ZipFile(src, "w") as zf:
            zf.writestr("a/hello.txt", b"hi")
            zf.writestr("b/nested/x.bin", b"\x00\x01\x02")

        dest = tmp_path / "out"
        extract_zip(src, dest)

        assert (dest / "a" / "hello.txt").read_bytes() == b"hi"
        assert (dest / "b" / "nested" / "x.bin").read_bytes() == b"\x00\x01\x02"

    def test_zip_slip_blocked(self, tmp_path: Path) -> None:
        src = tmp_path / "evil.zip"
        with zipfile.ZipFile(src, "w") as zf:
            zf.writestr("../escape.txt", b"pwned")

        dest = tmp_path / "out"
        with pytest.raises(ValueError):
            extract_zip(src, dest)

        # Sibling file must not have been created
        assert not (tmp_path / "escape.txt").exists()

    def test_strip_single_dir_pulls_inner_contents_up(self, tmp_path: Path) -> None:
        src = tmp_path / "in.zip"
        with zipfile.ZipFile(src, "w") as zf:
            zf.writestr("wrapper/index.html", b"<html></html>")
            zf.writestr("wrapper/game/a.txt", b"a")

        dest = tmp_path / "out"
        extract_zip(src, dest, strip_single_dir=True)

        assert (dest / "index.html").exists()
        assert (dest / "game" / "a.txt").read_bytes() == b"a"
        assert not (dest / "wrapper").exists()

    def test_strip_single_dir_noop_when_multiple_top_entries(
        self, tmp_path: Path
    ) -> None:
        src = tmp_path / "in.zip"
        with zipfile.ZipFile(src, "w") as zf:
            zf.writestr("index.html", b"<html></html>")
            zf.writestr("game/a.txt", b"a")

        dest = tmp_path / "out"
        extract_zip(src, dest, strip_single_dir=True)

        assert (dest / "index.html").exists()
        assert (dest / "game" / "a.txt").exists()
