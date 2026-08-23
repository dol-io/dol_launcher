from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.widgets import Button, Static

from .imagepacks import ImagepacksTab
from .mods import ModsTab
from .sources import SourcesTab
from .versions import VersionsTab


_SECTIONS = ("versions", "mods", "imagepacks", "sources")


class LibraryScreen(Container):
    """Installed content and download sources, kept out of the launch flow."""

    DEFAULT_CSS = """
    LibraryScreen {
        padding: 1 2;
    }

    LibraryScreen #library-heading {
        height: auto;
        padding-bottom: 1;
    }

    LibraryScreen #library-navigation {
        height: 2;
        padding-bottom: 1;
    }

    LibraryScreen #library-navigation Button {
        margin-right: 1;
    }

    LibraryScreen #library-content {
        height: 1fr;
    }

    LibraryScreen .library-section {
        display: none;
    }

    LibraryScreen .library-section.-current {
        display: block;
    }
    """

    def compose(self) -> ComposeResult:
        heading = Text("Library", style="bold yellow")
        heading.append(
            "\nInstall versions, mods, and imagepacks before assigning them to an instance.",
            style="bright_black",
        )
        yield Static(heading, id="library-heading")
        with Horizontal(id="library-navigation"):
            yield Button(
                "Versions",
                id="library-versions",
                classes="subnav-button -current",
            )
            yield Button("Mods", id="library-mods", classes="subnav-button")
            yield Button(
                "Imagepacks",
                id="library-imagepacks",
                classes="subnav-button",
            )
            yield Button(
                "Mod sources", id="library-sources", classes="subnav-button"
            )
        with Container(id="library-content"):
            yield VersionsTab(
                id="versions-section",
                classes="library-section -current",
            )
            yield ModsTab(id="mods-section", classes="library-section")
            yield ImagepacksTab(
                id="imagepacks-section",
                classes="library-section",
            )
            yield SourcesTab(id="sources-section", classes="library-section")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id or ""
        if button_id.startswith("library-"):
            self.show_section(button_id.removeprefix("library-"))

    def show_section(self, section: str) -> None:
        if section not in _SECTIONS or not self.is_mounted:
            return
        for candidate in _SECTIONS:
            current = candidate == section
            self.query_one(f"#{candidate}-section").set_class(current, "-current")
            self.query_one(f"#library-{candidate}", Button).set_class(
                current, "-current"
            )
