from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class DolCtlError(Exception):
    pass


@dataclass
class ChannelConfig:
    provider: str = "github"
    repo: str = ""
    asset_regex: str = ".*\\.zip$"


@dataclass
class Config:
    default_profile: str = "default"
    default_port: int = 8799
    open_browser: bool = True
    index_cache_ttl_seconds: int = 600
    channels: dict[str, ChannelConfig] = field(default_factory=dict)


@dataclass
class State:
    active_profile: str = "default"
    last_used_version: str = ""


@dataclass
class VersionManifest:
    id: str
    display_name: str
    channel: str
    source: str
    source_ref: str
    sha256: str | None
    installed_at: str
    entry: str = "index.html"


@dataclass
class Profile:
    name: str
    version_id: str = ""
    port: int | None = None
    open_browser: bool | None = None


@dataclass
class RemoteVersion:
    id: str
    display_name: str
    channel: str
    published_at: str
    asset_name: str
    download_url: str
    source_ref: str
    sha256: str | None = None


@dataclass
class InstalledVersion:
    id: str
    display_name: str
    channel: str
    source: str
    source_ref: str
    installed_at: str
    entry: str
    path: Path


@dataclass
class BuildResult:
    profile: str
    version_id: str
    output_dir: Path
    build_meta_path: Path


@dataclass
class RunResult:
    profile: str
    url: str
    port: int
    output_dir: Path
    server: Any
    open_browser: bool


def config_from_dict(data: dict[str, Any]) -> Config:
    channels: dict[str, ChannelConfig] = {}
    for name, cfg in (data.get("channels") or {}).items():
        if isinstance(cfg, dict):
            channels[name] = ChannelConfig(
                provider=str(cfg.get("provider", "github")),
                repo=str(cfg.get("repo", "")),
                asset_regex=str(cfg.get("asset_regex", ".*\\.zip$")),
            )
    return Config(
        default_profile=str(data.get("default_profile", "default")),
        default_port=int(data.get("default_port", 8799)),
        open_browser=bool(data.get("open_browser", True)),
        index_cache_ttl_seconds=int(data.get("index_cache_ttl_seconds", 600)),
        channels=channels,
    )


def config_to_dict(config: Config) -> dict[str, Any]:
    data: dict[str, Any] = {
        "default_profile": config.default_profile,
        "default_port": config.default_port,
        "open_browser": config.open_browser,
        "index_cache_ttl_seconds": config.index_cache_ttl_seconds,
    }
    if config.channels:
        data["channels"] = {
            name: {
                "provider": cfg.provider,
                "repo": cfg.repo,
                "asset_regex": cfg.asset_regex,
            }
            for name, cfg in config.channels.items()
        }
    return data


def state_from_dict(data: dict[str, Any]) -> State:
    return State(
        active_profile=str(data.get("active_profile", "default")),
        last_used_version=str(data.get("last_used_version", "")),
    )


def state_to_dict(state: State) -> dict[str, Any]:
    return {
        "active_profile": state.active_profile,
        "last_used_version": state.last_used_version,
    }


def profile_from_dict(data: dict[str, Any]) -> Profile:
    return Profile(
        name=str(data.get("name", "default")),
        version_id=str(data.get("version_id", "")),
        port=data.get("port"),
        open_browser=data.get("open_browser"),
    )


def profile_to_dict(profile: Profile) -> dict[str, Any]:
    data: dict[str, Any] = {
        "name": profile.name,
        "version_id": profile.version_id,
    }
    if profile.port is not None:
        data["port"] = profile.port
    if profile.open_browser is not None:
        data["open_browser"] = profile.open_browser
    return data


def version_manifest_to_dict(manifest: VersionManifest) -> dict[str, Any]:
    return {
        "id": manifest.id,
        "display_name": manifest.display_name,
        "channel": manifest.channel,
        "source": manifest.source,
        "source_ref": manifest.source_ref,
        "sha256": manifest.sha256 or "",
        "installed_at": manifest.installed_at,
        "entry": manifest.entry,
    }


def version_manifest_from_dict(data: dict[str, Any]) -> VersionManifest:
    return VersionManifest(
        id=str(data.get("id", "")),
        display_name=str(data.get("display_name", "")),
        channel=str(data.get("channel", "")),
        source=str(data.get("source", "")),
        source_ref=str(data.get("source_ref", "")),
        sha256=str(data.get("sha256", "")) or None,
        installed_at=str(data.get("installed_at", "")),
        entry=str(data.get("entry", "index.html")),
    )


def remote_version_to_dict(version: RemoteVersion) -> dict[str, Any]:
    return {
        "id": version.id,
        "display_name": version.display_name,
        "channel": version.channel,
        "published_at": version.published_at,
        "asset_name": version.asset_name,
        "download_url": version.download_url,
        "source_ref": version.source_ref,
        "sha256": version.sha256 or "",
    }


def remote_version_from_dict(data: dict[str, Any]) -> RemoteVersion:
    return RemoteVersion(
        id=str(data.get("id", "")),
        display_name=str(data.get("display_name", "")),
        channel=str(data.get("channel", "")),
        published_at=str(data.get("published_at", "")),
        asset_name=str(data.get("asset_name", "")),
        download_url=str(data.get("download_url", "")),
        source_ref=str(data.get("source_ref", "")),
        sha256=str(data.get("sha256", "")) or None,
    )
