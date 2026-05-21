"""TUI smoke tests.

We don't try to exercise the full keyboard flow — Textual's snapshot
testing is heavy and the value/effort ratio is low. The goal is just to
prove that the App composes, every tab mounts without raising, and the
refresh-from-disk path doesn't blow up on a populated root.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from core.channels import add_channel
from core.mods import add_mod_from_zip
from core.profiles import add_mod_to_profile, set_profile_version
from core.versions import install_from_dir
from dolctl.tui.app import DolctlApp
from dolctl.tui.screens.doctor import _run_checks


@pytest.mark.asyncio
async def test_app_cycles_all_tabs(root: Path, make_version_dir, make_mod_zip) -> None:
    add_channel(root, "vanilla", preset="dol-vanilla")
    src = make_version_dir()
    install_from_dir(root, src, version_id="v1", channel="vanilla")
    mod_zip = make_mod_zip("a.mod.zip", boot={"name": "A", "version": "1"})
    add_mod_from_zip(root, str(mod_zip))
    set_profile_version(root, "default", "v1")
    add_mod_to_profile(root, "default", "a")

    app = DolctlApp(root)
    async with app.run_test() as pilot:
        await pilot.pause()
        for tab in ("home", "channels", "versions", "mods", "profiles", "run", "doctor"):
            app.action_switch_tab(tab)
            await pilot.pause()


@pytest.mark.asyncio
async def test_app_handles_empty_root(root: Path) -> None:
    """Empty root (no channels, no mods, no versions) must not crash."""
    app = DolctlApp(root)
    async with app.run_test() as pilot:
        await pilot.pause()
        for tab in ("home", "channels", "versions", "mods", "profiles", "run", "doctor"):
            app.action_switch_tab(tab)
            await pilot.pause()


class TestDoctorChecks:
    def test_clean_root_only_warns_about_channels(self, root: Path) -> None:
        results = _run_checks(root)
        # Everything else should be ok; only the "no channels configured" check fails.
        failures = [c for c in results if not c.ok]
        assert len(failures) == 1
        assert "channel" in failures[0].note.lower()

    def test_profile_with_missing_version_flagged(
        self, root: Path, make_version_dir
    ) -> None:
        # Bind default profile to a version, then remove that version's dir
        src = make_version_dir()
        install_from_dir(root, src, version_id="ghost", channel="vanilla")
        set_profile_version(root, "default", "ghost")
        import shutil

        shutil.rmtree(root / "versions" / "ghost")

        results = _run_checks(root)
        missing_msgs = [c.note for c in results if not c.ok and "ghost" in c.note]
        assert any("references missing" in m for m in missing_msgs)
