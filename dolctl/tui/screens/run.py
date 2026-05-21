from __future__ import annotations

from textual.app import ComposeResult
from textual.widgets import Static

from .base import RefreshableTab


class RunTab(RefreshableTab):
    def compose(self) -> ComposeResult:
        yield Static("Run — coming soon", id="run-placeholder")
