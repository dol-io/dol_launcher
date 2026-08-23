from __future__ import annotations

import pytest
from textual.widgets import DataTable, ListView, TabbedContent

from core.launcher import Launcher
from dolctl.tui.app import DolctlApp
from dolctl.tui.screens.instances import InstancesTab
from dolctl.tui.screens.mods import ModsTab
from dolctl.tui.screens.sources import SourcesTab
from dolctl.tui.screens.system import SystemTab
from dolctl.tui.screens.versions import VersionsTab


@pytest.mark.asyncio
async def test_app_mounts_and_cycles_all_five_tabs(
    launcher: Launcher, make_version_dir, make_mod_zip
) -> None:
    launcher.install_version_directory(make_version_dir(), version_id="game")
    launcher.configure_instance("default", version_id="game")
    mod_id = launcher.install_mod(str(make_mod_zip()))
    launcher.enable_mod("default", mod_id)

    app = DolctlApp(launcher)
    async with app.run_test(size=(150, 50)) as pilot:
        await pilot.pause()
        tabs = app.query_one("#tabs", TabbedContent)
        for tab in ("instances", "versions", "mods", "sources", "system"):
            app.action_switch_tab(tab)
            await pilot.pause()
            assert tabs.active == tab

        assert (
            len(
                app.query_one(InstancesTab)
                .query_one("#instance-list", ListView)
                .children
            )
            == 1
        )
        assert (
            app.query_one(VersionsTab).query_one("#installed", DataTable).row_count == 1
        )
        assert app.query_one(ModsTab).query_one("#mods", DataTable).row_count == 1
        assert app.query_one(SourcesTab).query_one("#sources", DataTable).row_count == 1


@pytest.mark.asyncio
async def test_repeated_data_notifications_are_safe(launcher: Launcher) -> None:
    app = DolctlApp(launcher)
    async with app.run_test(size=(150, 50)) as pilot:
        await pilot.pause()
        for _ in range(3):
            app.notify_data_changed()
            await pilot.pause()


@pytest.mark.asyncio
async def test_system_tab_renders_diagnostics_for_corrupt_config(
    launcher: Launcher,
) -> None:
    (launcher.root / ".dolctl" / "config.toml").write_text("[", encoding="utf-8")
    app = DolctlApp(launcher)
    async with app.run_test(size=(150, 50)) as pilot:
        app.action_switch_tab("system")
        await pilot.pause()
        rendered = str(app.query_one(SystemTab).query_one("#checks").render())
        assert "Cannot read config" in rendered
