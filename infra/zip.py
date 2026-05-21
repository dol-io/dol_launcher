from __future__ import annotations

from pathlib import Path
import shutil
import zipfile


def _safe_member_path(dest: Path, member_name: str) -> Path:
    """Resolve *member_name* under *dest* and reject path traversal.

    Raises ``ValueError`` if the member name is absolute, contains ``..``
    segments, or resolves outside *dest*.
    """
    name = member_name.replace("\\", "/")
    if name.startswith("/") or ":" in name.split("/", 1)[0]:
        raise ValueError(f"Unsafe absolute path in zip: {member_name!r}")
    parts = [p for p in name.split("/") if p not in ("", ".")]
    if any(p == ".." for p in parts):
        raise ValueError(f"Path traversal in zip: {member_name!r}")
    target = (dest / Path(*parts)).resolve()
    dest_resolved = dest.resolve()
    if target != dest_resolved and dest_resolved not in target.parents:
        raise ValueError(f"Zip member escapes destination: {member_name!r}")
    return target


def extract_zip(src: Path, dest: Path, strip_single_dir: bool = False) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(src, "r") as zip_handle:
        for info in zip_handle.infolist():
            if info.filename.endswith("/"):
                target = _safe_member_path(dest, info.filename)
                target.mkdir(parents=True, exist_ok=True)
                continue
            target = _safe_member_path(dest, info.filename)
            target.parent.mkdir(parents=True, exist_ok=True)
            with zip_handle.open(info, "r") as source, target.open("wb") as sink:
                shutil.copyfileobj(source, sink)
    if strip_single_dir:
        entries = list(dest.iterdir())
        if len(entries) == 1 and entries[0].is_dir():
            inner = entries[0]
            for item in inner.iterdir():
                shutil.move(str(item), dest / item.name)
            shutil.rmtree(inner)
