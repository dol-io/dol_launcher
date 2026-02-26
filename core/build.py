from __future__ import annotations

import base64
import re
from pathlib import Path
import json
import logging
import os
import shutil

from .profiles import get_profile
from infra.fs import ensure_dir, safe_rmtree, now_iso
from infra.toml import read_toml
from core.models import BuildResult, DolCtlError, version_manifest_from_dict

logger = logging.getLogger(__name__)

IGNORED_FILES = {".manifest.toml"}

# Regex used by Lyra / DoL ModLoader to locate the mod list in the HTML.
_MOD_LIST_PATTERN = r"window\.modDataValueZipList\s*=\s*(\[.*?\]);"


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

    This follows the same strategy as Lyra's ``ModInjector.add_mods``:
    each mod zip is base64-encoded and appended to the JavaScript array
    ``window.modDataValueZipList`` that the DoL ModLoader reads at startup.

    If the HTML already contains the array (ModLoader / Lyra builds), the
    new entries are appended.  If not (vanilla builds), the array is created
    inside a new ``<script>`` block before ``</head>``.
    """
    content = html_path.read_text(encoding="utf-8")

    # Base64-encode each mod zip
    new_entries: list[str] = []
    for zp in mod_zips:
        logger.info("  Embedding mod: %s", zp.name)
        new_entries.append(_read_mod_as_base64(zp))

    match = re.search(_MOD_LIST_PATTERN, content, re.DOTALL)

    if match:
        # HTML already has modDataValueZipList – parse and extend it.
        existing_list: list[str] = json.loads(match.group(1))
        existing_list.extend(new_entries)
        replacement = f"window.modDataValueZipList = {json.dumps(existing_list)};"
        content = content[: match.start()] + replacement + content[match.end() :]
    else:
        # No ModLoader array present – create one.
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


def build_runtime(root: Path, profile_name: str, clean: bool = True) -> BuildResult:
    profile = get_profile(root, profile_name)
    if not profile.version_id:
        raise DolCtlError(f"Profile has no version set: {profile_name}")

    base_dir = root / "versions" / profile.version_id
    if not base_dir.exists():
        raise DolCtlError(f"Version not found: {profile.version_id}")

    runtime_dir = root / "runtime" / profile_name
    merged_dir = runtime_dir / "merged"

    if clean:
        safe_rmtree(merged_dir)
    ensure_dir(merged_dir)

    # 1. Copy base version files
    _copy_tree(base_dir, merged_dir)

    # 2. Collect mod zips and inject into HTML (base64-embed, Lyra style)
    mod_zip_paths: list[Path] = []
    if profile.mod_order:
        for mod_id in profile.mod_order:
            src_zip = root / "mods" / mod_id / f"{mod_id}.mod.zip"
            if not src_zip.exists():
                raise DolCtlError(
                    f"Mod zip not found for '{mod_id}': {src_zip}\n"
                    "The mod may have been deleted. Remove it from the profile first."
                )
            mod_zip_paths.append(src_zip)

    # 3. Locate entry HTML and inject mods
    html_path = _find_entry_html(merged_dir, base_dir)

    if mod_zip_paths:
        _inject_mods_into_html(html_path, mod_zip_paths)

    # 4. Write build meta
    build_meta = {
        "base_version_id": profile.version_id,
        "mod_order": profile.mod_order,
        "built_at": now_iso(),
    }
    runtime_dir.mkdir(parents=True, exist_ok=True)
    build_meta_path = runtime_dir / "build_meta.json"
    build_meta_path.write_text(json.dumps(build_meta, indent=2), encoding="utf-8")

    return BuildResult(
        profile=profile_name,
        version_id=profile.version_id,
        output_dir=merged_dir,
        build_meta_path=build_meta_path,
    )
