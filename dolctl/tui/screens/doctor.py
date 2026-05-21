from __future__ import annotations

from textual.app import ComposeResult
from textual.widgets import Static

from .base import RefreshableTab


class DoctorTab(RefreshableTab):
    def compose(self) -> ComposeResult:
        yield Static("Doctor — coming soon", id="doctor-placeholder")
