from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import shutil
import tempfile
from typing import Iterator
from uuid import uuid4


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def ensure_safe_subdirectory(root: Path, *parts: str) -> Path:
    """Create a descendant directory while rejecting symlinked components."""
    current = root.expanduser().resolve()
    for part in parts:
        if not part or Path(part).name != part:
            raise ValueError(f"Unsafe directory component: {part!r}")
        current = current / part
        if current.is_symlink():
            raise ValueError(f"Directory cannot be a symlink: {current}")
        current.mkdir(exist_ok=True)
    return current


def find_root(start: Path) -> Path | None:
    current = start.expanduser().resolve()
    for candidate in (current, *current.parents):
        if (candidate / ".dolctl").is_dir():
            return candidate
    return None


def ensure_within(path: Path, parent: Path, *, direct: bool = False) -> Path:
    """Return the resolved path after proving it stays below *parent*."""
    resolved_parent = parent.expanduser().resolve()
    absolute_path = Path(os.path.abspath(path.expanduser()))
    resolved_path = absolute_path.resolve(strict=False)
    if resolved_path == resolved_parent or resolved_parent not in resolved_path.parents:
        raise ValueError(f"Path escapes expected directory: {path}")
    if direct and absolute_path.parent.resolve() != resolved_parent:
        raise ValueError(f"Path is not a direct child of {parent}: {path}")
    return absolute_path


def remove_tree(path: Path, *, within: Path) -> None:
    target = ensure_within(path, within, direct=True)
    if target.is_symlink():
        raise ValueError(f"Refusing to remove symlinked directory: {path}")
    if not target.exists():
        return
    shutil.rmtree(target)


def atomic_write_text(path: Path, content: str, *, encoding: str = "utf-8") -> None:
    ensure_dir(path.parent)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding=encoding) as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def atomic_write_bytes(path: Path, content: bytes) -> None:
    ensure_dir(path.parent)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


@contextmanager
def staging_directory(root: Path, category: str) -> Iterator[Path]:
    parent = ensure_safe_subdirectory(root, ".dolctl", "staging", category)
    path = Path(tempfile.mkdtemp(prefix="work-", dir=parent))
    try:
        yield path
    finally:
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)


def replace_directory(
    staged: Path,
    destination: Path,
    *,
    collection: Path,
    force: bool,
) -> None:
    """Publish a staged directory and roll back a failed replacement."""
    destination = ensure_within(destination, collection, direct=True)
    staged = ensure_within(staged, staged.parents[2])
    if destination.is_symlink():
        raise ValueError(f"Refusing to replace symlinked directory: {destination}")
    ensure_dir(destination.parent)
    if destination.exists() and not force:
        raise FileExistsError(destination)
    if not destination.exists():
        os.replace(staged, destination)
        return

    backup = destination.parent / f".{destination.name}.backup-{uuid4().hex}"
    os.replace(destination, backup)
    try:
        os.replace(staged, destination)
    except BaseException:
        os.replace(backup, destination)
        raise
    shutil.rmtree(backup, ignore_errors=True)


def copy_tree(
    source: Path, destination: Path, *, ignored_names: set[str] | None = None
) -> None:
    ignored = ignored_names or set()
    for source_root, directories, filenames in os.walk(source):
        root_path = Path(source_root)
        relative_root = root_path.relative_to(source)
        directories[:] = [name for name in directories if name not in ignored]
        for filename in filenames:
            if filename in ignored:
                continue
            source_file = root_path / filename
            destination_file = destination / relative_root / filename
            ensure_dir(destination_file.parent)
            shutil.copy2(source_file, destination_file)


def calc_sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()
