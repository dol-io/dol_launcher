from __future__ import annotations

from pathlib import Path, PurePosixPath
import shutil
import tarfile

from .zip import DEFAULT_MAX_MEMBERS, DEFAULT_MAX_UNCOMPRESSED_BYTES


def _safe_member_path(destination: Path, member_name: str) -> Path:
    normalised = member_name.replace("\\", "/")
    member = PurePosixPath(normalised)
    if not member.parts:
        raise ValueError("Tar member has an empty path")
    if member.is_absolute() or any(part == ".." for part in member.parts):
        raise ValueError(f"Unsafe path in tar: {member_name!r}")
    if ":" in member.parts[0]:
        raise ValueError(f"Unsafe drive path in tar: {member_name!r}")
    target = destination.joinpath(*member.parts).resolve(strict=False)
    root = destination.resolve()
    if target == root or root not in target.parents:
        raise ValueError(f"Tar member escapes destination: {member_name!r}")
    return target


def extract_tar(
    source: Path,
    destination: Path,
    *,
    strip_single_dir: bool = False,
    max_members: int = DEFAULT_MAX_MEMBERS,
    max_uncompressed_bytes: int = DEFAULT_MAX_UNCOMPRESSED_BYTES,
) -> None:
    """Extract a tar archive without trusting paths, links, or special files."""
    destination.mkdir(parents=True, exist_ok=True)
    with tarfile.open(source, mode="r:*") as archive:
        members = archive.getmembers()
        if len(members) > max_members:
            raise ValueError(f"Tar contains too many members: {len(members)}")
        if any(member.size < 0 for member in members):
            raise ValueError("Tar contains a member with a negative size")
        total_size = sum(member.size for member in members if member.isfile())
        if total_size > max_uncompressed_bytes:
            raise ValueError(
                f"Tar expands to {total_size} bytes, above the configured limit"
            )

        validated: list[tuple[tarfile.TarInfo, Path]] = []
        for member in members:
            target = _safe_member_path(destination, member.name)
            if not member.isdir() and not member.isfile():
                raise ValueError(
                    f"Tar contains a link or special file: {member.name!r}"
                )
            validated.append((member, target))

        for member, target in validated:
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            source_handle = archive.extractfile(member)
            if source_handle is None:
                raise ValueError(f"Cannot read tar member: {member.name!r}")
            with source_handle, target.open("wb") as target_handle:
                shutil.copyfileobj(source_handle, target_handle)

    if strip_single_dir:
        entries = list(destination.iterdir())
        if len(entries) == 1 and entries[0].is_dir():
            wrapper = entries[0]
            for item in wrapper.iterdir():
                shutil.move(item, destination / item.name)
            wrapper.rmdir()
