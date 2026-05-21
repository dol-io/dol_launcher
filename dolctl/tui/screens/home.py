from __future__ import annotations

from textual.app import ComposeResult
from textual.widgets import Static

from .base import RefreshableTab


class HomeTab(RefreshableTab):
    def compose(self) -> ComposeResult:
        yield Static("Home — coming soon", id="home-placeholder")
