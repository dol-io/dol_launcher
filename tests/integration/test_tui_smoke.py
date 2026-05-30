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


@pytest.mark.asyncio
async def test_tabs_populate_on_initial_mount(
    root: Path, make_version_dir, make_mod_zip
) -> None:
    """Regression: tabs must populate from disk on first mount, not stay empty.

    Previously every tab guarded refresh_from_disk with ``if not self.is_mounted``,
    but is_mounted is False during on_mount, so the guard silently skipped
    the initial population and every tab rendered blank.
    """
    from dolctl.tui.screens.channels import ChannelsTab
    from dolctl.tui.screens.home import HomeTab
    from dolctl.tui.screens.mods import ModsTab
    from dolctl.tui.screens.profiles import ProfilesTab
    from dolctl.tui.screens.versions import VersionsTab
    from textual.widgets import DataTable, ListView, Static

    add_channel(root, "vanilla", preset="dol-vanilla")
    src = make_version_dir()
    install_from_dir(root, src, version_id="v1", channel="vanilla")
    mz = make_mod_zip("a.mod.zip", boot={"name": "A", "version": "1"})
    add_mod_from_zip(root, str(mz))
    set_profile_version(root, "default", "v1")
    add_mod_to_profile(root, "default", "a")

    app = DolctlApp(root)
    async with app.run_test(size=(150, 50)) as pilot:
        await pilot.pause()

        # Home tab cards have content (not blank)
        home_card = app.query_one(HomeTab).query_one("#card-root", Static)
        assert "ROOT" in str(home_card.render())

        # Channels tab populated
        app.action_switch_tab("channels")
        await pilot.pause()
        ct = app.query_one(ChannelsTab)
        assert ct.query_one("#channels-table", DataTable).row_count == 1
        assert len(ct.query_one("#presets-list", ListView).children) > 0

        # Versions tab populated
        app.action_switch_tab("versions")
        await pilot.pause()
        vt = app.query_one(VersionsTab)
        assert vt.query_one("#installed-table", DataTable).row_count == 1

        # Mods tab populated
        app.action_switch_tab("mods")
        await pilot.pause()
        assert app.query_one(ModsTab).query_one("#mods-table", DataTable).row_count == 1

        # Profiles tab populated
        app.action_switch_tab("profiles")
        await pilot.pause()
        pt = app.query_one(ProfilesTab)
        assert len(pt.query_one("#profile-list", ListView).children) == 1
        assert pt.query_one("#profile-mods-table", DataTable).row_count == 1


@pytest.mark.asyncio
async def test_repeated_data_bumps_dont_raise_duplicate_ids(
    root: Path, make_version_dir, make_mod_zip
) -> None:
    """Regression: ListView clear() is async; back-to-back refreshes used to
    raise DuplicateIds because the prior items hadn't been unmounted yet
    when new ones (with the same id="preset-..."/"profile-...") were added."""
    add_channel(root, "vanilla", preset="dol-vanilla")
    src = make_version_dir()
    install_from_dir(root, src, version_id="v1", channel="vanilla")
    mz = make_mod_zip("a.mod.zip", boot={"name": "A", "version": "1"})
    add_mod_from_zip(root, str(mz))

    app = DolctlApp(root)
    async with app.run_test(size=(150, 50)) as pilot:
        await pilot.pause()
        app.action_switch_tab("channels")
        await pilot.pause()
        for _ in range(3):
            app.bump_data()
            await pilot.pause()
        app.action_switch_tab("profiles")
        await pilot.pause()
        for _ in range(3):
            app.bump_data()
            await pilot.pause()


@pytest.mark.asyncio
async def test_remote_refresh_surfaces_http_errors(
    root: Path, monkeypatch
) -> None:
    """Regression: when ``list_remote_versions`` raises a non-DolCtlError
    (e.g. httpx.HTTPStatusError from a 404), the worker used to silently
    swallow it — users saw the TUI either hang on "fetching…" or crash.

    The worker now catches Exception so the error reaches the status bar.
    """
    import httpx

    from dolctl.tui.screens.versions import VersionsTab
    from textual.widgets import Select, Static

    add_channel(root, "vanilla", preset="dol-vanilla")

    # Stub list_remote_versions to raise the same shape of error httpx
    # produces against a 404 release endpoint.
    def boom(*_args, **_kwargs):
        request = httpx.Request("GET", "https://api.github.com/repos/x/y/releases")
        raise httpx.HTTPStatusError(
            "404 Not Found",
            request=request,
            response=httpx.Response(404, request=request),
        )

    monkeypatch.setattr("dolctl.tui.screens.versions.list_remote_versions", boom)

    app = DolctlApp(root)
    async with app.run_test(size=(150, 50)) as pilot:
        await pilot.pause()
        app.action_switch_tab("versions")
        await pilot.pause()
        vt = app.query_one(VersionsTab)
        vt.query_one("#channel-select", Select).value = "vanilla"
        await pilot.pause()
        vt._refresh_remote()
        # Worker runs in a thread; pump the UI a few times for the
        # call_from_thread status update to land.
        for _ in range(20):
            await pilot.pause()
        status = str(app.query_one("#status", Static).render())
        assert "error" in status.lower() and "404" in status, (
            f"expected HTTP error to reach status bar, got: {status!r}"
        )


@pytest.mark.asyncio
async def test_profile_version_select_never_writes_null_sentinel(
    root: Path, make_version_dir
) -> None:
    """Regression: ProfilesTab.refresh_from_disk does set_options() then
    select.value = profile.version_id back-to-back. Both post a
    Select.Changed event. The first event (value=Select.NULL from the
    reset) used to slip past the ``event.select.is_blank()`` guard
    because by the time the handler ran the live widget value had
    already advanced to the real version_id, so ``is_blank()`` (which
    reads current state, not the event's captured value) returned False.
    ``str(event.value)`` was then ``"Select.NULL"``, which we passed to
    ``set_profile_version`` — that raised ``Version not found:
    Select.NULL`` and the status bar showed the error on every refresh.

    Guard now compares ``event.value`` itself against the sentinel.
    """
    from textual.widgets import Static

    src = make_version_dir()
    install_from_dir(root, src, version_id="v1", channel="vanilla")
    set_profile_version(root, "default", "v1")

    app = DolctlApp(root)
    async with app.run_test(size=(150, 50)) as pilot:
        await pilot.pause()
        app.action_switch_tab("profiles")
        for _ in range(8):
            await pilot.pause()
        # Trigger a refresh cycle: set_options + value reassignment race
        app.bump_data()
        for _ in range(8):
            await pilot.pause()
        status = str(app.query_one("#status", Static).render())
        assert "Select.NULL" not in status, (
            f"refresh leaked the NoSelection sentinel to set_profile_version: {status!r}"
        )


@pytest.mark.asyncio
async def test_profiles_select_does_not_loop(
    root: Path, make_version_dir
) -> None:
    """Regression: ProfilesTab.refresh_from_disk re-assigns the version Select,
    which fires Select.Changed, which used to call set_profile_version +
    notify_data_changed → bump_data → refresh again → infinite loop.

    The handler now compares against current disk state to skip redundant
    writes; data_version must stay stable after settling.
    """
    src = make_version_dir()
    install_from_dir(root, src, version_id="v1", channel="vanilla")
    set_profile_version(root, "default", "v1")

    app = DolctlApp(root)
    async with app.run_test(size=(150, 50)) as pilot:
        await pilot.pause()
        app.action_switch_tab("profiles")
        for _ in range(8):
            await pilot.pause()
        baseline = app.data_version
        for _ in range(8):
            await pilot.pause()
        assert app.data_version == baseline, (
            f"data_version drifted from {baseline} to {app.data_version} "
            "— refresh→Select.Changed→write→bump_data loop is back"
        )


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
