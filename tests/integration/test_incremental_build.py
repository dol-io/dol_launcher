from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from core.build import build_runtime
from core.mods import add_mod_from_zip
from core.profiles import add_mod_to_profile, remove_mod_from_profile, set_profile_version
from core.versions import install_from_dir


def _read_meta(root: Path, profile: str = "default") -> dict:
    return json.loads(
        (root / "runtime" / profile / "build_meta.json").read_text(encoding="utf-8")
    )


def _setup_profile_with_mod(root: Path, make_version_dir, make_mod_zip) -> Path:
    src = make_version_dir()
    install_from_dir(root, src, version_id="v1", channel="vanilla")
    set_profile_version(root, "default", "v1")
    mod_zip = make_mod_zip("alpha.mod.zip", boot={"name": "Alpha", "version": "1"})
    add_mod_from_zip(root, str(mod_zip))
    add_mod_to_profile(root, "default", "alpha")
    return mod_zip


class TestIncrementalBuild:
    def test_first_build_is_full(self, root: Path, make_version_dir, make_mod_zip) -> None:
        _setup_profile_with_mod(root, make_version_dir, make_mod_zip)
        build_runtime(root, "default")
        meta = _read_meta(root)
        assert meta["schema_version"] == 2
        assert meta["base_version_id"] == "v1"
        assert [m["id"] for m in meta["mod_order"]] == ["alpha"]
        assert all("sha256" in m for m in meta["mod_order"])

    def test_second_build_is_cache_hit(
        self, root: Path, make_version_dir, make_mod_zip
    ) -> None:
        _setup_profile_with_mod(root, make_version_dir, make_mod_zip)
        build_runtime(root, "default")
        first_meta = _read_meta(root)

        # Touch a merged asset to a known mtime; if we re-copy the file
        # over it the mtime will jump back to the source's mtime.
        merged_asset = root / "runtime" / "default" / "merged" / "game" / "asset.txt"
        marker = 1_000_000_000  # 2001
        import os
        os.utime(merged_asset, (marker, marker))

        build_runtime(root, "default")
        assert merged_asset.stat().st_mtime == marker  # untouched
        assert _read_meta(root)["base_version_id"] == first_meta["base_version_id"]

    def test_mod_order_change_triggers_inject_only(
        self, root: Path, make_version_dir, make_mod_zip
    ) -> None:
        _setup_profile_with_mod(root, make_version_dir, make_mod_zip)
        # Add a second mod
        mod_b = make_mod_zip("beta.mod.zip", boot={"name": "Beta", "version": "1"})
        add_mod_from_zip(root, str(mod_b))
        add_mod_to_profile(root, "default", "beta")

        build_runtime(root, "default")
        meta_after_b = _read_meta(root)

        merged_asset = root / "runtime" / "default" / "merged" / "game" / "asset.txt"
        marker = 1_500_000_000
        import os
        os.utime(merged_asset, (marker, marker))

        remove_mod_from_profile(root, "default", "beta")
        build_runtime(root, "default")
        # Inject-only: non-HTML assets keep their previously-set mtime
        assert merged_asset.stat().st_mtime == marker

        meta_after_remove = _read_meta(root)
        assert [m["id"] for m in meta_after_remove["mod_order"]] == ["alpha"]
        # mod_order content shape changed
        assert meta_after_remove != meta_after_b

    def test_version_change_triggers_full_rebuild(
        self, root: Path, make_version_dir, make_mod_zip
    ) -> None:
        _setup_profile_with_mod(root, make_version_dir, make_mod_zip)
        build_runtime(root, "default")

        # Install a second version under a different id, point profile at it
        src2 = make_version_dir()
        install_from_dir(root, src2, version_id="v2", channel="vanilla", force=False)
        set_profile_version(root, "default", "v2")

        merged_asset = root / "runtime" / "default" / "merged" / "game" / "asset.txt"
        marker = 1_700_000_000
        import os
        os.utime(merged_asset, (marker, marker))

        build_runtime(root, "default")
        # Full rebuild copied the file fresh, mtime should NOT be the marker
        assert merged_asset.stat().st_mtime != marker
        assert _read_meta(root)["base_version_id"] == "v2"

    def test_clean_flag_forces_full_rebuild(
        self, root: Path, make_version_dir, make_mod_zip
    ) -> None:
        _setup_profile_with_mod(root, make_version_dir, make_mod_zip)
        build_runtime(root, "default")
        merged_asset = root / "runtime" / "default" / "merged" / "game" / "asset.txt"
        marker = 1_800_000_000
        import os
        os.utime(merged_asset, (marker, marker))

        build_runtime(root, "default", clean=True)
        # Clean rebuild: file recopied, mtime should not be the marker
        assert merged_asset.stat().st_mtime != marker

    def test_mod_zip_replacement_detected(
        self, root: Path, make_version_dir, make_mod_zip
    ) -> None:
        mod_zip = _setup_profile_with_mod(root, make_version_dir, make_mod_zip)
        build_runtime(root, "default")
        first_meta = _read_meta(root)

        # Replace the mod's bytes with new content (more bytes), keeping the id
        cached_mod = root / "mods" / "alpha" / "alpha.mod.zip"
        cached_mod.write_bytes(b"PK\x05\x06" + b"\x00" * 22)  # empty zip EOCD
        # Bump mtime to make sure st_mtime_ns differs
        import os
        os.utime(cached_mod, (time.time() + 100, time.time() + 100))

        build_runtime(root, "default")
        new_meta = _read_meta(root)
        # sha256 entry must have changed
        first_sha = first_meta["mod_order"][0]["sha256"]
        new_sha = new_meta["mod_order"][0]["sha256"]
        assert first_sha != new_sha
