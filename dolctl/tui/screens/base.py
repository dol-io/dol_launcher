from __future__ import annotations

import time
from typing import Any, Callable, TYPE_CHECKING

from textual.containers import Container
from textual.widgets import Button

from core.models import DolCtlError

if TYPE_CHECKING:
    from core.launcher import Launcher
    from ..app import DolctlApp


class RefreshableTab(Container):
    DEFAULT_CSS = """
    RefreshableTab {
        padding: 1 2;
        overflow-y: auto;
    }
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._busy = False

    @property
    def dolctl_app(self) -> "DolctlApp":
        return self.app  # type: ignore[return-value]

    @property
    def launcher(self) -> "Launcher":
        return self.dolctl_app.launcher

    def on_mount(self) -> None:
        self.reload_from_disk()
        self.watch(
            self.app,
            "data_version",
            lambda _value: self.reload_from_disk(),
            init=False,
        )

    def refresh_from_disk(self) -> None:
        pass

    def reload_from_disk(self) -> None:
        try:
            self.refresh_from_disk()
        except DolCtlError as exc:
            self.set_status(str(exc), "error")
        except Exception as exc:  # noqa: BLE001
            self.set_status(f"Unexpected refresh error: {exc}", "error")

    def set_status(self, message: str, level: str = "info") -> None:
        self.dolctl_app.set_status(message, level)

    def notify_data_changed(self) -> None:
        self.dolctl_app.notify_data_changed()

    def set_busy(self, busy: bool) -> None:
        self._busy = busy
        for button in self.query(Button):
            button.disabled = busy

    def run_operation(
        self,
        label: str,
        operation: Callable[[], Any],
        on_success: Callable[[Any], None] | None = None,
        *,
        mutates: bool = False,
    ) -> None:
        if self._busy:
            self.set_status("Another operation is still running", "warning")
            return
        self.set_busy(True)
        self.set_status(label)

        def worker() -> None:
            try:
                result = operation()
            except DolCtlError as exc:
                self.app.call_from_thread(self._operation_failed, str(exc))
            except Exception as exc:  # noqa: BLE001
                self.app.call_from_thread(
                    self._operation_failed,
                    f"Unexpected error: {exc}",
                )
            else:
                self.app.call_from_thread(
                    self._operation_succeeded,
                    result,
                    on_success,
                    mutates,
                )

        self.run_worker(worker, thread=True, exclusive=True)

    def _operation_failed(self, message: str) -> None:
        self.set_busy(False)
        self.set_status(message, "error")

    def _operation_succeeded(
        self,
        result: Any,
        callback: Callable[[Any], None] | None,
        mutates: bool,
    ) -> None:
        self.set_busy(False)
        if callback is not None:
            callback(result)
        if mutates:
            self.notify_data_changed()

    def progress_reporter(
        self, label: str, *, min_interval: float = 0.1
    ) -> Callable[[int, int | None], None]:
        state = {"last": 0.0}

        def report(downloaded: int, total: int | None) -> None:
            now = time.monotonic()
            if downloaded != total and now - state["last"] < min_interval:
                return
            state["last"] = now
            downloaded_mb = downloaded / 1_048_576
            if total:
                message = (
                    f"{label}: {downloaded_mb:.1f}/{total / 1_048_576:.1f} MB "
                    f"({downloaded * 100 // total}%)"
                )
            else:
                message = f"{label}: {downloaded_mb:.1f} MB"
            self.app.call_from_thread(self.set_status, message, "info")

        return report
