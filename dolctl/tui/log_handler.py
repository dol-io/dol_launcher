"""logging.Handler that pushes records into a Textual RichLog widget."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from textual.app import App
    from textual.widgets import RichLog


class RichLogHandler(logging.Handler):
    """Mirror dolctl logger output into a RichLog widget.

    Format is intentionally terser than the file handler (time + level
    + message only) since the screen is narrower than a log file.
    """

    def __init__(self, app: "App", widget: "RichLog") -> None:
        super().__init__(level=logging.INFO)
        self._app = app
        self._widget = widget
        self.setFormatter(logging.Formatter("%(asctime)s %(levelname)-5s %(message)s", "%H:%M:%S"))

    def emit(self, record: logging.LogRecord) -> None:
        try:
            message = self.format(record)
        except Exception:  # noqa: BLE001
            self.handleError(record)
            return
        # emit() can be called from worker threads; marshal back to UI.
        self._app.call_from_thread(self._widget.write, message)
