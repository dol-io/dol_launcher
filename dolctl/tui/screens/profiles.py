from __future__ import annotations

from textual.app import ComposeResult
from textual.widgets import Static

from .base import RefreshableTab


class ProfilesTab(RefreshableTab):
    def compose(self) -> ComposeResult:
        yield Static("Profiles — coming soon", id="profiles-placeholder")
