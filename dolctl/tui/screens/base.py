"""Shared base class for TUI tabs.

Each tab is a Container that knows how to refresh its on-disk state.
The App bumps a reactive `data_version`; tabs watch it and call
``refresh_from_disk`` when it changes.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from textual.containers import Container

if TYPE_CHECKING:
    from ..app import DolctlApp


def _fmt_mb(b: int) -> str:
    return f"{b / 1_048_576:.1f} MB"


def make_progress_reporter(
    app: "DolctlApp",
    setter: Callable[[str, str], None],
    label: str,
    min_interval: float = 0.1,
) -> Callable[[int, int | None], None]:
    """Build a download progress callback that throttles UI updates.

    The callback runs on the download worker thread; ``setter`` is the
    bound RefreshableTab.set_status that marshals back to the UI thread
    via ``call_from_thread``. Limiting to one update per ``min_interval``
    (default 100 ms) keeps the UI responsive without dropping the final
    completion update.
    """
    state = {"last": 0.0}

    def report(downloaded: int, total: int | None) -> None:
        now = time.monotonic()
        # Always emit the very first tick and the completion tick.
        if downloaded != total and now - state["last"] < min_interval:
            return
        state["last"] = now
        if total:
            pct = downloaded * 100 // total
            msg = f"{label}: {_fmt_mb(downloaded)} / {_fmt_mb(total)} ({pct}%)"
        else:
            msg = f"{label}: {_fmt_mb(downloaded)}"
        app.call_from_thread(setter, msg, "info")

    return report


class RefreshableTab(Container):
    """Container subclass providing common access to the root and refresh hooks."""

    DEFAULT_CSS = """
    RefreshableTab {
        padding: 1 2;
        overflow-y: auto;
    }
    """

    def on_mount(self) -> None:
        self.refresh_from_disk()
        # init=False so the watch doesn't fire an immediate second refresh
        # (we already called refresh_from_disk above).
        self.watch(
            self.app, "data_version", lambda _new: self.refresh_from_disk(), init=False
        )

    def refresh_from_disk(self) -> None:
        """Override to reload widget state from on-disk config."""

    # ----- helpers ------------------------------------------------------

    @property
    def dolctl_app(self) -> "DolctlApp":
        return self.app  # type: ignore[return-value]

    @property
    def root(self) -> Path:
        return self.dolctl_app.root_path

    def set_status(self, message: str, level: str = "info") -> None:
        self.dolctl_app.set_status(message, level)

    def notify_data_changed(self) -> None:
        self.dolctl_app.bump_data()
