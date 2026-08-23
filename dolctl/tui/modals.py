from __future__ import annotations

from dataclasses import dataclass
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
        width: 64; height: auto; border: thick; padding: 1 2;
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
                yield Button(self.confirm_label, id="confirm", variant="primary")
                yield Button("Cancel", id="cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "confirm")


@dataclass(frozen=True, slots=True)
class InputField:
    key: str
    label: str
    default: str = ""
    placeholder: str = ""
    required: bool = False


class InputModal(ModalScreen[dict[str, str] | None]):
    DEFAULT_CSS = """
    InputModal { align: center middle; }
    InputModal > Vertical {
        width: 72; height: auto; border: thick; padding: 1 2;
    }
    InputModal Label { padding-top: 1; }
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
        self.modal_title = title
        self.fields = tuple(fields)
        self.validator = validator

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static(f"[b]{self.modal_title}[/b]")
            for field in self.fields:
                yield Label(field.label)
                yield Input(
                    value=field.default,
                    placeholder=field.placeholder,
                    id=f"field-{field.key}",
                )
            yield Static("", id="error")
            with Horizontal():
                yield Button("OK", id="confirm", variant="primary")
                yield Button("Cancel", id="cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel":
            self.dismiss(None)
            return
        values = {
            field.key: self.query_one(f"#field-{field.key}", Input).value.strip()
            for field in self.fields
        }
        missing = next(
            (
                field.label
                for field in self.fields
                if field.required and not values[field.key]
            ),
            None,
        )
        if missing:
            self.query_one("#error", Static).update(f"[red]{missing} is required[/red]")
            return
        if self.validator is not None:
            error = self.validator(values)
            if error:
                self.query_one("#error", Static).update(f"[red]{error}[/red]")
                return
        self.dismiss(values)


class InfoModal(ModalScreen[None]):
    DEFAULT_CSS = """
    InfoModal { align: center middle; }
    InfoModal > Vertical {
        width: 72; height: auto; max-height: 85%; border: thick; padding: 1 2;
    }
    InfoModal Horizontal { height: auto; align: center middle; padding-top: 1; }
    """
    BINDINGS = [Binding("escape", "dismiss", "Close")]

    def __init__(self, title: str, body: str) -> None:
        super().__init__()
        self.modal_title = title
        self.body = body

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static(f"[b]{self.modal_title}[/b]")
            yield Static(self.body)
            with Horizontal():
                yield Button("Close", id="close", variant="primary")

    def on_button_pressed(self, _event: Button.Pressed) -> None:
        self.dismiss(None)
