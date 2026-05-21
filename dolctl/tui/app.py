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
from .screens.channels import ChannelsTab
from .screens.doctor import DoctorTab
from .screens.home import HomeTab
from .screens.mods import ModsTab
from .screens.profiles import ProfilesTab
from .screens.run import RunTab
from .screens.versions import VersionsTab


_TAB_IDS = ("home", "channels", "versions", "mods", "profiles", "run", "doctor")


class StatusBar(Label):
    """One-line status / last-action display above the footer."""

    DEFAULT_CSS = """
    StatusBar {
        height: 1;
        padding: 0 1;
        background: $panel;
        color: $text-muted;
    }
    """

    def set_status(self, message: str) -> None:
        self.update(message)


class DolctlApp(App):
    CSS = """
    Screen { background: $surface; }
    #version-info { width: auto; padding: 0 1; color: $text-muted; }
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
    data_version: reactive[int] = reactive(0)

    def __init__(self, root: Path) -> None:
        super().__init__()
        self.root_path = root

    # ----- composition --------------------------------------------------

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with Horizontal(id="version-row"):
            yield Label(f"dolctl v{__version__}", id="version-info")
        with TabbedContent(initial="home", id="tabs"):
            with TabPane("Home", id="home"):
                yield HomeTab(id="home-tab")
            with TabPane("Channels", id="channels"):
                yield ChannelsTab(id="channels-tab")
            with TabPane("Versions", id="versions"):
                yield VersionsTab(id="versions-tab")
            with TabPane("Mods", id="mods"):
                yield ModsTab(id="mods-tab")
            with TabPane("Profiles", id="profiles"):
                yield ProfilesTab(id="profiles-tab")
            with TabPane("Run", id="run"):
                yield RunTab(id="run-tab")
            with TabPane("Doctor", id="doctor"):
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
        self.set_status(
            "keys: 1-7 switch tab · F5 refresh · q quit · "
            "(tab-specific shortcuts shown at bottom)"
        )

    # ----- public helpers used by tabs ----------------------------------

    def set_status(self, message: str) -> None:
        self.query_one("#status", StatusBar).set_status(message)

    def bump_data(self) -> None:
        """Notify all tabs that on-disk state changed."""
        self.data_version += 1
