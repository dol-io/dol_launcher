from __future__ import annotations

import json
from pathlib import Path

from .models import DoctorCheck, DoctorReport, DolCtlError
from .mods import get_mod_info
from .profiles import get_profile
from .root import RootLayout, load_config, load_state
from .versions import get_installed


def run_doctor(root: Path) -> DoctorReport:
    layout = RootLayout.open(root)
    checks: list[DoctorCheck] = [
        DoctorCheck("root", True, f"ROOT: {layout.root}"),
    ]
    for name, directory in (
        ("control", layout.root / ".dolctl"),
        ("versions", layout.root / "versions"),
        ("mods", layout.root / "mods"),
        ("profiles", layout.root / "profiles"),
        ("runtime", layout.root / "runtime"),
    ):
        checks.append(
            DoctorCheck(
                f"directory.{name}",
                directory.is_dir() and not directory.is_symlink(),
                f"{directory.relative_to(layout.root)}/",
            )
        )

    try:
        config = load_config(layout.root)
        checks.append(
            DoctorCheck(
                "config",
                True,
                f"Configuration is valid ({len(config.channels)} sources)",
            )
        )
    except DolCtlError as exc:
        checks.append(DoctorCheck("config", False, str(exc)))

    try:
        state = load_state(layout.root)
        checks.append(DoctorCheck("state", True, "State is valid"))
    except DolCtlError as exc:
        state = None
        checks.append(DoctorCheck("state", False, str(exc)))

    versions: set[str] = set()
    versions_path = layout.root / "versions"
    version_dirs = (
        versions_path.iterdir()
        if versions_path.is_dir() and not versions_path.is_symlink()
        else ()
    )
    for directory in sorted(version_dirs, key=lambda item: item.name):
        if not directory.is_dir():
            continue
        try:
            version = get_installed(layout.root, directory.name)
            versions.add(version.id)
            checks.append(
                DoctorCheck(
                    f"version.{directory.name}",
                    True,
                    f"Version {version.id} is valid",
                )
            )
        except DolCtlError as exc:
            checks.append(DoctorCheck(f"version.{directory.name}", False, str(exc)))

    mods: set[str] = set()
    mods_path = layout.root / "mods"
    mod_dirs = (
        mods_path.iterdir() if mods_path.is_dir() and not mods_path.is_symlink() else ()
    )
    for directory in sorted(mod_dirs, key=lambda item: item.name):
        if not directory.is_dir():
            continue
        try:
            mod = get_mod_info(layout.root, directory.name)
            mods.add(mod.id)
            checks.append(
                DoctorCheck(f"mod.{directory.name}", True, f"Mod {mod.id} is valid")
            )
        except DolCtlError as exc:
            checks.append(DoctorCheck(f"mod.{directory.name}", False, str(exc)))

    profiles: set[str] = set()
    profiles_path = layout.root / "profiles"
    profile_dirs = (
        profiles_path.iterdir()
        if profiles_path.is_dir() and not profiles_path.is_symlink()
        else ()
    )
    for directory in sorted(profile_dirs, key=lambda item: item.name):
        if not directory.is_dir():
            continue
        try:
            profile = get_profile(layout.root, directory.name)
            profiles.add(profile.name)
            missing_mods = [
                mod_id for mod_id in profile.mod_order if mod_id not in mods
            ]
            if profile.version_id and profile.version_id not in versions:
                checks.append(
                    DoctorCheck(
                        f"profile.{profile.name}.version",
                        False,
                        f"Instance {profile.name} references missing version "
                        f"{profile.version_id}",
                    )
                )
            if missing_mods:
                checks.append(
                    DoctorCheck(
                        f"profile.{profile.name}.mods",
                        False,
                        f"Instance {profile.name} references missing mods: "
                        + ", ".join(missing_mods),
                    )
                )
            if not missing_mods and (
                not profile.version_id or profile.version_id in versions
            ):
                checks.append(
                    DoctorCheck(
                        f"profile.{profile.name}",
                        True,
                        f"Instance {profile.name} is valid",
                    )
                )
        except DolCtlError as exc:
            checks.append(DoctorCheck(f"profile.{directory.name}", False, str(exc)))

    checks.append(
        DoctorCheck(
            "profile.default",
            "default" in profiles,
            "Default instance exists"
            if "default" in profiles
            else "Default instance is missing",
        )
    )
    if state is not None:
        checks.append(
            DoctorCheck(
                "profile.active",
                state.active_profile in profiles,
                f"Active instance: {state.active_profile}"
                if state.active_profile in profiles
                else f"Active instance is missing: {state.active_profile}",
            )
        )

    for name in profiles:
        try:
            runtime = layout.runtime_dir(name)
        except DolCtlError as exc:
            checks.append(DoctorCheck(f"runtime.{name}", False, str(exc)))
            continue
        if not runtime.exists():
            continue
        metadata = runtime / "build_meta.json"
        try:
            payload = json.loads(metadata.read_text(encoding="utf-8"))
            complete = isinstance(payload, dict)
            entry = payload.get("entry") if complete else None
            complete = (
                complete
                and isinstance(entry, str)
                and isinstance(payload.get("build_key"), str)
                and (runtime / "merged" / entry).is_file()
            )
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            complete = False
        checks.append(
            DoctorCheck(
                f"runtime.{name}",
                complete,
                f"Runtime for {name} is complete"
                if complete
                else f"Runtime for {name} is incomplete; rebuild it",
            )
        )

    return DoctorReport(tuple(checks))
