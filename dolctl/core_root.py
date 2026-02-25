from __future__ import annotations

from pathlib import Path
import os

from .infra_fs import ensure_dir, find_root
from .infra_toml import read_toml, write_toml
from .models import Config, State, Profile, DolCtlError
from .models import (
    config_from_dict,
    config_to_dict,
    state_from_dict,
    state_to_dict,
    profile_to_dict,
)


def resolve_root(cli_root: str | None) -> Path:
    if cli_root:
        return Path(cli_root).expanduser().resolve()
    env_root = os.environ.get("DOLCTL_ROOT")
    if env_root:
        return Path(env_root).expanduser().resolve()
    found = find_root(Path.cwd())
    if found is None:
        raise DolCtlError("No root found. Run: dolctl init <dir>")
    return found


def init_root(root: Path) -> None:
    root = root.expanduser().resolve()
    ensure_dir(root)

    dolctl_dir = root / ".dolctl"
    ensure_dir(dolctl_dir)
    ensure_dir(dolctl_dir / "cache" / "downloads")
    ensure_dir(dolctl_dir / "cache" / "index")
    ensure_dir(dolctl_dir / "logs")

    ensure_dir(root / "versions")
    ensure_dir(root / "mods")
    ensure_dir(root / "profiles" / "default")
    ensure_dir(root / "runtime")

    config_path = dolctl_dir / "config.toml"
    if not config_path.exists():
        write_toml(config_path, config_to_dict(Config()))

    state_path = dolctl_dir / "state.toml"
    if not state_path.exists():
        write_toml(state_path, state_to_dict(State()))

    profile_path = root / "profiles" / "default" / "profile.toml"
    if not profile_path.exists():
        profile = Profile(name="default")
        write_toml(profile_path, profile_to_dict(profile))


def load_config(root: Path) -> Config:
    path = root / ".dolctl" / "config.toml"
    data = read_toml(path)
    return config_from_dict(data)


def save_config(root: Path, config: Config) -> None:
    path = root / ".dolctl" / "config.toml"
    write_toml(path, config_to_dict(config))


def load_state(root: Path) -> State:
    path = root / ".dolctl" / "state.toml"
    data = read_toml(path)
    return state_from_dict(data)


def save_state(root: Path, state: State) -> None:
    path = root / ".dolctl" / "state.toml"
    write_toml(path, state_to_dict(state))
