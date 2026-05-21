from __future__ import annotations

from textual.app import ComposeResult
from textual.widgets import Static

from .base import RefreshableTab


class ModsTab(RefreshableTab):
    def compose(self) -> ComposeResult:
        yield Static("Mods — coming soon", id="mods-placeholder")
