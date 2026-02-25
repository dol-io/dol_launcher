from __future__ import annotations

from pathlib import Path
import json
import os
import shutil

from .core_profiles import get_profile
from .infra_fs import ensure_dir, safe_rmtree, now_iso
from .models import BuildResult, DolCtlError


IGNORED_FILES = {".manifest.toml"}


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

    _copy_tree(base_dir, merged_dir)

    build_meta = {
        "base_version_id": profile.version_id,
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
