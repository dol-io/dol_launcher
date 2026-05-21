from __future__ import annotations

from textual.app import ComposeResult
from textual.widgets import Static

from .base import RefreshableTab


class ChannelsTab(RefreshableTab):
    def compose(self) -> ComposeResult:
        yield Static("Channels — coming soon", id="channels-placeholder")
