from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import tomllib
from uuid import uuid4

import providers
from infra.fs import (
    atomic_write_text,
    calc_sha256,
    copy_tree,
    ensure_dir,
    now_iso,
    remove_tree,
    replace_directory,
    staging_directory,
)
from infra.toml import read_toml, write_toml
from infra.zip import extract_zip

from .models import (
    ConflictError,
    ChannelConfig,
    DataError,
    DolCtlError,
    ExternalError,
    InstalledVersion,
    NotFoundError,
    ProgressCallback,
    RemoteVersion,
    RemoveResult,
    ValidationError,
    VersionManifest,
    remote_version_from_dict,
    remote_version_to_dict,
    version_manifest_from_dict,
    version_manifest_to_dict,
)
from .profiles import clear_version_from_profiles, list_profiles
from .root import RootLayout, load_config, validate_resource_name


_ENTRY_DEMOTIONS = ("polyfill", "debug", "test")


def _entry_score(name: str) -> tuple[int, int, str]:
    lowered = name.lower()
    return (
        sum(marker in lowered for marker in _ENTRY_DEMOTIONS),
        len(name),
        name,
    )


def _find_entry_html(directory: Path) -> str:
    preferred = directory / "index.html"
    if preferred.is_file():
        return preferred.name
    candidates = sorted(
        (
            item.name
            for item in directory.iterdir()
            if item.is_file() and item.suffix.lower() == ".html"
        ),
        key=_entry_score,
    )
    if not candidates:
        raise ValidationError("No entry HTML was found at the root of the game package")
    return candidates[0]


def _legacy_revision(manifest: VersionManifest) -> str:
    payload = "\0".join(
        (
            manifest.id,
            manifest.sha256 or "",
            manifest.installed_at,
            manifest.source_ref,
        )
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def _read_manifest(path: Path) -> VersionManifest:
    if path.is_symlink():
        raise DataError(f"Version manifest cannot be a symlink: {path}")
    try:
        manifest = version_manifest_from_dict(read_toml(path))
    except FileNotFoundError as exc:
        raise NotFoundError(f"Version manifest not found: {path}") from exc
    except (OSError, tomllib.TOMLDecodeError, DataError) as exc:
        raise DataError(f"Cannot read version manifest {path}: {exc}") from exc
    manifest.revision = manifest.revision or _legacy_revision(manifest)
    validate_resource_name(manifest.id, "version")
    validate_resource_name(manifest.entry, "entry HTML")
    return manifest


def get_installed(root: Path, version_id: str) -> InstalledVersion:
    layout = RootLayout.open(root)
    directory = layout.version_dir(version_id)
    if not directory.is_dir():
        raise NotFoundError(f"Version not found: {version_id}")
    manifest = _read_manifest(directory / ".manifest.toml")
    if manifest.id != version_id:
        raise DataError(
            f"Version manifest id {manifest.id!r} does not match {version_id!r}"
        )
    if not (directory / manifest.entry).is_file():
        raise DataError(f"Version entry is missing: {version_id}/{manifest.entry}")
    return InstalledVersion(
        id=manifest.id,
        display_name=manifest.display_name,
        channel=manifest.channel,
        source=manifest.source,
        source_ref=manifest.source_ref,
        installed_at=manifest.installed_at,
        entry=manifest.entry,
        revision=manifest.revision,
        path=directory,
    )


def list_installed(root: Path) -> list[InstalledVersion]:
    layout = RootLayout.open(root)
    versions: list[InstalledVersion] = []
    for directory in sorted(layout.versions.iterdir(), key=lambda item: item.name):
        if directory.is_dir() and (directory / ".manifest.toml").is_file():
            versions.append(get_installed(layout.root, directory.name))
    return versions


def _parse_time(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _channel_fingerprint(name: str, channel: ChannelConfig) -> str:
    payload = json.dumps(
        {
            "name": name,
            "provider": channel.provider,
            "repo": channel.repo,
            "asset_regex": channel.asset_regex,
            "extra": channel.extra,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def _load_remote_cache(
    path: Path, *, ttl_seconds: int, fingerprint: str
) -> list[RemoteVersion] | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        fetched_at = _parse_time(str(payload.get("fetched_at", "")))
        if fetched_at is None or payload.get("channel_fingerprint") != fingerprint:
            return None
        age = datetime.now(timezone.utc) - fetched_at
        if age.total_seconds() > ttl_seconds:
            return None
        raw_versions = payload.get("versions", [])
        if not isinstance(raw_versions, list) or not all(
            isinstance(item, dict) for item in raw_versions
        ):
            return None
        return [remote_version_from_dict(item) for item in raw_versions]
    except (OSError, json.JSONDecodeError, DataError, TypeError):
        return None


def _save_remote_cache(
    path: Path, versions: list[RemoteVersion], fingerprint: str
) -> None:
    payload = {
        "schema_version": 1,
        "fetched_at": now_iso(),
        "channel_fingerprint": fingerprint,
        "versions": [remote_version_to_dict(version) for version in versions],
    }
    atomic_write_text(path, json.dumps(payload, indent=2) + "\n")


def list_remote_versions(
    root: Path, channel: str, *, refresh: bool = False
) -> list[RemoteVersion]:
    layout = RootLayout.open(root)
    channel = validate_resource_name(channel, "channel")
    config = load_config(layout.root)
    channel_config = config.channels.get(channel)
    if channel_config is None:
        raise NotFoundError(f"Channel not found: {channel}")
    fingerprint = _channel_fingerprint(channel, channel_config)
    cache_file = layout.channel_cache_file(channel)
    if not refresh:
        cached = _load_remote_cache(
            cache_file,
            ttl_seconds=config.index_cache_ttl_seconds,
            fingerprint=fingerprint,
        )
        if cached is not None:
            return cached
    try:
        remote_versions = providers.create_provider(
            channel, channel_config
        ).list_versions()
    except DolCtlError:
        raise
    except Exception as exc:
        raise ExternalError(
            f"Could not load releases for channel {channel}: {exc}"
        ) from exc
    _save_remote_cache(cache_file, remote_versions, fingerprint)
    return remote_versions


def _normalise_selector(value: str, channel: str) -> str:
    normalised = value
    prefix = f"{channel}-"
    if channel and normalised.startswith(prefix):
        normalised = normalised[len(prefix) :]
    return normalised[1:] if normalised.startswith("v") else normalised


def _select_remote_version(
    versions: list[RemoteVersion], selector: str, channel: str = ""
) -> RemoteVersion:
    if selector == "latest":
        if not versions:
            raise NotFoundError("No remote releases were found")
        return max(versions, key=lambda item: item.published_at)
    requested = _normalise_selector(selector, channel)
    for version in versions:
        if _normalise_selector(version.id, channel) == requested:
            return version
    raise NotFoundError(f"Remote version not found: {selector}")


def _resolve_selector(selector: str, default_channel: str) -> tuple[str, str]:
    if ":" not in selector:
        return default_channel, selector
    channel, requested = selector.split(":", 1)
    if not channel or not requested:
        raise ValidationError(f"Invalid remote selector: {selector!r}")
    return channel, requested


def _safe_remote_component(remote_id: str, *, max_length: int = 128) -> str:
    if max_length < 16:
        raise ValidationError("Channel name leaves no room for a remote version id")
    candidate = re.sub(r"[\s/\\:]+", "-", remote_id).strip(".- ")
    candidate = re.sub(r"[^\w.-]+", "-", candidate, flags=re.UNICODE)
    if not candidate:
        candidate = "release"
    if candidate != remote_id or len(candidate) > max_length:
        suffix = hashlib.sha256(remote_id.encode()).hexdigest()[:8]
        base = candidate[: max_length - len(suffix) - 1].rstrip(".- ") or "release"
        candidate = f"{base}-{suffix}"
    return validate_resource_name(candidate, "remote version")


def _make_version_id(channel: str, remote_id: str) -> str:
    channel = validate_resource_name(channel, "channel")
    prefix = f"{channel}-"
    if remote_id.startswith(prefix):
        return _safe_remote_component(remote_id)
    available = 128 - len(prefix)
    return validate_resource_name(
        f"{prefix}{_safe_remote_component(remote_id, max_length=available)}",
        "version",
    )


def _publish_version(
    layout: RootLayout,
    payload: Path,
    manifest: VersionManifest,
    *,
    force: bool,
) -> str:
    write_toml(payload / ".manifest.toml", version_manifest_to_dict(manifest))
    try:
        replace_directory(
            payload,
            layout.version_dir(manifest.id),
            collection=layout.versions,
            force=force,
        )
    except FileExistsError as exc:
        raise ConflictError(
            f"Version already exists: {manifest.id}; use --force to replace it"
        ) from exc
    except OSError as exc:
        raise ExternalError(f"Could not publish version {manifest.id}: {exc}") from exc
    return manifest.id


def install_from_file(
    root: Path,
    file_path: Path,
    version_id: str | None,
    channel: str,
    *,
    force: bool = False,
) -> str:
    layout = RootLayout.open(root)
    source = file_path.expanduser().resolve()
    if not source.is_file():
        raise NotFoundError(f"Version archive not found: {source}")
    channel = validate_resource_name(channel, "channel")
    version_id = validate_resource_name(
        version_id or f"{channel}-{_safe_remote_component(source.stem)}",
        "version",
    )
    digest = calc_sha256(source)
    try:
        with staging_directory(layout.root, "versions") as workspace:
            payload = ensure_dir(workspace / "payload")
            extract_zip(source, payload, strip_single_dir=True)
            entry = _find_entry_html(payload)
            manifest = VersionManifest(
                id=version_id,
                display_name=version_id,
                channel=channel,
                source="local",
                source_ref=str(source),
                sha256=digest,
                installed_at=now_iso(),
                entry=entry,
                revision=uuid4().hex,
            )
            return _publish_version(layout, payload, manifest, force=force)
    except DolCtlError:
        raise
    except Exception as exc:
        raise ExternalError(f"Could not install {source.name}: {exc}") from exc


def install_from_dir(
    root: Path,
    dir_path: Path,
    version_id: str | None,
    channel: str,
    *,
    force: bool = False,
) -> str:
    layout = RootLayout.open(root)
    source = dir_path.expanduser().resolve()
    if not source.is_dir():
        raise NotFoundError(f"Version directory not found: {source}")
    channel = validate_resource_name(channel, "channel")
    version_id = validate_resource_name(
        version_id or f"{channel}-{_safe_remote_component(source.name)}",
        "version",
    )
    try:
        with staging_directory(layout.root, "versions") as workspace:
            payload = ensure_dir(workspace / "payload")
            copy_tree(source, payload, ignored_names={".manifest.toml"})
            entry = _find_entry_html(payload)
            manifest = VersionManifest(
                id=version_id,
                display_name=version_id,
                channel=channel,
                source="local",
                source_ref=str(source),
                sha256=None,
                installed_at=now_iso(),
                entry=entry,
                revision=uuid4().hex,
            )
            return _publish_version(layout, payload, manifest, force=force)
    except DolCtlError:
        raise
    except Exception as exc:
        raise ExternalError(f"Could not install directory {source}: {exc}") from exc


def install_from_remote(
    root: Path,
    channel: str,
    selector: str,
    *,
    force: bool = False,
    progress: ProgressCallback | None = None,
) -> str:
    layout = RootLayout.open(root)
    channel, selector = _resolve_selector(selector, channel)
    channel = validate_resource_name(channel, "channel")
    versions = list_remote_versions(layout.root, channel)
    remote = _select_remote_version(versions, selector, channel)
    version_id = _make_version_id(channel, remote.id)
    config = load_config(layout.root)
    channel_config = config.channels[channel]
    provider = providers.create_provider(channel, channel_config)
    cache_name = hashlib.sha256(remote.download_url.encode()).hexdigest()[:12]
    archive = layout.download_cache / f"{version_id}-{cache_name}.zip"
    ensure_dir(archive.parent)
    try:
        digest = provider.download(remote, archive, progress=progress)
        with staging_directory(layout.root, "versions") as workspace:
            payload = ensure_dir(workspace / "payload")
            extract_zip(archive, payload, strip_single_dir=True)
            entry = _find_entry_html(payload)
            manifest = VersionManifest(
                id=version_id,
                display_name=remote.display_name,
                channel=channel,
                source="remote",
                source_ref=remote.source_ref or remote.download_url,
                sha256=digest,
                installed_at=now_iso(),
                entry=entry,
                revision=uuid4().hex,
            )
            return _publish_version(layout, payload, manifest, force=force)
    except DolCtlError:
        raise
    except Exception as exc:
        raise ExternalError(
            f"Could not install {selector!r} from {channel}: {exc}"
        ) from exc


def remove_version(root: Path, version_id: str, *, force: bool = False) -> RemoveResult:
    layout = RootLayout.open(root)
    version_id = validate_resource_name(version_id, "version")
    get_installed(layout.root, version_id)
    affected = tuple(
        profile.name
        for profile in list_profiles(layout.root)
        if profile.version_id == version_id
    )
    if affected and not force:
        names = ", ".join(affected)
        raise ConflictError(
            f"Version {version_id} is used by: {names}; use --force to detach it"
        )
    if affected:
        clear_version_from_profiles(layout.root, version_id)
    try:
        remove_tree(layout.version_dir(version_id), within=layout.versions)
    except (OSError, ValueError) as exc:
        raise ExternalError(f"Could not remove version {version_id}: {exc}") from exc
    return RemoveResult(version_id, affected)
