from __future__ import annotations

import re
from pathlib import Path
import json
import os
import shutil

from .profiles import get_profile
from infra.fs import ensure_dir, safe_rmtree, now_iso
from core.models import BuildResult, DolCtlError


IGNORED_FILES = {".manifest.toml"}

# Marker wrapped around injected script so it can be detected / replaced cleanly
_INJECT_MARKER_START = "<!-- dolctl-mods-inject-start -->"
_INJECT_MARKER_END = "<!-- dolctl-mods-inject-end -->"


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


def _build_inject_script(mod_paths: list[str]) -> str:
    """Build the JavaScript snippet that registers mod zips with DoL ModLoader."""
    paths_js = ", ".join(f'"{ p}"' for p in mod_paths)
    return (
        f"{_INJECT_MARKER_START}\n"
        '<script type="text/javascript">\n'
        "(function () {\n"
        "  window.modList = window.modList || [];\n"
        + "".join(f'  window.modList.push("{p}");\n' for p in mod_paths)
        + "}());\n"
        "</script>\n"
        f"{_INJECT_MARKER_END}"
    )


def _inject_mods_into_html(html_path: Path, mod_zip_names: list[str]) -> None:
    """
    Inject a window.modList bootstrap script into index.html.

    The script is inserted just before </head>. If a previous injection marker
    is present (from a prior build), it is replaced atomically.

    mod_zip_names: relative paths like ["mods/modA.mod.zip", "mods/modB.mod.zip"]
    """
    content = html_path.read_text(encoding="utf-8")

    # Remove any previous injection
    content = re.sub(
        rf"{re.escape(_INJECT_MARKER_START)}.*?{re.escape(_INJECT_MARKER_END)}",
        "",
        content,
        flags=re.DOTALL,
    )

    if not mod_zip_names:
        html_path.write_text(content, encoding="utf-8")
        return

    inject_block = _build_inject_script(mod_zip_names)

    # Try to inject just before </head>
    if "</head>" in content:
        content = content.replace("</head>", inject_block + "\n</head>", 1)
    else:
        # Fallback: prepend to file
        content = inject_block + "\n" + content

    html_path.write_text(content, encoding="utf-8")


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

    # 2. Copy mod zips and inject into index.html
    mod_zip_names: list[str] = []
    if profile.mod_order:
        mods_dest = merged_dir / "mods"
        ensure_dir(mods_dest)
        for mod_id in profile.mod_order:
            src_zip = root / "mods" / mod_id / f"{mod_id}.mod.zip"
            if not src_zip.exists():
                raise DolCtlError(
                    f"Mod zip not found for '{mod_id}': {src_zip}\n"
                    "The mod may have been deleted. Remove it from the profile first."
                )
            dest_zip = mods_dest / f"{mod_id}.mod.zip"
            shutil.copy2(src_zip, dest_zip)
            # Relative path as the browser will request it from the game root
            mod_zip_names.append(f"mods/{mod_id}.mod.zip")

    # 3. Inject mod list into index.html
    html_path = merged_dir / "index.html"
    if not html_path.exists():
        # Try any .html file at root
        html_files = list(merged_dir.glob("*.html"))
        if html_files:
            html_path = html_files[0]
        else:
            raise DolCtlError("No index.html found in the built version.")

    _inject_mods_into_html(html_path, mod_zip_names)

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
