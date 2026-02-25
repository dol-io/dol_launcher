from __future__ import annotations

from pathlib import Path
import json
import shutil
import tempfile
from datetime import datetime, timezone

from .core_root import load_config
from .infra_fs import ensure_dir, safe_rmtree, atomic_dir_move, now_iso, calc_sha256
from .infra_toml import read_toml, write_toml
from .infra_zip import extract_zip
from .infra_net import download_file
from .models import (
    DolCtlError,
    VersionManifest,
    InstalledVersion,
    RemoteVersion,
    version_manifest_from_dict,
    version_manifest_to_dict,
    remote_version_from_dict,
    remote_version_to_dict,
)
from .providers_github import GitHubReleasesProvider


def _versions_dir(root: Path) -> Path:
    return root / "versions"


def _cache_dir(root: Path) -> Path:
    return root / ".dolctl" / "cache" / "index"


def _download_cache_dir(root: Path) -> Path:
    return root / ".dolctl" / "cache" / "downloads"


def list_installed(root: Path) -> list[InstalledVersion]:
    versions: list[InstalledVersion] = []
    versions_dir = _versions_dir(root)
    if not versions_dir.exists():
        return versions
    for entry in versions_dir.iterdir():
        if not entry.is_dir():
            continue
        manifest_path = entry / ".manifest.toml"
        if not manifest_path.exists():
            continue
        manifest = version_manifest_from_dict(read_toml(manifest_path))
        versions.append(
            InstalledVersion(
                id=manifest.id,
                display_name=manifest.display_name,
                channel=manifest.channel,
                source=manifest.source,
                source_ref=manifest.source_ref,
                installed_at=manifest.installed_at,
                entry=manifest.entry,
                path=entry,
            )
        )
    return sorted(versions, key=lambda v: v.id)


def _parse_iso(value: str) -> datetime | None:
    if not value:
        return None
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _cache_valid(path: Path, ttl_seconds: int) -> bool:
    if not path.exists():
        return False
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False
    fetched_at = _parse_iso(str(payload.get("fetched_at", "")))
    if not fetched_at:
        return False
    age = datetime.now(timezone.utc) - fetched_at
    return age.total_seconds() <= ttl_seconds


def _load_cache(path: Path) -> list[RemoteVersion]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    versions = []
    for item in payload.get("versions", []):
        versions.append(remote_version_from_dict(item))
    return versions


def _save_cache(path: Path, versions: list[RemoteVersion]) -> None:
    payload = {
        "fetched_at": now_iso(),
        "versions": [remote_version_to_dict(v) for v in versions],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _get_provider(root: Path, channel: str) -> GitHubReleasesProvider:
    config = load_config(root)
    channel_cfg = config.channels.get(channel)
    if channel_cfg is None:
        raise DolCtlError(f"Channel not configured: {channel}")
    if channel_cfg.provider != "github":
        raise DolCtlError(f"Unsupported provider: {channel_cfg.provider}")
    if not channel_cfg.repo:
        raise DolCtlError(f"Channel repo is missing: {channel}")
    return GitHubReleasesProvider(channel, channel_cfg.repo, channel_cfg.asset_regex)


def list_remote_versions(root: Path, channel: str, refresh: bool = False) -> list[RemoteVersion]:
    config = load_config(root)
    cache_path = _cache_dir(root) / f"{channel}.json"
    if not refresh and _cache_valid(cache_path, config.index_cache_ttl_seconds):
        return _load_cache(cache_path)
    provider = _get_provider(root, channel)
    versions = provider.list_versions()
    _save_cache(cache_path, versions)
    return versions


def _normalize_id(value: str) -> str:
    if value.startswith("v"):
        return value[1:]
    return value


def _select_remote_version(versions: list[RemoteVersion], selector: str) -> RemoteVersion:
    if selector == "latest":
        ordered = sorted(versions, key=lambda v: v.published_at, reverse=True)
        if not ordered:
            raise DolCtlError("No remote versions found")
        return ordered[0]
    normalized = _normalize_id(selector)
    for version in versions:
        if _normalize_id(version.id) == normalized:
            return version
    raise DolCtlError(f"Remote version not found: {selector}")


def _resolve_selector(selector: str, default_channel: str) -> tuple[str, str]:
    if ":" in selector:
        channel, tail = selector.split(":", 1)
        if channel:
            return channel, tail
    return default_channel, selector


def _make_version_id(channel: str, remote_id: str) -> str:
    if remote_id.startswith(f"{channel}-"):
        return remote_id
    return f"{channel}-{remote_id}"


def _install_from_temp(root: Path, temp_dir: Path, version_id: str, manifest: VersionManifest, force: bool) -> None:
    dest = _versions_dir(root) / version_id
    if dest.exists():
        if not force:
            safe_rmtree(temp_dir)
            raise DolCtlError(f"Version already exists: {version_id}")
        safe_rmtree(dest)
    atomic_dir_move(temp_dir, dest)
    write_toml(dest / ".manifest.toml", version_manifest_to_dict(manifest))


def install_from_remote(
    root: Path,
    channel: str,
    selector: str,
    force: bool = False,
) -> str:
    channel, selector = _resolve_selector(selector, channel)
    versions = list_remote_versions(root, channel)
    remote = _select_remote_version(versions, selector)
    version_id = _make_version_id(channel, remote.id)

    ensure_dir(_download_cache_dir(root))
    dest_zip = _download_cache_dir(root) / f"{version_id}-{remote.asset_name}"
    sha256 = download_file(remote.download_url, dest_zip)

    tmp_base = _download_cache_dir(root) / ".tmp"
    ensure_dir(tmp_base)
    temp_dir = Path(tempfile.mkdtemp(prefix="install_", dir=tmp_base))
    try:
        extract_zip(dest_zip, temp_dir, strip_single_dir=True)
        if not (temp_dir / "index.html").exists():
            raise DolCtlError("Installed version is missing index.html")
        manifest = VersionManifest(
            id=version_id,
            display_name=remote.display_name,
            channel=channel,
            source="remote",
            source_ref=remote.download_url,
            sha256=sha256,
            installed_at=now_iso(),
            entry="index.html",
        )
        _install_from_temp(root, temp_dir, version_id, manifest, force)
    except Exception:
        safe_rmtree(temp_dir)
        raise
    return version_id


def install_from_file(
    root: Path,
    file_path: Path,
    version_id: str | None,
    channel: str,
    force: bool = False,
) -> str:
    file_path = file_path.expanduser().resolve()
    if not file_path.exists():
        raise DolCtlError(f"File not found: {file_path}")
    if not version_id:
        version_id = _make_version_id(channel, file_path.stem)
    sha256 = calc_sha256(file_path)
    tmp_base = _download_cache_dir(root) / ".tmp"
    ensure_dir(tmp_base)
    temp_dir = Path(tempfile.mkdtemp(prefix="install_", dir=tmp_base))
    try:
        extract_zip(file_path, temp_dir, strip_single_dir=True)
        if not (temp_dir / "index.html").exists():
            raise DolCtlError("Installed version is missing index.html")
        manifest = VersionManifest(
            id=version_id,
            display_name=version_id,
            channel=channel,
            source="local",
            source_ref=str(file_path),
            sha256=sha256,
            installed_at=now_iso(),
            entry="index.html",
        )
        _install_from_temp(root, temp_dir, version_id, manifest, force)
    except Exception:
        safe_rmtree(temp_dir)
        raise
    return version_id


def install_from_dir(
    root: Path,
    dir_path: Path,
    version_id: str | None,
    channel: str,
    force: bool = False,
) -> str:
    dir_path = dir_path.expanduser().resolve()
    if not dir_path.exists():
        raise DolCtlError(f"Directory not found: {dir_path}")
    if not (dir_path / "index.html").exists():
        raise DolCtlError("Source directory is missing index.html")
    if not version_id:
        version_id = _make_version_id(channel, dir_path.name)
    tmp_base = _download_cache_dir(root) / ".tmp"
    ensure_dir(tmp_base)
    temp_dir = Path(tempfile.mkdtemp(prefix="install_", dir=tmp_base))
    try:
        shutil.copytree(dir_path, temp_dir, dirs_exist_ok=True)
        manifest = VersionManifest(
            id=version_id,
            display_name=version_id,
            channel=channel,
            source="local",
            source_ref=str(dir_path),
            sha256=None,
            installed_at=now_iso(),
            entry="index.html",
        )
        _install_from_temp(root, temp_dir, version_id, manifest, force)
    except Exception:
        safe_rmtree(temp_dir)
        raise
    return version_id
