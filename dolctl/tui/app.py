from __future__ import annotations

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.reactive import reactive
from textual.widgets import Footer, Header, Label, TabbedContent, TabPane

from core.launcher import Launcher

from .. import __version__
from .modals import InfoModal
from .screens.instances import InstancesTab
from .screens.mods import ModsTab
from .screens.sources import SourcesTab
from .screens.system import SystemTab
from .screens.versions import VersionsTab


_TABS = ("instances", "versions", "mods", "sources", "system")


class StatusBar(Label):
    DEFAULT_CSS = "StatusBar { height: 1; padding: 0 1; }"

    def show_message(self, message: str, level: str = "info") -> None:
        colour = {
            "success": "green",
            "warning": "yellow",
            "error": "red",
        }.get(level)
        self.update(f"[{colour}]{message}[/]" if colour else message)


class DolctlApp(App[None]):
    CSS = """
    #context-row { height: 1; }
    #context { width: auto; padding: 0 1; }
    TabbedContent { height: 1fr; }
    """

    BINDINGS = [
        Binding("1", "switch_tab('instances')", "Instances", show=False),
        Binding("2", "switch_tab('versions')", "Versions", show=False),
        Binding("3", "switch_tab('mods')", "Mods", show=False),
        Binding("4", "switch_tab('sources')", "Sources", show=False),
        Binding("5", "switch_tab('system')", "System", show=False),
        Binding("f5", "refresh", "Refresh"),
        Binding("q", "quit", "Quit"),
        Binding("?", "help", "Help"),
    ]

    data_version: reactive[int] = reactive(0, init=False)

    def __init__(self, launcher: Launcher) -> None:
        super().__init__()
        self.launcher = launcher

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with Horizontal(id="context-row"):
            yield Label(
                f"dolctl {__version__}  ·  {self.launcher.root}",
                id="context",
            )
        with TabbedContent(initial="instances", id="tabs"):
            with TabPane("1·Instances", id="instances"):
                yield InstancesTab(id="instances-tab")
            with TabPane("2·Versions", id="versions"):
                yield VersionsTab(id="versions-tab")
            with TabPane("3·Mods", id="mods"):
                yield ModsTab(id="mods-tab")
            with TabPane("4·Sources", id="sources"):
                yield SourcesTab(id="sources-tab")
            with TabPane("5·System", id="system"):
                yield SystemTab(id="system-tab")
        yield StatusBar("Ready", id="status")
        yield Footer()

    def on_mount(self) -> None:
        self.title = "dolctl"
        self.sub_title = "Instance launcher"

    def action_switch_tab(self, tab_id: str) -> None:
        if tab_id in _TABS:
            self.query_one("#tabs", TabbedContent).active = tab_id

    def action_refresh(self) -> None:
        self.notify_data_changed()
        self.set_status("Reloaded launcher data", "success")

    def action_help(self) -> None:
        self.push_screen(
            InfoModal(
                "Keyboard shortcuts",
                "1-5    switch page\n"
                "F5     reload launcher data\n"
                "q      quit\n"
                "?      show this help\n\n"
                "Instances\n"
                "Space  toggle selected mod\n"
                "+/-    move enabled mod up/down",
            )
        )

    def set_status(self, message: str, level: str = "info") -> None:
        self.query_one("#status", StatusBar).show_message(message, level)

    def notify_data_changed(self) -> None:
        self.data_version += 1
