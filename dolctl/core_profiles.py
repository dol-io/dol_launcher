from __future__ import annotations

from pathlib import Path

from .infra_fs import ensure_dir
from .infra_toml import read_toml, write_toml
from .models import Profile, DolCtlError
from .models import profile_from_dict, profile_to_dict
from .core_root import load_state, save_state


def _profile_dir(root: Path, name: str) -> Path:
    return root / "profiles" / name


def _profile_path(root: Path, name: str) -> Path:
    return _profile_dir(root, name) / "profile.toml"


def list_profiles(root: Path) -> list[str]:
    profiles_dir = root / "profiles"
    if not profiles_dir.exists():
        return []
    return sorted([p.name for p in profiles_dir.iterdir() if p.is_dir()])


def get_profile(root: Path, name: str) -> Profile:
    path = _profile_path(root, name)
    if not path.exists():
        raise DolCtlError(f"Profile not found: {name}")
    data = read_toml(path)
    profile = profile_from_dict(data)
    if not profile.name:
        profile.name = name
    return profile


def save_profile(root: Path, profile: Profile) -> None:
    path = _profile_path(root, profile.name)
    ensure_dir(path.parent)
    write_toml(path, profile_to_dict(profile))


def create_profile(root: Path, name: str) -> None:
    path = _profile_path(root, name)
    if path.exists():
        raise DolCtlError(f"Profile already exists: {name}")
    state = load_state(root)
    profile = Profile(name=name, version_id=state.last_used_version)
    save_profile(root, profile)


def set_active_profile(root: Path, name: str) -> None:
    if not _profile_path(root, name).exists():
        raise DolCtlError(f"Profile not found: {name}")
    state = load_state(root)
    state.active_profile = name
    save_state(root, state)


def set_profile_version(root: Path, profile_name: str, version_id: str) -> None:
    version_dir = root / "versions" / version_id
    if not version_dir.exists():
        raise DolCtlError(f"Version not found: {version_id}")
    profile = get_profile(root, profile_name)
    profile.version_id = version_id
    save_profile(root, profile)
    state = load_state(root)
    state.last_used_version = version_id
    save_state(root, state)
