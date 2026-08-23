from __future__ import annotations

from pathlib import Path
import tomllib
from typing import Any

from infra.fs import remove_tree
from infra.toml import read_toml, write_toml

from .models import (
    ConflictError,
    DataError,
    NotFoundError,
    Profile,
    RemoveResult,
    ValidationError,
    profile_from_dict,
    profile_to_dict,
)
from .root import (
    RootLayout,
    load_state,
    save_state,
    validate_port,
    validate_resource_name,
)


UNSET: Any = object()


def _profile_file(layout: RootLayout, name: str) -> Path:
    return layout.profile_dir(name) / "profile.toml"


def _read_profile(path: Path) -> Profile:
    if path.is_symlink():
        raise DataError(f"Instance manifest cannot be a symlink: {path}")
    try:
        return profile_from_dict(read_toml(path))
    except FileNotFoundError as exc:
        raise NotFoundError(f"Instance not found: {path.parent.name}") from exc
    except (OSError, tomllib.TOMLDecodeError, DataError) as exc:
        raise DataError(f"Cannot read instance manifest {path}: {exc}") from exc


def _validate_profile(profile: Profile) -> None:
    validate_resource_name(profile.name, "instance")
    if profile.version_id:
        validate_resource_name(profile.version_id, "version")
    if profile.port is not None:
        validate_port(profile.port)
    if len(profile.mod_order) != len(set(profile.mod_order)):
        raise ValidationError("An instance cannot contain the same mod twice")
    for mod_id in profile.mod_order:
        validate_resource_name(mod_id, "mod")


def list_profiles(root: Path) -> list[Profile]:
    layout = RootLayout.open(root)
    profiles: list[Profile] = []
    for directory in sorted(layout.profiles.iterdir(), key=lambda item: item.name):
        if not directory.is_dir():
            continue
        manifest = directory / "profile.toml"
        if not manifest.exists():
            continue
        profile = _read_profile(manifest)
        if profile.name != directory.name:
            raise DataError(
                f"Instance manifest name {profile.name!r} does not match "
                f"directory {directory.name!r}"
            )
        _validate_profile(profile)
        profiles.append(profile)
    return profiles


def get_profile(root: Path, name: str) -> Profile:
    layout = RootLayout.open(root)
    validate_resource_name(name, "instance")
    profile = _read_profile(_profile_file(layout, name))
    if profile.name != name:
        raise DataError(
            f"Instance manifest name {profile.name!r} does not match directory {name!r}"
        )
    _validate_profile(profile)
    return profile


def save_profile(root: Path, profile: Profile) -> Profile:
    layout = RootLayout.open(root)
    _validate_profile(profile)
    write_toml(_profile_file(layout, profile.name), profile_to_dict(profile))
    return profile


def active_profile_name(root: Path, requested: str | None = None) -> str:
    layout = RootLayout.open(root)
    if requested:
        name = validate_resource_name(requested, "instance")
    else:
        state = load_state(layout.root)
        name = state.active_profile or "default"
    get_profile(layout.root, name)
    return name


def create_profile(root: Path, name: str, *, version_id: str | None = None) -> Profile:
    layout = RootLayout.open(root)
    name = validate_resource_name(name, "instance")
    destination = layout.profile_dir(name)
    if destination.exists():
        raise ConflictError(f"Instance already exists: {name}")

    if version_id is None:
        candidate = load_state(layout.root).last_used_version
        version_id = (
            candidate if candidate and layout.version_dir(candidate).is_dir() else ""
        )
    elif version_id:
        version_id = validate_resource_name(version_id, "version")
        if not layout.version_dir(version_id).is_dir():
            raise NotFoundError(f"Version not found: {version_id}")

    profile = Profile(name=name, version_id=version_id or "")
    return save_profile(layout.root, profile)


def select_profile(root: Path, name: str) -> Profile:
    layout = RootLayout.open(root)
    profile = get_profile(layout.root, name)
    state = load_state(layout.root)
    state.active_profile = profile.name
    save_state(layout.root, state)
    return profile


def configure_profile(
    root: Path,
    name: str,
    *,
    version_id: str | None | object = UNSET,
    port: int | None | object = UNSET,
    open_browser: bool | None | object = UNSET,
) -> Profile:
    layout = RootLayout.open(root)
    profile = get_profile(layout.root, name)

    if version_id is not UNSET:
        if version_id is None or version_id == "":
            profile.version_id = ""
        else:
            assert isinstance(version_id, str)
            validate_resource_name(version_id, "version")
            if not layout.version_dir(version_id).is_dir():
                raise NotFoundError(f"Version not found: {version_id}")
            profile.version_id = version_id
            state = load_state(layout.root)
            state.last_used_version = version_id
            save_state(layout.root, state)

    if port is not UNSET:
        if port is not None:
            assert isinstance(port, int)
            validate_port(port)
        profile.port = port

    if open_browser is not UNSET:
        if open_browser is not None and not isinstance(open_browser, bool):
            raise ValidationError("open_browser must be true, false, or unset")
        profile.open_browser = open_browser

    return save_profile(layout.root, profile)


def set_profile_version(root: Path, profile_name: str, version_id: str) -> Profile:
    return configure_profile(root, profile_name, version_id=version_id)


def delete_profile(root: Path, name: str) -> RemoveResult:
    layout = RootLayout.open(root)
    name = validate_resource_name(name, "instance")
    if name == "default":
        raise ConflictError("The default instance cannot be deleted")
    get_profile(layout.root, name)

    state = load_state(layout.root)
    if state.active_profile == name:
        state.active_profile = "default"
        save_state(layout.root, state)

    remove_tree(layout.profile_dir(name), within=layout.profiles)
    remove_tree(layout.runtime_dir(name), within=layout.runtime)
    return RemoveResult(name)


def add_mod_to_profile(root: Path, profile_name: str, mod_id: str) -> Profile:
    layout = RootLayout.open(root)
    mod_id = validate_resource_name(mod_id, "mod")
    if not (layout.mod_dir(mod_id) / ".mod.toml").is_file():
        raise NotFoundError(f"Mod not found: {mod_id}")
    profile = get_profile(layout.root, profile_name)
    if mod_id in profile.mod_order:
        raise ConflictError(f"Mod already enabled: {mod_id}")
    profile.mod_order.append(mod_id)
    return save_profile(layout.root, profile)


def remove_mod_from_profile(root: Path, profile_name: str, mod_id: str) -> Profile:
    profile = get_profile(root, profile_name)
    if mod_id not in profile.mod_order:
        raise NotFoundError(f"Mod is not enabled in {profile_name}: {mod_id}")
    profile.mod_order.remove(mod_id)
    return save_profile(root, profile)


def reorder_mods(root: Path, profile_name: str, ordered_mod_ids: list[str]) -> Profile:
    profile = get_profile(root, profile_name)
    if len(ordered_mod_ids) != len(set(ordered_mod_ids)):
        raise ValidationError("Mod order contains duplicates")
    if set(ordered_mod_ids) != set(profile.mod_order):
        raise ValidationError(
            "New mod order must contain exactly the currently enabled mods"
        )
    profile.mod_order = list(ordered_mod_ids)
    return save_profile(root, profile)


def remove_mod_from_all_profiles(root: Path, mod_id: str) -> tuple[str, ...]:
    affected: list[str] = []
    for profile in list_profiles(root):
        if mod_id not in profile.mod_order:
            continue
        profile.mod_order = [item for item in profile.mod_order if item != mod_id]
        save_profile(root, profile)
        affected.append(profile.name)
    return tuple(affected)


def clear_version_from_profiles(root: Path, version_id: str) -> tuple[str, ...]:
    affected: list[str] = []
    for profile in list_profiles(root):
        if profile.version_id != version_id:
            continue
        profile.version_id = ""
        save_profile(root, profile)
        affected.append(profile.name)
    state = load_state(root)
    if state.last_used_version == version_id:
        state.last_used_version = ""
        save_state(root, state)
    return tuple(affected)
