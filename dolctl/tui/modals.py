"""Reusable modal screens: confirmation, single/multi-input prompts."""

from __future__ import annotations

from typing import Callable, Sequence

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Static


class ConfirmModal(ModalScreen[bool]):
    DEFAULT_CSS = """
    ConfirmModal { align: center middle; }
    ConfirmModal > Vertical {
        width: 60;
        height: auto;
        border: thick;
        padding: 1 2;
    }
    ConfirmModal Horizontal { height: auto; align: center middle; padding-top: 1; }
    ConfirmModal Button { margin: 0 1; }
    """

    BINDINGS = [Binding("escape", "dismiss(False)", "Cancel")]

    def __init__(self, prompt: str, *, confirm_label: str = "OK") -> None:
        super().__init__()
        self.prompt = prompt
        self.confirm_label = confirm_label

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static(self.prompt)
            with Horizontal():
                yield Button(self.confirm_label, variant="primary", id="ok")
                yield Button("Cancel", id="cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "ok")


class InputField:
    def __init__(
        self,
        key: str,
        label: str,
        *,
        placeholder: str = "",
        default: str = "",
        required: bool = False,
    ) -> None:
        self.key = key
        self.label = label
        self.placeholder = placeholder
        self.default = default
        self.required = required


class InputModal(ModalScreen[dict[str, str] | None]):
    """Generic multi-field input modal. Returns None on cancel."""

    DEFAULT_CSS = """
    InputModal { align: center middle; }
    InputModal > Vertical {
        width: 70;
        height: auto;
        border: thick;
        padding: 1 2;
    }
    InputModal Label.field-label {
        padding-top: 1;
    }
    InputModal Horizontal { height: auto; align: center middle; padding-top: 1; }
    InputModal Button { margin: 0 1; }
    """

    BINDINGS = [Binding("escape", "dismiss(None)", "Cancel")]

    def __init__(
        self,
        title: str,
        fields: Sequence[InputField],
        *,
        validator: Callable[[dict[str, str]], str | None] | None = None,
    ) -> None:
        super().__init__()
        self.title_text = title
        self.fields = list(fields)
        self.validator = validator

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static(f"[b]{self.title_text}[/b]")
            for field in self.fields:
                yield Label(field.label, classes="field-label")
                yield Input(
                    value=field.default,
                    placeholder=field.placeholder,
                    id=f"field-{field.key}",
                )
            yield Static("", id="error")
            with Horizontal():
                yield Button("OK", variant="primary", id="ok")
                yield Button("Cancel", id="cancel")

    def _collect(self) -> dict[str, str]:
        result: dict[str, str] = {}
        for field in self.fields:
            value = self.query_one(f"#field-{field.key}", Input).value.strip()
            result[field.key] = value
        return result

    def _set_error(self, message: str) -> None:
        self.query_one("#error", Static).update(f"[red]{message}[/red]")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel":
            self.dismiss(None)
            return
        values = self._collect()
        for field in self.fields:
            if field.required and not values[field.key]:
                self._set_error(f"{field.label} is required")
                return
        if self.validator is not None:
            error = self.validator(values)
            if error:
                self._set_error(error)
                return
        self.dismiss(values)


class InfoModal(ModalScreen[None]):
    """Read-only info modal — used for `mod info`-style detail views."""

    DEFAULT_CSS = """
    InfoModal { align: center middle; }
    InfoModal > Vertical {
        width: 70;
        height: auto;
        max-height: 80%;
        border: thick;
        padding: 1 2;
    }
    InfoModal Horizontal { height: auto; align: center middle; padding-top: 1; }
    """

    BINDINGS = [Binding("escape", "dismiss", "Close")]

    def __init__(self, title: str, body: str) -> None:
        super().__init__()
        self.title_text = title
        self.body = body

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static(f"[b]{self.title_text}[/b]")
            yield Static(self.body)
            with Horizontal():
                yield Button("Close", variant="primary", id="close")

    def on_button_pressed(self, _event: Button.Pressed) -> None:
        self.dismiss(None)
