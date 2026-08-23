from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Sequence

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, DataTable, Input, Label, Select, Static

from core.models import Mod, Profile


class ConfirmModal(ModalScreen[bool]):
    DEFAULT_CSS = """
    ConfirmModal { align: center middle; }
    ConfirmModal > Vertical {
        width: 64; height: auto; border: round ansi_blue; padding: 1 2;
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
        with Vertical() as card:
            card.border_title = Text(" Confirm ")
            yield Static(self.prompt)
            with Horizontal():
                confirm_class = (
                    "action-danger"
                    if self.confirm_label in {"Delete", "Remove"}
                    else "action-primary"
                )
                yield Button(
                    self.confirm_label,
                    id="confirm",
                    classes=confirm_class,
                )
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
        width: 72; height: auto; border: round ansi_blue; padding: 1 2;
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
        with Vertical() as card:
            card.border_title = Text(f" {self.modal_title} ")
            for field in self.fields:
                yield Label(field.label)
                yield Input(
                    value=field.default,
                    placeholder=field.placeholder,
                    id=f"field-{field.key}",
                )
            yield Static("", id="error", classes="form-error", markup=False)
            with Horizontal():
                yield Button("OK", id="confirm", classes="action-primary")
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
            self.query_one("#error", Static).update(f"Error: {missing} is required")
            return
        if self.validator is not None:
            error = self.validator(values)
            if error:
                self.query_one("#error", Static).update(f"Error: {error}")
                return
        self.dismiss(values)


class InfoModal(ModalScreen[None]):
    DEFAULT_CSS = """
    InfoModal { align: center middle; }
    InfoModal > Vertical {
        width: 72; height: auto; max-height: 85%;
        border: round ansi_blue; padding: 1 2;
    }
    InfoModal Horizontal { height: auto; align: center middle; padding-top: 1; }
    """
    BINDINGS = [Binding("escape", "dismiss", "Close")]

    def __init__(self, title: str, body: str) -> None:
        super().__init__()
        self.modal_title = title
        self.body = body

    def compose(self) -> ComposeResult:
        with Vertical() as card:
            card.border_title = Text(f" {self.modal_title} ")
            yield Static(self.body, markup=False)
            with Horizontal():
                yield Button("Close", id="close", classes="action-accent")

    def on_button_pressed(self, _event: Button.Pressed) -> None:
        self.dismiss(None)


@dataclass(frozen=True, slots=True)
class CreateInstanceValues:
    name: str
    version_id: str | None


class CreateInstanceModal(ModalScreen[CreateInstanceValues | None]):
    DEFAULT_CSS = """
    CreateInstanceModal { align: center middle; }
    CreateInstanceModal > Vertical {
        width: 68; height: auto; border: round ansi_blue; padding: 1 2;
    }
    CreateInstanceModal Label { padding-top: 1; }
    CreateInstanceModal Horizontal {
        height: auto; align: center middle; padding-top: 1;
    }
    CreateInstanceModal Button { margin: 0 1; }
    """
    BINDINGS = [Binding("escape", "dismiss(None)", "Cancel")]

    def __init__(self, version_ids: Sequence[str]) -> None:
        super().__init__()
        self.version_ids = tuple(version_ids)

    def compose(self) -> ComposeResult:
        with Vertical() as card:
            card.border_title = Text(" Create instance ")
            yield Label("Name")
            yield Input(placeholder="instance name", id="instance-name")
            yield Label("Game version")
            yield Select(
                [(version_id, version_id) for version_id in self.version_ids],
                prompt="No version yet",
                id="instance-version",
            )
            yield Static(
                "",
                id="instance-error",
                classes="form-error",
                markup=False,
            )
            with Horizontal():
                yield Button(
                    "Create",
                    id="instance-create",
                    classes="action-primary",
                )
                yield Button("Cancel", id="instance-cancel")

    def on_mount(self) -> None:
        self.query_one("#instance-name", Input).focus()

    def on_input_submitted(self, _event: Input.Submitted) -> None:
        self._submit()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "instance-cancel":
            self.dismiss(None)
        elif event.button.id == "instance-create":
            self._submit()

    def _submit(self) -> None:
        name = self.query_one("#instance-name", Input).value.strip()
        if not name:
            self.query_one("#instance-error", Static).update("Error: Name is required")
            return
        version_select = self.query_one("#instance-version", Select)
        version_id = None if version_select.is_blank() else str(version_select.value)
        self.dismiss(CreateInstanceValues(name, version_id))


@dataclass(frozen=True, slots=True)
class InstanceSettings:
    version_id: str | None
    port: int | None
    open_browser: bool | None


class InstanceSettingsModal(ModalScreen[InstanceSettings | None]):
    DEFAULT_CSS = """
    InstanceSettingsModal { align: center middle; }
    InstanceSettingsModal > Vertical {
        width: 68; height: auto; border: round ansi_blue; padding: 1 2;
    }
    InstanceSettingsModal Label { padding-top: 1; }
    InstanceSettingsModal Horizontal {
        height: auto; align: center middle; padding-top: 1;
    }
    InstanceSettingsModal Button { margin: 0 1; }
    """
    BINDINGS = [Binding("escape", "dismiss(None)", "Cancel")]

    def __init__(self, profile: Profile, version_ids: Sequence[str]) -> None:
        super().__init__()
        self.profile = profile
        available = list(version_ids)
        if profile.version_id and profile.version_id not in available:
            available.append(profile.version_id)
        self.version_ids = tuple(available)

    def compose(self) -> ComposeResult:
        browser_value = (
            "default"
            if self.profile.open_browser is None
            else ("open" if self.profile.open_browser else "closed")
        )
        version_value = (
            self.profile.version_id if self.profile.version_id else Select.NULL
        )
        with Vertical() as card:
            card.border_title = Text(f" Configure {self.profile.name} ")
            yield Label("Game version")
            yield Select(
                [(version_id, version_id) for version_id in self.version_ids],
                prompt="No version selected",
                value=version_value,
                id="settings-version",
            )
            yield Label("Port (empty uses the global default)")
            yield Input(
                value=str(self.profile.port) if self.profile.port is not None else "",
                placeholder="global default",
                id="settings-port",
            )
            yield Label("Open browser after launch")
            yield Select(
                [
                    ("Use global setting", "default"),
                    ("Open browser", "open"),
                    ("Do not open browser", "closed"),
                ],
                value=browser_value,
                allow_blank=False,
                id="settings-browser",
            )
            yield Static(
                "",
                id="settings-error",
                classes="form-error",
                markup=False,
            )
            with Horizontal():
                yield Button("Save", id="settings-save", classes="action-primary")
                yield Button("Cancel", id="settings-cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "settings-cancel":
            self.dismiss(None)
        elif event.button.id == "settings-save":
            self._submit()

    def _submit(self) -> None:
        port_text = self.query_one("#settings-port", Input).value.strip()
        try:
            port = int(port_text) if port_text else None
        except ValueError:
            self.query_one("#settings-error", Static).update(
                "Error: Port must be a number"
            )
            return
        if port is not None and not 1 <= port <= 65535:
            self.query_one("#settings-error", Static).update(
                "Error: Port must be between 1 and 65535"
            )
            return
        version_select = self.query_one("#settings-version", Select)
        version_id = None if version_select.is_blank() else str(version_select.value)
        browser_value = str(self.query_one("#settings-browser", Select).value)
        browser = None if browser_value == "default" else browser_value == "open"
        self.dismiss(InstanceSettings(version_id, port, browser))


class ModManagerModal(ModalScreen[list[str] | None]):
    DEFAULT_CSS = """
    ModManagerModal { align: center middle; }
    ModManagerModal > Vertical {
        width: 90%; height: 85%; border: round ansi_blue; padding: 1 2;
    }
    ModManagerModal DataTable {
        height: 1fr;
        border: round ansi_blue;
    }
    ModManagerModal Horizontal { height: auto; padding-top: 1; }
    ModManagerModal Button { margin-right: 1; }
    ModManagerModal #mod-manager-hint { height: auto; }
    ModManagerModal #mod-manager-error { height: auto; }
    """
    BINDINGS = [
        Binding("escape", "dismiss(None)", "Cancel"),
        Binding("space", "toggle_mod", "Toggle", show=False),
        Binding("plus", "move(-1)", "Move up", show=False),
        Binding("minus", "move(1)", "Move down", show=False),
    ]

    def __init__(self, profile: Profile, mods: Sequence[Mod]) -> None:
        super().__init__()
        self.profile = profile
        self._mods = {mod.id: mod for mod in mods}
        self._order = list(profile.mod_order)
        self._all_ids = list(profile.mod_order)
        self._all_ids.extend(mod.id for mod in mods if mod.id not in self._all_ids)

    def compose(self) -> ComposeResult:
        with Vertical() as card:
            card.border_title = Text(f" Mods for {self.profile.name} ")
            yield Static(
                "Space toggles a mod. + / - changes the load order.",
                id="mod-manager-hint",
                classes="hint",
                markup=False,
            )
            table: DataTable[str] = DataTable(id="mod-manager-table", cursor_type="row")
            table.add_columns("on", "order", "id", "name", "version")
            yield table
            yield Static(
                "",
                id="mod-manager-error",
                classes="form-error",
                markup=False,
            )
            with Horizontal():
                yield Button(
                    "Toggle",
                    id="mod-manager-toggle",
                    classes="action-accent",
                )
                yield Button("Move up", id="mod-manager-up")
                yield Button("Move down", id="mod-manager-down")
                yield Button(
                    "Save",
                    id="mod-manager-save",
                    classes="action-primary",
                )
                yield Button("Cancel", id="mod-manager-cancel")

    def on_mount(self) -> None:
        self._render_rows()
        self.query_one("#mod-manager-table", DataTable).focus()

    def _row_ids(self) -> list[str]:
        return [
            *self._order,
            *[item for item in self._all_ids if item not in self._order],
        ]

    def _render_rows(self, selected: str | None = None) -> None:
        table = self.query_one("#mod-manager-table", DataTable)
        table.clear()
        row_ids = self._row_ids()
        for mod_id in row_ids:
            mod = self._mods.get(mod_id)
            enabled = mod_id in self._order
            table.add_row(
                "yes" if enabled else "",
                str(self._order.index(mod_id) + 1) if enabled else "",
                mod_id,
                mod.name if mod is not None else "(missing)",
                mod.version if mod is not None else "",
                key=mod_id,
            )
        if selected in row_ids:
            table.move_cursor(row=row_ids.index(selected))

    def _selected_mod(self) -> str | None:
        table = self.query_one("#mod-manager-table", DataTable)
        if table.row_count == 0:
            return None
        key = table.coordinate_to_cell_key(table.cursor_coordinate).row_key
        return str(key.value) if key is not None else None

    def _show_error(self, message: str = "") -> None:
        self.query_one("#mod-manager-error", Static).update(
            f"Error: {message}" if message else ""
        )

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        if event.data_table.id == "mod-manager-table":
            self.action_toggle_mod()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        handlers = {
            "mod-manager-toggle": self.action_toggle_mod,
            "mod-manager-up": lambda: self.action_move(-1),
            "mod-manager-down": lambda: self.action_move(1),
            "mod-manager-save": lambda: self.dismiss(list(self._order)),
            "mod-manager-cancel": lambda: self.dismiss(None),
        }
        handler = handlers.get(event.button.id or "")
        if handler is not None:
            handler()

    def action_toggle_mod(self) -> None:
        mod_id = self._selected_mod()
        if mod_id is None:
            return
        if mod_id in self._order:
            self._order.remove(mod_id)
        elif mod_id not in self._mods:
            self._show_error(f"{mod_id} is not installed")
            return
        else:
            self._order.append(mod_id)
        self._show_error()
        self._render_rows(mod_id)

    def action_move(self, delta: int) -> None:
        mod_id = self._selected_mod()
        if mod_id is None:
            return
        if mod_id not in self._order:
            self._show_error("Only enabled mods have a load order")
            return
        old_index = self._order.index(mod_id)
        new_index = max(0, min(len(self._order) - 1, old_index + delta))
        if old_index == new_index:
            return
        self._order.insert(new_index, self._order.pop(old_index))
        self._show_error()
        self._render_rows(mod_id)
