from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import re
import tomllib

from infra.fs import ensure_dir, ensure_safe_subdirectory, find_root
from infra.toml import read_toml, write_toml

from .channel_presets import get_preset
from .models import (
    ChannelConfig,
    Config,
    DataError,
    Profile,
    State,
    ValidationError,
    config_from_dict,
    config_to_dict,
    profile_to_dict,
    state_from_dict,
    state_to_dict,
)


_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


def validate_resource_name(value: str, kind: str = "resource") -> str:
    if not isinstance(value, str) or not value:
        raise ValidationError(f"{kind} name cannot be empty")
    if value != value.strip():
        raise ValidationError(f"{kind} name cannot start or end with whitespace")
    if len(value) > 128:
        raise ValidationError(f"{kind} name is too long")
    if value in {".", ".."} or value.startswith("."):
        raise ValidationError(f"Unsafe {kind} name: {value!r}")
    if "/" in value or "\\" in value or ":" in value or _CONTROL.search(value):
        raise ValidationError(f"Unsafe {kind} name: {value!r}")
    if Path(value).is_absolute():
        raise ValidationError(f"Unsafe {kind} name: {value!r}")
    return value


def validate_port(port: int) -> int:
    if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
        raise ValidationError(f"Port must be between 1 and 65535: {port}")
    return port


@dataclass(frozen=True, slots=True)
class RootLayout:
    root: Path

    @classmethod
    def open(cls, root: Path) -> "RootLayout":
        resolved = root.expanduser().resolve()
        if not (resolved / ".dolctl").is_dir():
            raise DataError(
                f"Not a dolctl root: {resolved}. Run: dolctl init {resolved}"
            )
        return cls(resolved)

    def _safe_path(self, *parts: str) -> Path:
        current = self.root
        for part in parts:
            current = current / part
            if current.is_symlink():
                relative = current.relative_to(self.root)
                raise DataError(f"Launcher path cannot be a symlink: {relative}")
        return current

    @property
    def control(self) -> Path:
        return self._safe_path(".dolctl")

    @property
    def versions(self) -> Path:
        return self._safe_path("versions")

    @property
    def mods(self) -> Path:
        return self._safe_path("mods")

    @property
    def profiles(self) -> Path:
        return self._safe_path("profiles")

    @property
    def runtime(self) -> Path:
        return self._safe_path("runtime")

    @property
    def config_file(self) -> Path:
        return self._safe_path(".dolctl", "config.toml")

    @property
    def state_file(self) -> Path:
        return self._safe_path(".dolctl", "state.toml")

    @property
    def index_cache(self) -> Path:
        return self._safe_path(".dolctl", "cache", "index")

    @property
    def download_cache(self) -> Path:
        return self._safe_path(".dolctl", "cache", "downloads")

    def version_dir(self, version_id: str) -> Path:
        safe_id = validate_resource_name(version_id, "version")
        return self._safe_path("versions", safe_id)

    def mod_dir(self, mod_id: str) -> Path:
        safe_id = validate_resource_name(mod_id, "mod")
        return self._safe_path("mods", safe_id)

    def profile_dir(self, name: str) -> Path:
        safe_name = validate_resource_name(name, "instance")
        return self._safe_path("profiles", safe_name)

    def runtime_dir(self, name: str) -> Path:
        safe_name = validate_resource_name(name, "instance")
        return self._safe_path("runtime", safe_name)

    def channel_cache_file(self, name: str) -> Path:
        safe_name = validate_resource_name(name, "channel")
        return self._safe_path(".dolctl", "cache", "index", f"{safe_name}.json")


def resolve_root(cli_root: str | Path | None = None) -> Path:
    if cli_root is not None:
        return RootLayout.open(Path(cli_root)).root
    environment_root = os.environ.get("DOLCTL_ROOT")
    if environment_root:
        return RootLayout.open(Path(environment_root)).root
    found = find_root(Path.cwd())
    if found is None:
        raise DataError("No dolctl root found. Run: dolctl init <dir>")
    return RootLayout.open(found).root


def _default_config() -> Config:
    modloader = get_preset("dol-modloader")
    return Config(
        channels={
            "modloader": ChannelConfig(
                kind=modloader.kind,
                provider=modloader.provider,
                repo=modloader.repo,
                asset_regex=modloader.asset_regex,
            ),
        }
    )


def init_root(root: Path) -> RootLayout:
    resolved = root.expanduser().resolve()
    ensure_dir(resolved)
    layout = RootLayout(resolved)
    for parts in (
        (".dolctl", "cache", "downloads"),
        (".dolctl", "cache", "index"),
        (".dolctl", "logs"),
        (".dolctl", "staging"),
        ("versions",),
        ("mods",),
        ("profiles",),
        ("runtime",),
    ):
        ensure_safe_subdirectory(resolved, *parts)
    if not layout.config_file.exists():
        write_toml(layout.config_file, config_to_dict(_default_config()))
    if not layout.state_file.exists():
        write_toml(layout.state_file, state_to_dict(State()))
    default_profile = layout.profile_dir("default") / "profile.toml"
    if not default_profile.exists():
        write_toml(default_profile, profile_to_dict(Profile(name="default")))
    return RootLayout.open(resolved)


def _read(path: Path, label: str) -> dict:
    try:
        return read_toml(path)
    except FileNotFoundError as exc:
        raise DataError(f"Missing {label}: {path}") from exc
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise DataError(f"Cannot read {label}: {path}: {exc}") from exc


def load_config(root: Path) -> Config:
    layout = RootLayout.open(root)
    config = config_from_dict(_read(layout.config_file, "config"))
    validate_resource_name(config.default_profile, "default instance")
    validate_port(config.default_port)
    if config.index_cache_ttl_seconds < 0:
        raise DataError("index_cache_ttl_seconds cannot be negative")
    import providers

    for name, channel in config.channels.items():
        validate_resource_name(name, "channel")
        providers.validate_config(channel)
    return config


def save_config(root: Path, config: Config) -> None:
    layout = RootLayout.open(root)
    validate_resource_name(config.default_profile, "default instance")
    validate_port(config.default_port)
    if config.index_cache_ttl_seconds < 0:
        raise ValidationError("index_cache_ttl_seconds cannot be negative")
    import providers

    for name, channel in config.channels.items():
        validate_resource_name(name, "channel")
        providers.validate_config(channel)
    write_toml(layout.config_file, config_to_dict(config))


def load_state(root: Path) -> State:
    layout = RootLayout.open(root)
    state = state_from_dict(_read(layout.state_file, "state"))
    if state.active_profile:
        validate_resource_name(state.active_profile, "active instance")
    if state.last_used_version:
        validate_resource_name(state.last_used_version, "last-used version")
    return state


def save_state(root: Path, state: State) -> None:
    layout = RootLayout.open(root)
    if state.active_profile:
        validate_resource_name(state.active_profile, "active instance")
    if state.last_used_version:
        validate_resource_name(state.last_used_version, "last-used version")
    write_toml(layout.state_file, state_to_dict(state))
