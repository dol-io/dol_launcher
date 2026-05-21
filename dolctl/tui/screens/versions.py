from __future__ import annotations

from textual.app import ComposeResult
from textual.widgets import Static

from .base import RefreshableTab


class VersionsTab(RefreshableTab):
    def compose(self) -> ComposeResult:
        yield Static("Versions — coming soon", id="versions-placeholder")
