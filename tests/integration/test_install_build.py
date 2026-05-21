from __future__ import annotations

import re
from pathlib import Path

import pytest

from core.build import _MOD_LIST_PATTERN, build_runtime
from core.mods import add_mod_from_zip
from core.profiles import add_mod_to_profile, set_profile_version
from core.versions import install_from_dir, install_from_file, list_installed


class TestInstallFromFile:
    def test_extracts_zip_and_writes_manifest(
        self, root: Path, make_version_zip
    ) -> None:
        zip_path = make_version_zip("dol-0.5.3.zip")
        version_id = install_from_file(
            root, zip_path, version_id=None, channel="vanilla"
        )
        assert version_id.startswith("vanilla-")
        manifest = root / "versions" / version_id / ".manifest.toml"
        assert manifest.exists()
        assert (root / "versions" / version_id / "index.html").exists()

        listed = list_installed(root)
        assert len(listed) == 1
        assert listed[0].id == version_id
        assert listed[0].entry == "index.html"

    def test_install_from_dir_preserves_files(
        self, root: Path, make_version_dir
    ) -> None:
        src = make_version_dir()
        version_id = install_from_dir(root, src, version_id="vanilla-test", channel="vanilla")
        assert version_id == "vanilla-test"
        assert (root / "versions" / "vanilla-test" / "index.html").exists()
        assert (
            root / "versions" / "vanilla-test" / "game" / "asset.txt"
        ).read_text() == "payload"


class TestBuildRuntime:
    def test_builds_merged_dir_without_mods(
        self, root: Path, make_version_dir
    ) -> None:
        src = make_version_dir()
        install_from_dir(root, src, version_id="v1", channel="vanilla")
        set_profile_version(root, "default", "v1")

        result = build_runtime(root, "default")
        merged = root / "runtime" / "default" / "merged"
        assert result.output_dir == merged
        assert (merged / "index.html").exists()
        assert (merged / "game" / "asset.txt").read_text() == "payload"
        # No mods → no injection
        assert "modDataValueZipList" not in (merged / "index.html").read_text()

    def test_builds_merged_dir_with_mod_injection(
        self, root: Path, make_version_dir, make_mod_zip
    ) -> None:
        src = make_version_dir()
        install_from_dir(root, src, version_id="v1", channel="vanilla")
        set_profile_version(root, "default", "v1")

        mod_zip = make_mod_zip("alpha.mod.zip", boot={"name": "Alpha", "version": "1"})
        mod_id = add_mod_from_zip(root, str(mod_zip))
        add_mod_to_profile(root, "default", mod_id)

        build_runtime(root, "default")
        injected = (root / "runtime" / "default" / "merged" / "index.html").read_text()
        match = re.search(_MOD_LIST_PATTERN, injected, re.DOTALL)
        assert match is not None
        # Single entry expected
        assert injected.count("modDataValueZipList") == 1

    def test_build_fails_when_mod_zip_missing(
        self, root: Path, make_version_dir, make_mod_zip
    ) -> None:
        from core.models import DolCtlError

        src = make_version_dir()
        install_from_dir(root, src, version_id="v1", channel="vanilla")
        set_profile_version(root, "default", "v1")

        mod_zip = make_mod_zip("gone.mod.zip", boot={"name": "Gone", "version": "1"})
        mod_id = add_mod_from_zip(root, str(mod_zip))
        add_mod_to_profile(root, "default", mod_id)
        # Simulate manual deletion
        (root / "mods" / mod_id / f"{mod_id}.mod.zip").unlink()

        with pytest.raises(DolCtlError):
            build_runtime(root, "default")
