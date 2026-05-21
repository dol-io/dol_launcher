"""Shared base class for TUI tabs.

Each tab is a Container that knows how to refresh its on-disk state.
The App bumps a reactive `data_version`; tabs watch it and call
``refresh_from_disk`` when it changes.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from textual.containers import Container

if TYPE_CHECKING:
    from ..app import DolctlApp


class RefreshableTab(Container):
    """Container subclass providing common access to the root and refresh hooks."""

    DEFAULT_CSS = """
    RefreshableTab {
        padding: 1 2;
    }
    """

    def on_mount(self) -> None:
        self.refresh_from_disk()
        self.watch(self.app, "data_version", lambda _new: self.refresh_from_disk())

    def refresh_from_disk(self) -> None:
        """Override to reload widget state from on-disk config."""

    # ----- helpers ------------------------------------------------------

    @property
    def dolctl_app(self) -> "DolctlApp":
        return self.app  # type: ignore[return-value]

    @property
    def root(self) -> Path:
        return self.dolctl_app.root_path

    def set_status(self, message: str) -> None:
        self.dolctl_app.set_status(message)

    def notify_data_changed(self) -> None:
        self.dolctl_app.bump_data()
