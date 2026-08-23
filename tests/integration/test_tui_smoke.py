from __future__ import annotations

from pathlib import Path
import re

import pytest
from rich.color import ColorType
from textual.widgets import Button, DataTable, Input, OptionList, Static

from core.launcher import Launcher
from dolctl.tui.app import DolctlApp
from dolctl.tui.modals import ModManagerModal
from dolctl.tui.screens.instances import InstancesTab
from dolctl.tui.screens.library import LibraryScreen
from dolctl.tui.screens.mods import ModsTab
from dolctl.tui.screens.sources import SourcesTab
from dolctl.tui.screens.system import SystemTab
from dolctl.tui.screens.versions import VersionsTab
from dolctl.tui.theme import ANSI_16_COLOURS, TERMINAL_CSS, TERMINAL_THEME


@pytest.mark.asyncio
async def test_app_mounts_and_navigates_the_three_workspaces(
    launcher: Launcher, make_version_dir, make_mod_zip
) -> None:
    launcher.install_version_directory(make_version_dir(), version_id="game")
    launcher.configure_instance("default", version_id="game")
    mod_id = launcher.install_mod(str(make_mod_zip()))
    launcher.enable_mod("default", mod_id)

    app = DolctlApp(launcher)
    async with app.run_test(size=(150, 50)) as pilot:
        await pilot.pause()
        assert app.current_theme.name == "dolctl-ansi16"
        assert app.query_one("#play-page").has_class("-current")
        assert (
            app.query_one(InstancesTab)
            .query_one("#instance-list", OptionList)
            .option_count
            == 1
        )
        assert (
            app.query_one(InstancesTab).query_one("#enabled-mods", DataTable).row_count
            == 1
        )
        enabled_mods = app.query_one("#enabled-mods", DataTable)
        assert enabled_mods.max_scroll_y == 0

        await pilot.press("2")
        assert app.query_one("#library-page").has_class("-current")
        library = app.query_one(LibraryScreen)
        for section in ("versions", "mods", "sources"):
            library.show_section(section)
            await pilot.pause()
            assert app.query_one(f"#{section}-section").has_class("-current")
            assert app.query_one(f"#library-{section}", Button).has_class("-current")

        assert (
            app.query_one(VersionsTab).query_one("#installed", DataTable).row_count == 1
        )
        assert app.query_one(ModsTab).query_one("#mods", DataTable).row_count == 1
        assert app.query_one(SourcesTab).query_one("#sources", DataTable).row_count == 1

        await pilot.click("#nav-system")
        assert app.query_one("#system-page").has_class("-current")


@pytest.mark.asyncio
async def test_highlight_selects_instance_without_mutating_active_state(
    launcher: Launcher, make_version_dir
) -> None:
    launcher.install_version_directory(make_version_dir(), version_id="game")
    launcher.create_instance("second", version_id="game")

    app = DolctlApp(launcher)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        assert launcher.active_instance() == "default"

        await pilot.press("down")
        summary = app.query_one("#instance-summary", Static)
        assert "second" in str(summary.render())
        assert launcher.active_instance() == "default"
        assert not app.query_one("#make-active", Button).disabled


@pytest.mark.asyncio
async def test_play_stays_usable_in_an_80_column_terminal(
    launcher: Launcher,
) -> None:
    app = DolctlApp(launcher)
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        detail = app.query_one("#instance-detail")
        launch = app.query_one("#launch-instance", Button)
        status = app.query_one("#status")

        assert detail.allow_vertical_scroll
        assert launch.region.bottom <= status.region.y


@pytest.mark.asyncio
async def test_enabled_mods_expand_into_the_page_scroll(
    launcher: Launcher, make_mod_zip
) -> None:
    for index in range(12):
        mod_id = launcher.install_mod(
            str(make_mod_zip(f"mod-{index}.zip", mod_name=f"Mod {index}"))
        )
        launcher.enable_mod("default", mod_id)

    app = DolctlApp(launcher)
    async with app.run_test(size=(100, 24)) as pilot:
        await pilot.pause()
        table = app.query_one("#enabled-mods", DataTable)
        detail = app.query_one("#instance-detail")

        assert table.row_count == 12
        assert table.max_scroll_y == 0
        assert detail.max_scroll_y > 0


@pytest.mark.asyncio
async def test_tui_keeps_native_ansi_slots_at_runtime(
    launcher: Launcher, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("NO_COLOR", raising=False)
    app = DolctlApp(launcher)
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()

        assert app.native_ansi_color
        topbar = app.query_one("#topbar")
        assert topbar.styles.background.ansi == -1
        assert topbar.styles.border_top[1].ansi == 4

        current_page = app.query_one("#nav-play", Button).rich_style
        assert current_page.color is not None
        assert current_page.bgcolor is not None
        assert current_page.color.type is ColorType.STANDARD
        assert current_page.color.number == 0
        assert current_page.bgcolor.type is ColorType.STANDARD
        assert current_page.bgcolor.number == 4

        launch = app.query_one("#launch-instance", Button).rich_style
        assert launch.color is not None
        assert launch.bgcolor is not None
        assert launch.color.type is ColorType.STANDARD
        assert launch.color.number == 0
        assert launch.bgcolor.type is ColorType.STANDARD
        assert launch.bgcolor.number == 2


@pytest.mark.asyncio
async def test_workspace_shortcuts_do_not_capture_input_text(
    launcher: Launcher,
) -> None:
    app = DolctlApp(launcher)
    async with app.run_test(size=(100, 35)) as pilot:
        app.open_library("mods")
        source = app.query_one("#source", Input)
        source.focus()

        await pilot.press("2", "q")
        await pilot.pause()

        assert source.value == "2q"
        assert app.query_one("#library-page").has_class("-current")


@pytest.mark.asyncio
async def test_library_filters_game_and_mod_sources(launcher: Launcher) -> None:
    launcher.add_channel("image-pack", preset="dol-image-pack")
    app = DolctlApp(launcher)
    async with app.run_test(size=(120, 40)) as pilot:
        app.open_library("mods")
        await pilot.pause()

        version_source = app.query_one("#version-source")
        mod_source = app.query_one("#mod-source")
        assert str(version_source.value) == "modloader"
        assert str(mod_source.value) == "image-pack"


@pytest.mark.asyncio
async def test_mod_manager_saves_toggle_and_order_as_one_change(
    launcher: Launcher, make_mod_zip
) -> None:
    alpha = launcher.install_mod(str(make_mod_zip("alpha.zip", mod_name="Alpha")))
    beta = launcher.install_mod(str(make_mod_zip("beta.zip", mod_name="Beta")))
    launcher.enable_mod("default", alpha)

    app = DolctlApp(launcher)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        result: list[list[str] | None] = []
        app.push_screen(
            ModManagerModal(launcher.instance("default"), launcher.mods()),
            result.append,
        )
        await pilot.pause()
        assert isinstance(app.screen, ModManagerModal)

        await pilot.press("down", "space", "plus")
        await pilot.click("#mod-manager-save")
        await pilot.pause()
        assert result == [[beta, alpha]]
        assert launcher.instance("default").mod_order == [alpha]


@pytest.mark.asyncio
async def test_repeated_data_notifications_are_safe(launcher: Launcher) -> None:
    app = DolctlApp(launcher)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        for _ in range(3):
            app.notify_data_changed()
            await pilot.pause()


@pytest.mark.asyncio
async def test_system_page_renders_diagnostics_for_corrupt_config(
    launcher: Launcher,
) -> None:
    (launcher.root / ".dolctl" / "config.toml").write_text("[", encoding="utf-8")
    app = DolctlApp(launcher)
    async with app.run_test(size=(120, 40)) as pilot:
        app.action_switch_page("system")
        await pilot.pause()
        rendered = str(app.query_one(SystemTab).query_one("#checks").render())
        assert "Cannot read config" in rendered


def test_tui_uses_only_ansi_16_terminal_colours() -> None:
    tui_root = Path(__file__).parents[2] / "dolctl" / "tui"
    source = "\n".join(
        path.read_text(encoding="utf-8") for path in tui_root.rglob("*.py")
    )

    assert not re.search(r"(?<![\w-])#[0-9a-fA-F]{3,8}\b", source)
    assert not re.search(r"\b(?:rgb|rgba|hsl|hsla)\(", source)
    assert "variant=" not in source
    allowed_colours = ANSI_16_COLOURS | {"ansi_default"}
    source_colours = set(re.findall(r"ansi_[a-z_]+", source))
    assert source_colours <= allowed_colours
    assert {
        "ansi_blue",
        "ansi_cyan",
        "ansi_green",
        "ansi_yellow",
        "ansi_red",
    } <= source_colours
    assert "background: ansi_default" in TERMINAL_CSS

    variables = {
        **TERMINAL_THEME.to_color_system().generate(),
        **TERMINAL_THEME.variables,
    }
    theme_colours = {
        colour
        for value in variables.values()
        for colour in re.findall(r"ansi_[a-z_]+", value)
    }
    assert theme_colours <= allowed_colours
