from __future__ import annotations

from pathlib import Path
import hashlib
import os
import shutil
from datetime import datetime, timezone


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def find_root(start: Path) -> Path | None:
    current = start.resolve()
    if (current / ".dolctl").is_dir():
        return current
    for parent in current.parents:
        if (parent / ".dolctl").is_dir():
            return parent
    return None


def safe_rmtree(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)


def atomic_dir_move(src: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    os.replace(src, dest)


def copytree_atomic(src: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.parent / f".tmp_{dest.name}"
    if tmp.exists():
        safe_rmtree(tmp)
    shutil.copytree(src, tmp)
    if dest.exists():
        safe_rmtree(dest)
    atomic_dir_move(tmp, dest)


def calc_sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()
