from __future__ import annotations

import base64
import hashlib
import re
from pathlib import Path
import json
import os
import shutil

from .profiles import get_profile
from infra.fs import ensure_dir, safe_rmtree, now_iso
from infra.log import get_logger
from infra.toml import read_toml
from core.models import BuildResult, DolCtlError, version_manifest_from_dict

logger = get_logger(__name__)

IGNORED_FILES = {".manifest.toml"}

# Regex used by Lyra / DoL ModLoader to locate the mod list in the HTML.
_MOD_LIST_PATTERN = r"window\.modDataValueZipList\s*=\s*(\[.*?\]);"

_BUILD_META_SCHEMA = 2


def _copy_tree(src: Path, dest: Path) -> None:
    for root_dir, _dirs, files in os.walk(src):
        root_path = Path(root_dir)
        rel_root = root_path.relative_to(src)
        for filename in files:
            if filename in IGNORED_FILES:
                continue
            src_file = root_path / filename
            rel_path = rel_root / filename if str(rel_root) != "." else Path(filename)
            dest_file = dest / rel_path
            dest_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_file, dest_file)


def _find_entry_html(merged_dir: Path, base_dir: Path) -> Path:
    """Resolve the entry HTML file inside *merged_dir*.

    Uses the version manifest ``entry`` field when available, otherwise
    falls back to glob-matching ``*.html`` at the root level.
    """
    manifest_path = base_dir / ".manifest.toml"
    if manifest_path.exists():
        manifest = version_manifest_from_dict(read_toml(manifest_path))
        entry_name = manifest.entry
    else:
        entry_name = "index.html"

    html_path = merged_dir / entry_name
    if html_path.exists():
        return html_path

    # Fallback: first .html at root
    html_files = sorted(merged_dir.glob("*.html"))
    if html_files:
        return html_files[0]

    raise DolCtlError("No HTML entry file found in the built version.")


# ---------------------------------------------------------------------------
# ModLoader injection (base64-embed approach, matching Lyra)
# ---------------------------------------------------------------------------


def _read_mod_as_base64(zip_path: Path) -> str:
    """Read a ``.mod.zip`` file and return its content as a base64 string."""
    return base64.b64encode(zip_path.read_bytes()).decode("ascii")


def _inject_mods_into_html(html_path: Path, mod_zips: list[Path]) -> None:
    """Inject mod zips into the HTML's ``window.modDataValueZipList``.

    Follows Lyra's ``ModInjector.add_mods`` strategy: each mod zip is
    base64-encoded and appended to the JavaScript array
    ``window.modDataValueZipList`` that the DoL ModLoader reads at startup.

    If the HTML already contains the array (ModLoader / Lyra builds), the
    new entries are appended. If not (vanilla builds), the array is created
    inside a new ``<script>`` block before ``</head>``.
    """
    content = html_path.read_text(encoding="utf-8")

    new_entries: list[str] = []
    for zp in mod_zips:
        logger.info("  Embedding mod: %s", zp.name)
        new_entries.append(_read_mod_as_base64(zp))

    match = re.search(_MOD_LIST_PATTERN, content, re.DOTALL)

    if match:
        existing_list: list[str] = json.loads(match.group(1))
        existing_list.extend(new_entries)
        replacement = f"window.modDataValueZipList = {json.dumps(existing_list)};"
        content = content[: match.start()] + replacement + content[match.end():]
    else:
        script_block = (
            '<script type="text/javascript">'
            f"window.modDataValueZipList = {json.dumps(new_entries)};"
            "</script>"
        )
        if "</head>" in content:
            content = content.replace("</head>", script_block + "\n</head>", 1)
        else:
            content = script_block + "\n" + content

    html_path.write_text(content, encoding="utf-8")
    logger.info("  Injected %d mod(s) into %s", len(new_entries), html_path.name)


# ---------------------------------------------------------------------------
# Incremental build bookkeeping
# ---------------------------------------------------------------------------


def _mod_fingerprint(
    zip_path: Path, previous: dict[str, object] | None
) -> dict[str, object]:
    """Return ``{id, mtime_ns, size, sha256}`` for *zip_path*.

    Reuses ``previous['sha256']`` when ``mtime_ns`` and ``size`` are
    unchanged so the typical incremental rebuild touches no mod bytes.
    """
    stat = zip_path.stat()
    if (
        previous is not None
        and previous.get("mtime_ns") == stat.st_mtime_ns
        and previous.get("size") == stat.st_size
        and previous.get("sha256")
    ):
        sha256 = str(previous["sha256"])
    else:
        hasher = hashlib.sha256()
        with zip_path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                hasher.update(chunk)
        sha256 = hasher.hexdigest()
    return {
        "id": zip_path.parent.name,
        "mtime_ns": stat.st_mtime_ns,
        "size": stat.st_size,
        "sha256": sha256,
    }


def _load_meta(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _mod_order_matches(prev_entries: list[dict], current: list[dict]) -> bool:
    if len(prev_entries) != len(current):
        return False
    for a, b in zip(prev_entries, current):
        if a.get("id") != b.get("id"):
            return False
        if a.get("sha256") != b.get("sha256"):
            return False
    return True


def build_runtime(
    root: Path, profile_name: str, clean: bool = False
) -> BuildResult:
    """Build the runtime directory for *profile_name*.

    Skips work when the existing ``runtime/<profile>/merged`` already
    matches the requested version and mod set. Pass ``clean=True`` to force
    a full rebuild.
    """
    profile = get_profile(root, profile_name)
    if not profile.version_id:
        raise DolCtlError(f"Profile has no version set: {profile_name}")

    base_dir = root / "versions" / profile.version_id
    if not base_dir.exists():
        raise DolCtlError(f"Version not found: {profile.version_id}")

    runtime_dir = root / "runtime" / profile_name
    merged_dir = runtime_dir / "merged"
    build_meta_path = runtime_dir / "build_meta.json"
    previous_meta = None if clean else _load_meta(build_meta_path)

    # Compute the desired state ----------------------------------------------
    mod_zip_paths: list[Path] = []
    previous_mods_by_id: dict[str, dict] = {}
    if previous_meta and isinstance(previous_meta.get("mod_order"), list):
        for item in previous_meta["mod_order"]:
            if isinstance(item, dict) and "id" in item:
                previous_mods_by_id[item["id"]] = item

    for mod_id in profile.mod_order:
        src_zip = root / "mods" / mod_id / f"{mod_id}.mod.zip"
        if not src_zip.exists():
            raise DolCtlError(
                f"Mod zip not found for '{mod_id}': {src_zip}\n"
                "The mod may have been deleted. Remove it from the profile first."
            )
        mod_zip_paths.append(src_zip)

    current_mod_entries = [
        _mod_fingerprint(p, previous_mods_by_id.get(p.parent.name))
        for p in mod_zip_paths
    ]

    # Decide which sections of the build can be skipped ----------------------
    need_copy = (
        clean
        or previous_meta is None
        or previous_meta.get("base_version_id") != profile.version_id
        or not merged_dir.exists()
    )
    need_inject = need_copy or not _mod_order_matches(
        previous_meta.get("mod_order", []) if previous_meta else [],
        current_mod_entries,
    )

    logger.info(
        "Building profile %s from version %s (%d mod(s)) — %s",
        profile_name,
        profile.version_id,
        len(profile.mod_order),
        "full" if need_copy else ("inject-only" if need_inject else "cache hit"),
    )

    if need_copy:
        safe_rmtree(merged_dir)
        ensure_dir(merged_dir)
        _copy_tree(base_dir, merged_dir)
    elif need_inject:
        # Refresh the entry HTML from the pristine version so subsequent
        # injection works from a clean base, regardless of how the previous
        # injection mutated the file.
        entry_html_in_base = _find_entry_html(base_dir, base_dir)
        rel_entry = entry_html_in_base.relative_to(base_dir)
        target = merged_dir / rel_entry
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(entry_html_in_base, target)

    if need_inject and mod_zip_paths:
        html_path = _find_entry_html(merged_dir, base_dir)
        _inject_mods_into_html(html_path, mod_zip_paths)

    # Write build meta -------------------------------------------------------
    build_meta = {
        "schema_version": _BUILD_META_SCHEMA,
        "base_version_id": profile.version_id,
        "mod_order": current_mod_entries,
        "built_at": now_iso(),
    }
    runtime_dir.mkdir(parents=True, exist_ok=True)
    build_meta_path.write_text(json.dumps(build_meta, indent=2), encoding="utf-8")

    return BuildResult(
        profile=profile_name,
        version_id=profile.version_id,
        output_dir=merged_dir,
        build_meta_path=build_meta_path,
    )
