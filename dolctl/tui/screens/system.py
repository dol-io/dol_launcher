from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Button, Static

from .base import RefreshableTab


class SystemTab(RefreshableTab):
    DEFAULT_CSS = """
    SystemTab #summary { height: auto; padding-bottom: 1; }
    SystemTab #checks { height: 1fr; border: round; padding: 1; }
    SystemTab #actions { height: auto; padding-top: 1; }
    """

    def compose(self) -> ComposeResult:
        yield Static("", id="summary")
        yield Static("", id="checks")
        with Horizontal(id="actions"):
            yield Button("Run diagnostics", id="refresh", variant="primary")

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._last_doctor_ok = False

    def refresh_from_disk(self) -> None:
        report = self.launcher.doctor()
        self._last_doctor_ok = report.ok
        self.query_one("#checks", Static).update(
            "\n".join(
                f"[{'green' if check.ok else 'red'}]"
                f"{'✓' if check.ok else '✗'}[/] {check.message}"
                for check in report.checks
            )
        )
        try:
            snapshot = self.launcher.snapshot()
        except Exception as exc:  # noqa: BLE001
            summary = f"[b]ROOT[/b] {self.launcher.root}\nData unavailable: {exc}"
        else:
            summary = (
                f"[b]ROOT[/b] {self.launcher.root}\n"
                f"{len(snapshot.profiles)} instance(s)  ·  "
                f"{len(snapshot.versions)} version(s)  ·  "
                f"{len(snapshot.mods)} mod(s)  ·  "
                f"{len(snapshot.channels)} source(s)"
            )
        self.query_one("#summary", Static).update(summary)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "refresh":
            self.reload_from_disk()
            self.set_status(
                "Diagnostics passed"
                if self._last_doctor_ok
                else "Diagnostics found problems",
                "success" if self._last_doctor_ok else "error",
            )
