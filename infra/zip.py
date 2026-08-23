from __future__ import annotations

from pathlib import Path, PurePosixPath
import shutil
import stat
import zipfile


DEFAULT_MAX_MEMBERS = 100_000
DEFAULT_MAX_UNCOMPRESSED_BYTES = 8 * 1024 * 1024 * 1024


def _safe_member_path(destination: Path, member_name: str) -> Path:
    normalised = member_name.replace("\\", "/")
    member = PurePosixPath(normalised)
    if member.is_absolute() or any(part == ".." for part in member.parts):
        raise ValueError(f"Unsafe path in zip: {member_name!r}")
    if member.parts and ":" in member.parts[0]:
        raise ValueError(f"Unsafe drive path in zip: {member_name!r}")
    target = destination.joinpath(*member.parts).resolve(strict=False)
    root = destination.resolve()
    if target != root and root not in target.parents:
        raise ValueError(f"Zip member escapes destination: {member_name!r}")
    return target


def _is_symlink(info: zipfile.ZipInfo) -> bool:
    return stat.S_ISLNK(info.external_attr >> 16)


def extract_zip(
    source: Path,
    destination: Path,
    *,
    strip_single_dir: bool = False,
    max_members: int = DEFAULT_MAX_MEMBERS,
    max_uncompressed_bytes: int = DEFAULT_MAX_UNCOMPRESSED_BYTES,
) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(source) as archive:
        members = archive.infolist()
        if len(members) > max_members:
            raise ValueError(f"Zip contains too many members: {len(members)}")
        total_size = sum(member.file_size for member in members)
        if total_size > max_uncompressed_bytes:
            raise ValueError(
                f"Zip expands to {total_size} bytes, above the configured limit"
            )
        for member in members:
            if _is_symlink(member):
                raise ValueError(f"Zip contains a symlink: {member.filename!r}")
            target = _safe_member_path(destination, member.filename)
            if member.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with (
                archive.open(member) as source_handle,
                target.open("wb") as target_handle,
            ):
                shutil.copyfileobj(source_handle, target_handle)

    if strip_single_dir:
        entries = list(destination.iterdir())
        if len(entries) == 1 and entries[0].is_dir():
            wrapper = entries[0]
            for item in wrapper.iterdir():
                shutil.move(item, destination / item.name)
            wrapper.rmdir()
