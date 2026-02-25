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


def add_mod_to_profile(root: Path, profile_name: str, mod_id: str) -> None:
    """Append mod_id to the end of the profile's mod_order list."""
    mod_toml = root / "mods" / mod_id / ".mod.toml"
    if not mod_toml.exists():
        raise DolCtlError(f"Mod not found: {mod_id}")
    profile = get_profile(root, profile_name)
    if mod_id in profile.mod_order:
        raise DolCtlError(f"Mod already in profile: {mod_id}")
    profile.mod_order.append(mod_id)
    save_profile(root, profile)


def remove_mod_from_profile(root: Path, profile_name: str, mod_id: str) -> None:
    """Remove mod_id from the profile's mod_order list."""
    profile = get_profile(root, profile_name)
    if mod_id not in profile.mod_order:
        raise DolCtlError(f"Mod not in profile: {mod_id}")
    profile.mod_order.remove(mod_id)
    save_profile(root, profile)


def reorder_mods(root: Path, profile_name: str, ordered_mod_ids: list[str]) -> None:
    """Replace mod_order with the given ordered list (all ids must exist in profile)."""
    profile = get_profile(root, profile_name)
    current = set(profile.mod_order)
    requested = set(ordered_mod_ids)
    if current != requested:
        raise DolCtlError(
            f"Reorder list must contain exactly the same mods as the profile.\n"
            f"  Profile has: {sorted(current)}\n"
            f"  Provided:    {sorted(requested)}"
        )
    profile.mod_order = list(ordered_mod_ids)
    save_profile(root, profile)
