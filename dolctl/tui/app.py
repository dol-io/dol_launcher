from __future__ import annotations

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal
from textual.reactive import reactive
from textual.widgets import Button, Label, Static

from core.launcher import Launcher

from .. import __version__
from .modals import InfoModal
from .screens.instances import InstancesTab
from .screens.library import LibraryScreen
from .screens.system import SystemTab
from .theme import TERMINAL_CSS, TERMINAL_THEME


_PAGES = ("play", "library", "system")


class StatusBar(Label):
    DEFAULT_CSS = "StatusBar { height: 1; padding: 0 1; }"

    _PREFIXES = {
        "success": "OK",
        "warning": "!",
        "error": "ERROR",
    }

    def show_message(self, message: str, level: str = "info") -> None:
        prefix = self._PREFIXES.get(level)
        self.update(f"{prefix}: {message}" if prefix else message)


class DolctlApp(App[None]):
    CSS = (
        TERMINAL_CSS
        + """
    #topbar {
        height: 1;
        padding: 0 1;
    }

    #brand {
        width: auto;
        text-style: bold;
    }

    #root-context {
        width: 1fr;
        text-align: right;
        text-overflow: ellipsis;
    }

    #navigation {
        height: 3;
        padding-left: 1;
        border-bottom: solid ansi_default;
    }

    #navigation Button {
        margin-right: 1;
    }

    #workspace {
        height: 1fr;
    }

    .workspace-page {
        display: none;
    }

    .workspace-page.-current {
        display: block;
    }

    #status {
        border-top: solid ansi_default;
    }

    #keybar {
        height: 1;
        padding: 0 1;
        text-align: right;
        text-style: dim;
    }
    """
    )

    BINDINGS = [
        Binding("1", "switch_page('play')", "Play", show=False),
        Binding("2", "switch_page('library')", "Library", show=False),
        Binding("3", "switch_page('system')", "System", show=False),
        Binding("f5", "refresh", "Refresh", show=False),
        Binding("q", "quit", "Quit", show=False),
        Binding("?", "help", "Help", show=False),
    ]

    data_version: reactive[int] = reactive(0, init=False)

    def __init__(self, launcher: Launcher) -> None:
        super().__init__()
        self.launcher = launcher
        self.register_theme(TERMINAL_THEME)
        self.theme = TERMINAL_THEME.name

    def compose(self) -> ComposeResult:
        with Horizontal(id="topbar"):
            yield Static(f"dolctl {__version__}", id="brand", markup=False)
            yield Static(str(self.launcher.root), id="root-context", markup=False)
        with Horizontal(id="navigation"):
            yield Button("1  Play", id="nav-play", classes="-current")
            yield Button("2  Library", id="nav-library")
            yield Button("3  System", id="nav-system")
        with Container(id="workspace"):
            yield InstancesTab(id="play-page", classes="workspace-page -current")
            yield LibraryScreen(id="library-page", classes="workspace-page")
            yield SystemTab(id="system-page", classes="workspace-page")
        yield StatusBar("Ready", id="status", markup=False)
        yield Static(
            "F5 refresh   ? help   q quit",
            id="keybar",
            markup=False,
        )

    def on_mount(self) -> None:
        self.title = "dolctl"
        self.sub_title = "Instance launcher"
        self.query_one("#instance-list").focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id or ""
        if button_id.startswith("nav-"):
            self.action_switch_page(button_id.removeprefix("nav-"))

    def action_switch_page(self, page_id: str) -> None:
        if page_id not in _PAGES:
            return
        for candidate in _PAGES:
            current = candidate == page_id
            self.query_one(f"#{candidate}-page").set_class(current, "-current")
            self.query_one(f"#nav-{candidate}", Button).set_class(current, "-current")

    def open_library(self, section: str) -> None:
        self.action_switch_page("library")
        self.query_one(LibraryScreen).show_section(section)

    def action_refresh(self) -> None:
        self.notify_data_changed()
        self.set_status("Reloaded launcher data", "success")

    def action_help(self) -> None:
        self.push_screen(
            InfoModal(
                "Keyboard shortcuts",
                "Global\n"
                "1 / 2 / 3   Play / Library / System\n"
                "F5          reload launcher data\n"
                "q           quit\n"
                "?           show this help\n\n"
                "Play\n"
                "n           new instance\n"
                "a           make selected instance active\n"
                "e           edit launch settings\n"
                "m           manage enabled mods\n"
                "b           build\n"
                "l           launch\n"
                "x           stop server",
            )
        )

    def set_status(self, message: str, level: str = "info") -> None:
        self.query_one("#status", StatusBar).show_message(message, level)

    def notify_data_changed(self) -> None:
        self.data_version += 1
