from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Button, Static

from .base import RefreshableTab


class SystemTab(RefreshableTab):
    DEFAULT_CSS = """
    SystemTab #summary { height: auto; padding-bottom: 1; }
    SystemTab #checks {
        height: 1fr;
        border: round ansi_blue;
        border-title-color: ansi_yellow;
        border-title-background: ansi_default;
        border-title-style: bold;
        padding: 1;
    }
    SystemTab #actions { height: auto; padding-top: 1; }
    """

    def compose(self) -> ComposeResult:
        yield Static("", id="summary", markup=False)
        checks = Static("", id="checks", markup=False)
        checks.border_title = " Diagnostics "
        yield checks
        with Horizontal(id="actions"):
            yield Button("Run diagnostics", id="refresh", classes="action-accent")

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._last_doctor_ok = False

    def refresh_from_disk(self) -> None:
        report = self.launcher.doctor()
        self._last_doctor_ok = report.ok
        check_lines: list[Text] = []
        for check in report.checks:
            line = Text()
            line.append(
                "OK  " if check.ok else "FAIL  ",
                style="bold green" if check.ok else "bold red",
            )
            line.append(check.message)
            check_lines.append(line)
        self.query_one("#checks", Static).update(Text("\n").join(check_lines))
        summary = Text()
        summary.append("ROOT  ", style="bold yellow")
        summary.append(str(self.launcher.root))
        summary.append("\n")
        try:
            snapshot = self.launcher.snapshot()
        except Exception as exc:  # noqa: BLE001
            summary.append(f"Data unavailable: {exc}", style="red")
        else:
            summary.append(
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
