from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import tomllib
import zipfile

import providers
from infra.fs import (
    calc_sha256,
    ensure_dir,
    now_iso,
    remove_tree,
    replace_directory,
    staging_directory,
)
from infra.net import download_file, is_url
from infra.toml import read_toml, write_toml
from infra.zip import DEFAULT_MAX_MEMBERS, DEFAULT_MAX_UNCOMPRESSED_BYTES

from .models import (
    ConflictError,
    DataError,
    DolCtlError,
    ExternalError,
    Mod,
    NotFoundError,
    ProgressCallback,
    RemoveResult,
    ValidationError,
    mod_from_dict,
    mod_to_dict,
)
from .profiles import remove_mod_from_all_profiles
from .root import RootLayout, load_config, validate_resource_name
from .versions import _select_remote_version, list_remote_mods


def _mod_manifest(layout: RootLayout, mod_id: str) -> Path:
    return layout.mod_dir(mod_id) / ".mod.toml"


def _mod_archive(layout: RootLayout, mod_id: str) -> Path:
    return layout.mod_dir(mod_id) / f"{mod_id}.mod.zip"


def _safe_archive_name(name: str) -> PurePosixPath:
    normalised = name.replace("\\", "/")
    path = PurePosixPath(normalised)
    if path.is_absolute() or any(part == ".." for part in path.parts):
        raise ValidationError(f"Unsafe path in mod archive: {name!r}")
    if path.parts and ":" in path.parts[0]:
        raise ValidationError(f"Unsafe drive path in mod archive: {name!r}")
    return path


def _inspect_mod_archive(path: Path) -> tuple[dict, str | None]:
    try:
        with zipfile.ZipFile(path) as archive:
            members = archive.infolist()
            if len(members) > DEFAULT_MAX_MEMBERS:
                raise ValidationError("Mod archive contains too many files")
            if (
                sum(member.file_size for member in members)
                > DEFAULT_MAX_UNCOMPRESSED_BYTES
            ):
                raise ValidationError("Mod archive is too large when expanded")
            files: list[str] = []
            for member in members:
                _safe_archive_name(member.filename)
                if stat.S_ISLNK(member.external_attr >> 16):
                    raise ValidationError(
                        f"Mod archive contains a symlink: {member.filename!r}"
                    )
                if not member.is_dir():
                    files.append(member.filename.replace("\\", "/"))

            if "boot.json" in files:
                boot_path = "boot.json"
                wrapper = None
            else:
                candidates = [
                    name
                    for name in files
                    if len(PurePosixPath(name).parts) == 2
                    and PurePosixPath(name).name == "boot.json"
                ]
                if len(candidates) != 1:
                    raise ValidationError(
                        "Mod archive must contain boot.json at its root or "
                        "inside one wrapper directory"
                    )
                boot_path = candidates[0]
                wrapper = PurePosixPath(boot_path).parts[0]
                if any(PurePosixPath(name).parts[0] != wrapper for name in files):
                    raise ValidationError(
                        "A wrapped mod archive cannot contain files outside its wrapper"
                    )

            raw = archive.read(boot_path)
    except DolCtlError:
        raise
    except (OSError, zipfile.BadZipFile, KeyError) as exc:
        raise ValidationError(f"Cannot read mod archive {path.name}: {exc}") from exc

    try:
        boot = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValidationError(f"Invalid boot.json in {path.name}: {exc}") from exc
    if not isinstance(boot, dict):
        raise ValidationError("boot.json must contain a JSON object")
    return boot, wrapper


def _flatten_archive(source: Path, destination: Path, wrapper: str) -> None:
    prefix = f"{wrapper}/"
    with (
        zipfile.ZipFile(source) as input_archive,
        zipfile.ZipFile(
            destination, "w", compression=zipfile.ZIP_DEFLATED
        ) as output_archive,
    ):
        for member in input_archive.infolist():
            name = member.filename.replace("\\", "/")
            if not name.startswith(prefix):
                continue
            flattened = name[len(prefix) :]
            if not flattened:
                continue
            copied = zipfile.ZipInfo(flattened, date_time=member.date_time)
            copied.compress_type = zipfile.ZIP_DEFLATED
            copied.external_attr = member.external_attr
            if member.is_dir():
                output_archive.writestr(copied, b"")
            else:
                output_archive.writestr(copied, input_archive.read(member))


def _slug(value: str, seed: str) -> str:
    normalised = re.sub(r"[^a-z0-9._-]+", "-", value.lower()).strip(".-")
    if not normalised:
        normalised = "mod"
    digest = hashlib.sha256((value + "\0" + seed).encode()).hexdigest()[:8]
    candidate = normalised[:110]
    if candidate == "mod" or candidate != value.lower():
        candidate = f"{candidate}-{digest}"
    return validate_resource_name(candidate, "mod")


def _read_mod(layout: RootLayout, mod_id: str) -> Mod:
    directory = layout.mod_dir(mod_id)
    manifest_path = directory / ".mod.toml"
    archive_path = directory / f"{mod_id}.mod.zip"
    if not directory.is_dir() or not manifest_path.is_file():
        raise NotFoundError(f"Mod not found: {mod_id}")
    if manifest_path.is_symlink() or archive_path.is_symlink():
        raise DataError(f"Mod files cannot be symlinks: {mod_id}")
    try:
        mod = mod_from_dict(read_toml(manifest_path), directory)
    except (OSError, tomllib.TOMLDecodeError, DataError) as exc:
        raise DataError(f"Cannot read mod manifest {manifest_path}: {exc}") from exc
    if mod.id != mod_id:
        raise DataError(f"Mod manifest id {mod.id!r} does not match {mod_id!r}")
    if not archive_path.is_file():
        raise DataError(f"Mod archive is missing: {archive_path}")
    mod.sha256 = mod.sha256 or calc_sha256(archive_path)
    return mod


def get_mod_info(root: Path, mod_id: str) -> Mod:
    layout = RootLayout.open(root)
    mod_id = validate_resource_name(mod_id, "mod")
    return _read_mod(layout, mod_id)


def list_mods(root: Path) -> list[Mod]:
    layout = RootLayout.open(root)
    mods: list[Mod] = []
    for directory in sorted(layout.mods.iterdir(), key=lambda item: item.name):
        if directory.is_dir() and (directory / ".mod.toml").is_file():
            mods.append(_read_mod(layout, directory.name))
    return mods


def _publish_mod_archive(
    layout: RootLayout,
    source: Path,
    mod_id: str | None = None,
    *,
    source_kind: str,
    source_ref: str,
    force: bool = False,
) -> str:
    boot, wrapper = _inspect_mod_archive(source)
    name = str(boot.get("name") or source.stem.replace(".mod", ""))
    selected_id = (
        validate_resource_name(mod_id, "mod")
        if mod_id
        else _slug(name, source.name)
    )

    with staging_directory(layout.root, "mods") as workspace:
        payload = ensure_dir(workspace / "payload")
        destination_archive = payload / f"{selected_id}.mod.zip"
        if wrapper is None:
            shutil.copy2(source, destination_archive)
        else:
            _flatten_archive(source, destination_archive, wrapper)
        _inspect_mod_archive(destination_archive)
        digest = calc_sha256(destination_archive)
        mod = Mod(
            id=selected_id,
            name=name,
            version=str(boot.get("version") or ""),
            author=str(boot.get("author") or ""),
            description=str(boot.get("description") or ""),
            source=source_kind,
            source_ref=source_ref,
            installed_at=now_iso(),
            sha256=digest,
            path=payload,
        )
        write_toml(payload / ".mod.toml", mod_to_dict(mod))
        try:
            replace_directory(
                payload,
                layout.mod_dir(selected_id),
                collection=layout.mods,
                force=force,
            )
        except FileExistsError as exc:
            raise ConflictError(
                f"Mod already exists: {selected_id}; use --force to replace it"
            ) from exc
        return selected_id


def add_mod_from_zip(
    root: Path,
    path_or_url: str,
    mod_id: str | None = None,
    *,
    force: bool = False,
    progress: ProgressCallback | None = None,
) -> str:
    layout = RootLayout.open(root)
    source_kind = "url" if is_url(path_or_url) else "local"
    if source_kind == "url":
        cache_key = hashlib.sha256(path_or_url.encode()).hexdigest()[:16]
        source = layout.download_cache / f"mod-{cache_key}.zip"
        try:
            download_file(path_or_url, source, progress=progress)
        except Exception as exc:
            raise ExternalError(f"Could not download mod: {exc}") from exc
    else:
        source = Path(path_or_url).expanduser().resolve()
        if not source.is_file():
            raise NotFoundError(f"Mod archive not found: {source}")

    try:
        return _publish_mod_archive(
            layout,
            source,
            mod_id,
            source_kind=source_kind,
            source_ref=path_or_url,
            force=force,
        )
    except DolCtlError:
        raise
    except Exception as exc:
        raise ExternalError(f"Could not import mod {source.name}: {exc}") from exc


def install_mod_from_remote(
    root: Path,
    channel: str,
    selector: str,
    mod_id: str | None = None,
    *,
    force: bool = False,
    progress: ProgressCallback | None = None,
) -> str:
    layout = RootLayout.open(root)
    channel = validate_resource_name(channel, "channel")
    releases = list_remote_mods(layout.root, channel)
    remote = _select_remote_version(releases, selector, channel)
    config = load_config(layout.root)
    provider = providers.create_provider(channel, config.channels[channel])
    cache_key = hashlib.sha256(remote.download_url.encode()).hexdigest()[:16]
    archive = layout.download_cache / f"remote-mod-{cache_key}.zip"
    ensure_dir(archive.parent)
    try:
        provider.download(remote, archive, progress=progress)
        return _publish_mod_archive(
            layout,
            archive,
            mod_id,
            source_kind="remote",
            source_ref=remote.source_ref or remote.download_url,
            force=force,
        )
    except DolCtlError:
        raise
    except Exception as exc:
        raise ExternalError(
            f"Could not install {selector!r} from {channel}: {exc}"
        ) from exc


def remove_mod(root: Path, mod_id: str) -> RemoveResult:
    layout = RootLayout.open(root)
    mod_id = validate_resource_name(mod_id, "mod")
    get_mod_info(layout.root, mod_id)
    affected = remove_mod_from_all_profiles(layout.root, mod_id)
    try:
        remove_tree(layout.mod_dir(mod_id), within=layout.mods)
    except (OSError, ValueError) as exc:
        raise ExternalError(f"Could not remove mod {mod_id}: {exc}") from exc
    return RemoveResult(mod_id, affected)
