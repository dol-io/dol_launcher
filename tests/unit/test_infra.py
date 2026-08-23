from __future__ import annotations

import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
from pathlib import Path
import stat
import tarfile
import threading
import zipfile

import pytest

from infra.net import download_file, is_url
from infra.tar import _safe_member_path as _safe_tar_member_path
from infra.tar import extract_tar
from infra.zip import _safe_member_path, extract_zip


def test_url_detection_only_accepts_http() -> None:
    assert is_url("https://example.invalid/mod.zip")
    assert is_url("http://example.invalid/mod.zip")
    assert not is_url("file:///tmp/mod.zip")
    assert not is_url("relative/mod.zip")


@pytest.mark.parametrize(
    "name",
    ["../escape", "a/../../escape", "/etc/passwd", "C:/Windows/system32"],
)
def test_zip_member_rejects_escape(tmp_path: Path, name: str) -> None:
    with pytest.raises(ValueError):
        _safe_member_path(tmp_path, name)


def test_zip_normalises_backslashes(tmp_path: Path) -> None:
    assert (
        _safe_member_path(tmp_path, r"a\b.txt") == (tmp_path / "a" / "b.txt").resolve()
    )


def test_extract_zip_flattens_single_wrapper(make_zip, tmp_path: Path) -> None:
    archive = make_zip(
        "wrapped.zip",
        {
            "release/index.html": b"game",
            "release/assets/data": b"payload",
        },
    )
    destination = tmp_path / "out"
    extract_zip(archive, destination, strip_single_dir=True)
    assert (destination / "index.html").read_bytes() == b"game"
    assert (destination / "assets" / "data").read_bytes() == b"payload"
    assert not (destination / "release").exists()


def test_extract_zip_enforces_member_and_size_limits(make_zip, tmp_path: Path) -> None:
    archive = make_zip("limits.zip", {"a": b"1234", "b": b"5678"})
    with pytest.raises(ValueError, match="too many members"):
        extract_zip(archive, tmp_path / "members", max_members=1)
    with pytest.raises(ValueError, match="configured limit"):
        extract_zip(archive, tmp_path / "bytes", max_uncompressed_bytes=7)


def test_extract_zip_rejects_symlinks(tmp_path: Path) -> None:
    archive = tmp_path / "symlink.zip"
    info = zipfile.ZipInfo("link")
    info.create_system = 3
    info.external_attr = (stat.S_IFLNK | 0o777) << 16
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr(info, "target")
    with pytest.raises(ValueError, match="symlink"):
        extract_zip(archive, tmp_path / "out")


@pytest.mark.parametrize(
    "name",
    ["../escape", "a/../../escape", "/etc/passwd", "C:/Windows/system32"],
)
def test_tar_member_rejects_escape(tmp_path: Path, name: str) -> None:
    with pytest.raises(ValueError):
        _safe_tar_member_path(tmp_path, name)


def _add_tar_file(archive: tarfile.TarFile, name: str, content: bytes) -> None:
    info = tarfile.TarInfo(name)
    info.size = len(content)
    archive.addfile(info, io.BytesIO(content))


def test_extract_tar_flattens_single_wrapper(tmp_path: Path) -> None:
    source = tmp_path / "wrapped.tar.gz"
    with tarfile.open(source, "w:gz") as archive:
        _add_tar_file(archive, "release/assets/image.png", b"image")
    destination = tmp_path / "tar-out"
    extract_tar(source, destination, strip_single_dir=True)
    assert (destination / "assets" / "image.png").read_bytes() == b"image"
    assert not (destination / "release").exists()


def test_extract_tar_validates_all_members_before_writing(tmp_path: Path) -> None:
    source = tmp_path / "unsafe.tar.gz"
    with tarfile.open(source, "w:gz") as archive:
        _add_tar_file(archive, "release/safe.png", b"image")
        link = tarfile.TarInfo("release/link")
        link.type = tarfile.SYMTYPE
        link.linkname = "../../outside"
        archive.addfile(link)
    destination = tmp_path / "unsafe-out"
    with pytest.raises(ValueError, match="link or special"):
        extract_tar(source, destination)
    assert not (destination / "release" / "safe.png").exists()


class _PayloadHandler(BaseHTTPRequestHandler):
    payload = b"A" * 65_536

    def do_GET(self) -> None:  # noqa: N802
        self.send_response(200)
        self.send_header("Content-Length", str(len(self.payload)))
        self.end_headers()
        self.wfile.write(self.payload)

    def log_message(self, *_args: object) -> None:
        return


class _BrokenHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        self.send_response(200)
        self.send_header("Content-Length", "100")
        self.end_headers()
        self.wfile.write(b"short")
        self.close_connection = True

    def log_message(self, *_args: object) -> None:
        return


def _serve(handler: type[BaseHTTPRequestHandler]):
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def test_download_is_atomic_and_reports_progress(tmp_path: Path) -> None:
    server = _serve(_PayloadHandler)
    destination = tmp_path / "payload.bin"
    ticks: list[tuple[int, int | None]] = []
    try:
        digest = download_file(
            f"http://127.0.0.1:{server.server_port}/payload",
            destination,
            progress=lambda done, total: ticks.append((done, total)),
        )
    finally:
        server.shutdown()
        server.server_close()
    assert destination.read_bytes() == _PayloadHandler.payload
    assert digest == hashlib.sha256(_PayloadHandler.payload).hexdigest()
    assert ticks[-1] == (len(_PayloadHandler.payload), len(_PayloadHandler.payload))
    assert not destination.with_name("payload.bin.part").exists()


def test_failed_download_keeps_previous_file_and_removes_partial(
    tmp_path: Path,
) -> None:
    server = _serve(_BrokenHandler)
    destination = tmp_path / "payload.bin"
    destination.write_bytes(b"stable")
    try:
        with pytest.raises(Exception):
            download_file(
                f"http://127.0.0.1:{server.server_port}/payload",
                destination,
            )
    finally:
        server.shutdown()
        server.server_close()
    assert destination.read_bytes() == b"stable"
    assert not destination.with_name("payload.bin.part").exists()


def test_checksum_mismatch_keeps_previous_file(tmp_path: Path) -> None:
    server = _serve(_PayloadHandler)
    destination = tmp_path / "payload.bin"
    destination.write_bytes(b"stable")
    try:
        with pytest.raises(ValueError, match="checksum mismatch"):
            download_file(
                f"http://127.0.0.1:{server.server_port}/payload",
                destination,
                expected_sha256="0" * 64,
            )
    finally:
        server.shutdown()
        server.server_close()
    assert destination.read_bytes() == b"stable"
    assert not destination.with_name("payload.bin.part").exists()
