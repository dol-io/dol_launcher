from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
import re

from infra.fs import (
    atomic_write_text,
    copy_tree,
    ensure_dir,
    now_iso,
    replace_directory,
    staging_directory,
)

from .models import (
    BuildResult,
    BuildStatus,
    DataError,
    DolCtlError,
    ExternalError,
    NotFoundError,
)
from .mods import get_mod_info
from .profiles import get_profile
from .root import RootLayout
from .versions import get_installed


BUILD_META_SCHEMA = 3
IGNORED_VERSION_FILES = {".manifest.toml"}
_MOD_LIST = re.compile(
    r"window\.modDataValueZipList\s*=\s*(\[.*?\]);",
    re.DOTALL,
)


def _encode_mod(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode("ascii")


def _inject_mods_into_html(html_path: Path, mod_archives: list[Path]) -> None:
    content = html_path.read_text(encoding="utf-8")
    encoded = [_encode_mod(path) for path in mod_archives]
    match = _MOD_LIST.search(content)
    if match is not None:
        try:
            existing = json.loads(match.group(1))
        except json.JSONDecodeError as exc:
            raise DataError(
                "The base game's window.modDataValueZipList is not valid JSON"
            ) from exc
        if not isinstance(existing, list) or not all(
            isinstance(item, str) for item in existing
        ):
            raise DataError("The base game's mod list must be an array of strings")
        combined = existing + encoded
        replacement = (
            "window.modDataValueZipList = "
            + json.dumps(combined, separators=(",", ":"))
            + ";"
        )
        content = content[: match.start()] + replacement + content[match.end() :]
    else:
        script = (
            '<script id="dolctl-mods" type="text/javascript">'
            "window.modDataValueZipList = "
            + json.dumps(encoded, separators=(",", ":"))
            + ";</script>"
        )
        closing_head = re.search(r"</head\s*>", content, re.IGNORECASE)
        if closing_head is None:
            content = script + "\n" + content
        else:
            content = (
                content[: closing_head.start()]
                + script
                + "\n"
                + content[closing_head.start() :]
            )
    atomic_write_text(html_path, content)


def _build_key(version_revision: str, mods: list[tuple[str, str]]) -> str:
    canonical = json.dumps(
        {
            "version_revision": version_revision,
            "mods": [{"id": mod_id, "sha256": sha256} for mod_id, sha256 in mods],
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


def expected_build_key(root: Path, profile_name: str) -> str:
    """Return the build key for the instance's current immutable inputs."""
    profile = get_profile(root, profile_name)
    if not profile.version_id:
        raise NotFoundError(f"Instance has no version selected: {profile_name}")
    version = get_installed(root, profile.version_id)
    mods = [(mod_id, get_mod_info(root, mod_id).sha256) for mod_id in profile.mod_order]
    return _build_key(version.revision, mods)


def _read_meta(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict) or data.get("schema_version") != BUILD_META_SCHEMA:
        return None
    return data


def _result(
    layout: RootLayout,
    profile_name: str,
    version_id: str,
    entry: str,
    key: str,
    status: BuildStatus,
) -> BuildResult:
    runtime = layout.runtime_dir(profile_name)
    return BuildResult(
        profile=profile_name,
        version_id=version_id,
        output_dir=runtime / "merged",
        build_meta_path=runtime / "build_meta.json",
        entry=entry,
        build_key=key,
        status=status,
    )


def build_runtime(root: Path, profile_name: str, *, clean: bool = False) -> BuildResult:
    layout = RootLayout.open(root)
    profile = get_profile(layout.root, profile_name)
    if not profile.version_id:
        raise NotFoundError(f"Instance has no version selected: {profile_name}")
    version = get_installed(layout.root, profile.version_id)

    mods: list[tuple[str, str, Path]] = []
    for mod_id in profile.mod_order:
        mod = get_mod_info(layout.root, mod_id)
        archive = mod.path / f"{mod.id}.mod.zip"
        mods.append((mod.id, mod.sha256, archive))

    key = _build_key(version.revision, [(item[0], item[1]) for item in mods])
    runtime = layout.runtime_dir(profile.name)
    merged = runtime / "merged"
    metadata = runtime / "build_meta.json"
    previous = None if clean else _read_meta(metadata)
    if (
        previous is not None
        and previous.get("build_key") == key
        and (merged / version.entry).is_file()
    ):
        return _result(
            layout,
            profile.name,
            version.id,
            version.entry,
            key,
            "cache-hit",
        )

    try:
        with staging_directory(layout.root, "builds") as workspace:
            staged_runtime = ensure_dir(workspace / "runtime")
            staged_merged = ensure_dir(staged_runtime / "merged")
            copy_tree(
                version.path,
                staged_merged,
                ignored_names=IGNORED_VERSION_FILES,
            )
            entry = staged_merged / version.entry
            if not entry.is_file():
                raise DataError(f"Built entry HTML is missing: {version.entry}")
            if mods:
                _inject_mods_into_html(entry, [item[2] for item in mods])

            build_meta = {
                "schema_version": BUILD_META_SCHEMA,
                "profile": profile.name,
                "base_version_id": version.id,
                "version_revision": version.revision,
                "entry": version.entry,
                "build_key": key,
                "mod_order": [
                    {"id": mod_id, "sha256": sha256}
                    for mod_id, sha256, _archive in mods
                ],
                "built_at": now_iso(),
            }
            atomic_write_text(
                staged_runtime / "build_meta.json",
                json.dumps(build_meta, indent=2) + "\n",
            )
            replace_directory(
                staged_runtime,
                runtime,
                collection=layout.runtime,
                force=True,
            )
    except DolCtlError:
        raise
    except Exception as exc:
        raise ExternalError(f"Could not build instance {profile.name}: {exc}") from exc

    return _result(
        layout,
        profile.name,
        version.id,
        version.entry,
        key,
        "full",
    )
