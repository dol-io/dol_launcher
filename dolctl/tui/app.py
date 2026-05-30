"""DolctlApp — Textual TUI front-end for dolctl.

The CLI in ``dolctl.cli`` remains the canonical interface; the TUI is an
alternative driver that imports the same ``core.*`` helpers. Each tab
re-reads from disk so the two front-ends can be used interchangeably in
the same session.
"""

from __future__ import annotations

from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.reactive import reactive
from textual.widgets import Footer, Header, Label, TabbedContent, TabPane

from .. import __version__
from .modals import InfoModal
from .screens.channels import ChannelsTab
from .screens.doctor import DoctorTab
from .screens.home import HomeTab
from .screens.mods import ModsTab
from .screens.profiles import ProfilesTab
from .screens.run import RunTab
from .screens.versions import VersionsTab


_TAB_IDS = ("home", "channels", "versions", "mods", "profiles", "run", "doctor")


_LEVEL_TAG = {
    "info": "",
    "success": "[green]",
    "warn": "[yellow]",
    "error": "[red]",
}


class StatusBar(Label):
    """One-line status / last-action display above the footer.

    The most recent message wins (single line), but the level
    classifies it: success/warn/error get an ANSI colour tag so the
    user can tell at a glance whether an operation succeeded.
    """

    DEFAULT_CSS = """
    StatusBar {
        height: 1;
        padding: 0 1;
    }
    """

    def set_status(self, message: str, level: str = "info") -> None:
        tag = _LEVEL_TAG.get(level, "")
        close = "[/]" if tag else ""
        self.update(f"{tag}{message}{close}")


class DolctlApp(App):
    CSS = """
    #version-row { height: 1; }
    #version-info { width: auto; padding: 0 1; }
    TabbedContent { height: 1fr; }
    """

    BINDINGS = [
        Binding("1", "switch_tab('home')", "Home", show=False),
        Binding("2", "switch_tab('channels')", "Channels", show=False),
        Binding("3", "switch_tab('versions')", "Versions", show=False),
        Binding("4", "switch_tab('mods')", "Mods", show=False),
        Binding("5", "switch_tab('profiles')", "Profiles", show=False),
        Binding("6", "switch_tab('run')", "Run", show=False),
        Binding("7", "switch_tab('doctor')", "Doctor", show=False),
        Binding("f5", "refresh_active_tab", "Refresh", show=True),
        Binding("r", "refresh_active_tab", "Refresh", show=False),
        Binding("q", "quit", "Quit", show=True),
        Binding("?", "help", "Help", show=True),
    ]

    # Bumped by any write operation so subscribing tabs reload from disk
    # when they next become visible. See base.py:RefreshableTab.
    # init=False: tabs do their first refresh in on_mount; we don't want
    # the reactive's auto-init to fire all watchers again.
    data_version: reactive[int] = reactive(0, init=False)

    def __init__(self, root: Path) -> None:
        super().__init__()
        self.root_path = root

    # ----- composition --------------------------------------------------

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with Horizontal(id="version-row"):
            yield Label(f"dolctl v{__version__}", id="version-info")
        with TabbedContent(initial="home", id="tabs"):
            with TabPane("1·Home", id="home"):
                yield HomeTab(id="home-tab")
            with TabPane("2·Channels", id="channels"):
                yield ChannelsTab(id="channels-tab")
            with TabPane("3·Versions", id="versions"):
                yield VersionsTab(id="versions-tab")
            with TabPane("4·Mods", id="mods"):
                yield ModsTab(id="mods-tab")
            with TabPane("5·Profiles", id="profiles"):
                yield ProfilesTab(id="profiles-tab")
            with TabPane("6·Run", id="run"):
                yield RunTab(id="run-tab")
            with TabPane("7·Doctor", id="doctor"):
                yield DoctorTab(id="doctor-tab")
        yield StatusBar("ready", id="status")
        yield Footer()

    # ----- lifecycle ----------------------------------------------------

    def on_mount(self) -> None:
        self.title = f"dolctl · {self.root_path}"
        self.sub_title = "TUI"

    # ----- actions ------------------------------------------------------

    def action_switch_tab(self, tab_id: str) -> None:
        if tab_id not in _TAB_IDS:
            return
        self.query_one("#tabs", TabbedContent).active = tab_id

    def action_refresh_active_tab(self) -> None:
        self.bump_data()
        self.set_status("refreshed")

    def action_help(self) -> None:
        body = (
            "Global\n"
            "  1-7       switch tab (numbers shown in tab labels)\n"
            "  r / F5    refresh active tab from disk\n"
            "  ?         this help\n"
            "  q         quit\n"
            "\n"
            "Profiles tab\n"
            "  space     toggle mod enabled/disabled (on selected row)\n"
            "  +         move enabled mod up in load order\n"
            "  -         move enabled mod down in load order\n"
            "\n"
            "Most tabs\n"
            "  Tab / Shift+Tab     move focus between controls\n"
            "  Enter               activate the focused button\n"
            "  Esc                 close the current modal\n"
        )
        self.push_screen(InfoModal("Keyboard shortcuts", body))

    # ----- public helpers used by tabs ----------------------------------

    def set_status(self, message: str, level: str = "info") -> None:
        self.query_one("#status", StatusBar).set_status(message, level)

    def bump_data(self) -> None:
        """Notify all tabs that on-disk state changed."""
        self.data_version += 1
