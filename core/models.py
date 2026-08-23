from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, cast, Literal


class DolCtlError(Exception):
    """Base class for expected, user-facing launcher failures."""


class ValidationError(DolCtlError):
    """Input or persisted data does not satisfy the launcher contract."""


class NotFoundError(DolCtlError):
    """A requested launcher resource does not exist."""


class ConflictError(DolCtlError):
    """A mutation conflicts with existing launcher state."""


class DataError(DolCtlError):
    """Persisted launcher data is missing, corrupt, or unsupported."""


class ExternalError(DolCtlError):
    """A network, archive, browser, or operating-system operation failed."""


ProgressCallback = Callable[[int, int | None], None]
BuildStatus = Literal["full", "cache-hit"]
ChannelKind = Literal["game", "mod"]
CHANNEL_KINDS: tuple[ChannelKind, ...] = ("game", "mod")


@dataclass(slots=True)
class ChannelConfig:
    kind: ChannelKind = "game"
    provider: str = "github"
    repo: str = ""
    asset_regex: str = r".*\.zip"
    extra: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class Config:
    schema_version: int = 1
    default_profile: str = "default"
    default_port: int = 8799
    open_browser: bool = True
    index_cache_ttl_seconds: int = 600
    channels: dict[str, ChannelConfig] = field(default_factory=dict)


@dataclass(slots=True)
class State:
    schema_version: int = 1
    active_profile: str = "default"
    last_used_version: str = ""


@dataclass(slots=True)
class VersionManifest:
    id: str
    display_name: str
    channel: str
    source: str
    source_ref: str
    sha256: str | None
    installed_at: str
    entry: str = "index.html"
    revision: str = ""
    schema_version: int = 1


@dataclass(slots=True)
class InstalledVersion:
    id: str
    display_name: str
    channel: str
    source: str
    source_ref: str
    installed_at: str
    entry: str
    revision: str
    path: Path


@dataclass(slots=True)
class Mod:
    id: str
    name: str
    version: str
    author: str
    description: str
    source: str
    source_ref: str
    installed_at: str
    sha256: str
    path: Path
    schema_version: int = 1


@dataclass(slots=True)
class Profile:
    name: str
    version_id: str = ""
    mod_order: list[str] = field(default_factory=list)
    port: int | None = None
    open_browser: bool | None = None
    schema_version: int = 1


@dataclass(slots=True)
class RemoteVersion:
    id: str
    display_name: str
    channel: str
    published_at: str
    asset_name: str
    download_url: str
    source_ref: str
    sha256: str | None = None


@dataclass(frozen=True, slots=True)
class BuildResult:
    profile: str
    version_id: str
    output_dir: Path
    build_meta_path: Path
    entry: str
    build_key: str
    status: BuildStatus


@dataclass(frozen=True, slots=True)
class RemoveResult:
    resource_id: str
    affected_profiles: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class DoctorCheck:
    key: str
    ok: bool
    message: str


@dataclass(frozen=True, slots=True)
class DoctorReport:
    checks: tuple[DoctorCheck, ...]

    @property
    def ok(self) -> bool:
        return all(check.ok for check in self.checks)


_RESERVED_CHANNEL_KEYS = {"kind", "provider", "repo", "asset_regex"}


def _schema(data: dict[str, Any], *, maximum: int = 1) -> int:
    value = data.get("schema_version", 0)
    if isinstance(value, bool) or not isinstance(value, int):
        raise DataError("schema_version must be an integer")
    if value < 0 or value > maximum:
        raise DataError(f"Unsupported schema_version: {value}")
    return value


def _string(
    data: dict[str, Any], key: str, default: str = "", *, required: bool = False
) -> str:
    value = data.get(key, default)
    if not isinstance(value, str):
        raise DataError(f"{key} must be a string")
    if required and not value:
        raise DataError(f"{key} is required")
    return value


def _integer(data: dict[str, Any], key: str, default: int) -> int:
    value = data.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int):
        raise DataError(f"{key} must be an integer")
    return value


def _boolean(data: dict[str, Any], key: str, default: bool) -> bool:
    value = data.get(key, default)
    if not isinstance(value, bool):
        raise DataError(f"{key} must be a boolean")
    return value


def _optional_integer(data: dict[str, Any], key: str) -> int | None:
    value = data.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise DataError(f"{key} must be an integer")
    return value


def _optional_boolean(data: dict[str, Any], key: str) -> bool | None:
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, bool):
        raise DataError(f"{key} must be a boolean")
    return value


def _string_list(data: dict[str, Any], key: str) -> list[str]:
    value = data.get(key, [])
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise DataError(f"{key} must be an array of strings")
    return list(value)


def config_from_dict(data: dict[str, Any]) -> Config:
    _schema(data)
    raw_channels = data.get("channels", {})
    if not isinstance(raw_channels, dict):
        raise DataError("channels must be a table")
    channels: dict[str, ChannelConfig] = {}
    for name, raw in raw_channels.items():
        if not isinstance(name, str) or not isinstance(raw, dict):
            raise DataError("Each channel must be a named table")
        extra = {
            str(key): str(value)
            for key, value in raw.items()
            if key not in _RESERVED_CHANNEL_KEYS
        }
        raw_kind = _string(raw, "kind", "game")
        if raw_kind not in CHANNEL_KINDS:
            raise DataError("channel kind must be 'game' or 'mod'")
        channels[name] = ChannelConfig(
            kind=cast(ChannelKind, raw_kind),
            provider=_string(raw, "provider", "github"),
            repo=_string(raw, "repo"),
            asset_regex=_string(raw, "asset_regex", r".*\.zip"),
            extra=extra,
        )
    return Config(
        schema_version=1,
        default_profile=_string(data, "default_profile", "default"),
        default_port=_integer(data, "default_port", 8799),
        open_browser=_boolean(data, "open_browser", True),
        index_cache_ttl_seconds=_integer(data, "index_cache_ttl_seconds", 600),
        channels=channels,
    )


def config_to_dict(config: Config) -> dict[str, Any]:
    data: dict[str, Any] = {
        "schema_version": 1,
        "default_profile": config.default_profile,
        "default_port": config.default_port,
        "open_browser": config.open_browser,
        "index_cache_ttl_seconds": config.index_cache_ttl_seconds,
    }
    if config.channels:
        data["channels"] = {
            name: {
                "kind": channel.kind,
                "provider": channel.provider,
                "repo": channel.repo,
                "asset_regex": channel.asset_regex,
                **channel.extra,
            }
            for name, channel in config.channels.items()
        }
    return data


def state_from_dict(data: dict[str, Any]) -> State:
    _schema(data)
    return State(
        schema_version=1,
        active_profile=_string(data, "active_profile", "default"),
        last_used_version=_string(data, "last_used_version"),
    )


def state_to_dict(state: State) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "active_profile": state.active_profile,
        "last_used_version": state.last_used_version,
    }


def profile_from_dict(data: dict[str, Any]) -> Profile:
    _schema(data)
    return Profile(
        schema_version=1,
        name=_string(data, "name", required=True),
        version_id=_string(data, "version_id"),
        mod_order=_string_list(data, "mod_order"),
        port=_optional_integer(data, "port"),
        open_browser=_optional_boolean(data, "open_browser"),
    )


def profile_to_dict(profile: Profile) -> dict[str, Any]:
    data: dict[str, Any] = {
        "schema_version": 1,
        "name": profile.name,
        "version_id": profile.version_id,
        "mod_order": list(profile.mod_order),
    }
    if profile.port is not None:
        data["port"] = profile.port
    if profile.open_browser is not None:
        data["open_browser"] = profile.open_browser
    return data


def mod_from_dict(data: dict[str, Any], path: Path) -> Mod:
    _schema(data)
    return Mod(
        schema_version=1,
        id=_string(data, "id", required=True),
        name=_string(data, "name", required=True),
        version=_string(data, "version"),
        author=_string(data, "author"),
        description=_string(data, "description"),
        source=_string(data, "source", "local"),
        source_ref=_string(data, "source_ref"),
        installed_at=_string(data, "installed_at"),
        sha256=_string(data, "sha256"),
        path=path,
    )


def mod_to_dict(mod: Mod) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "id": mod.id,
        "name": mod.name,
        "version": mod.version,
        "author": mod.author,
        "description": mod.description,
        "source": mod.source,
        "source_ref": mod.source_ref,
        "installed_at": mod.installed_at,
        "sha256": mod.sha256,
    }


def version_manifest_from_dict(data: dict[str, Any]) -> VersionManifest:
    _schema(data)
    return VersionManifest(
        schema_version=1,
        id=_string(data, "id", required=True),
        display_name=_string(data, "display_name", required=True),
        channel=_string(data, "channel", required=True),
        source=_string(data, "source", required=True),
        source_ref=_string(data, "source_ref"),
        sha256=_string(data, "sha256") or None,
        installed_at=_string(data, "installed_at"),
        entry=_string(data, "entry", "index.html"),
        revision=_string(data, "revision"),
    )


def version_manifest_to_dict(manifest: VersionManifest) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "id": manifest.id,
        "display_name": manifest.display_name,
        "channel": manifest.channel,
        "source": manifest.source,
        "source_ref": manifest.source_ref,
        "sha256": manifest.sha256 or "",
        "installed_at": manifest.installed_at,
        "entry": manifest.entry,
        "revision": manifest.revision,
    }


def remote_version_from_dict(data: dict[str, Any]) -> RemoteVersion:
    return RemoteVersion(
        id=_string(data, "id", required=True),
        display_name=_string(data, "display_name", required=True),
        channel=_string(data, "channel", required=True),
        published_at=_string(data, "published_at"),
        asset_name=_string(data, "asset_name", required=True),
        download_url=_string(data, "download_url", required=True),
        source_ref=_string(data, "source_ref"),
        sha256=_string(data, "sha256") or None,
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
