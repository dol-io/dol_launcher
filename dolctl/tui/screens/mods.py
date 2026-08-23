from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Button, Checkbox, DataTable, Input, Select

from core.models import Mod, RemoveResult

from ..modals import ConfirmModal, InfoModal
from .base import RefreshableTab


class ModsTab(RefreshableTab):
    DEFAULT_CSS = """
    ModsTab #import { height: auto; padding-bottom: 1; }
    ModsTab #remote-import { height: auto; padding-bottom: 1; }
    ModsTab #source { width: 1fr; margin-right: 1; }
    ModsTab #mod-source { width: 1fr; max-width: 48; margin-right: 1; }
    ModsTab #mod-id { width: 24; margin-right: 1; }
    ModsTab Checkbox { width: auto; margin-right: 1; }
    ModsTab DataTable {
        height: 1fr;
        border: round ansi_blue;
        border-title-color: ansi_yellow;
        border-title-background: ansi_default;
        border-title-style: bold;
    }
    ModsTab #actions { height: auto; padding-top: 1; }
    ModsTab Button { margin-right: 1; }
    """

    def compose(self) -> ComposeResult:
        with Horizontal(id="import"):
            yield Input(
                placeholder="Path or https:// URL to a ModLoader zip",
                id="source",
            )
            yield Input(placeholder="id override", id="mod-id")
            yield Checkbox("replace", id="force")
            yield Button("Import", id="import-button", classes="action-primary")
        with Horizontal(id="remote-import"):
            yield Select([], prompt="Remote Mod source", id="mod-source")
            yield Button(
                "Install latest",
                id="install-remote",
                classes="action-accent",
            )
        table: DataTable[str] = DataTable(id="mods", cursor_type="row")
        table.add_columns("id", "name", "version", "author", "source")
        table.border_title = " Mod library "
        yield table
        with Horizontal(id="actions"):
            yield Button("Info", id="info", classes="action-accent")
            yield Button("Remove", id="remove", classes="action-danger")

    def refresh_from_disk(self) -> None:
        snapshot = self.launcher.snapshot()
        table = self.query_one("#mods", DataTable)
        table.clear()
        for mod in snapshot.mods:
            table.add_row(
                mod.id,
                mod.name,
                mod.version,
                mod.author,
                mod.source,
                key=mod.id,
            )
        select = self.query_one("#mod-source", Select)
        previous = None if select.is_blank() else str(select.value)
        names = [
            name for name, channel in snapshot.channels if channel.kind == "mod"
        ]
        select.set_options([(name, name) for name in names])
        if previous in names:
            select.value = previous
        elif names:
            select.value = names[0]

    def _selected(self) -> str | None:
        table = self.query_one("#mods", DataTable)
        if table.row_count == 0:
            return None
        key = table.coordinate_to_cell_key(table.cursor_coordinate).row_key
        return str(key.value) if key is not None else None

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id in {"source", "mod-id"}:
            self._import()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "import-button":
            self._import()
        elif event.button.id == "install-remote":
            self._install_remote()
        elif event.button.id == "info":
            self._info()
        elif event.button.id == "remove":
            self._remove()

    def _import(self) -> None:
        source = self.query_one("#source", Input).value.strip()
        if not source:
            self.set_status("Enter a mod path or URL", "warning")
            return
        mod_id = self.query_one("#mod-id", Input).value.strip() or None
        force = self.query_one("#force", Checkbox).value
        progress = self.progress_reporter("Downloading mod")
        self.run_operation(
            "Importing mod…",
            lambda: self.launcher.install_mod(
                source,
                mod_id=mod_id,
                force=force,
                progress=progress,
            ),
            self._imported,
            mutates=True,
        )

    def _imported(self, result: object) -> None:
        assert isinstance(result, str)
        self.query_one("#source", Input).value = ""
        self.query_one("#mod-id", Input).value = ""
        self.query_one("#force", Checkbox).value = False
        self.set_status(f"Imported mod {result}", "success")

    def _install_remote(self) -> None:
        select = self.query_one("#mod-source", Select)
        if select.is_blank():
            self.set_status("Add and select a Mod source first", "warning")
            return
        channel = str(select.value)
        mod_id = self.query_one("#mod-id", Input).value.strip() or None
        force = self.query_one("#force", Checkbox).value
        progress = self.progress_reporter("Downloading mod")
        self.run_operation(
            f"Installing latest Mod from {channel}…",
            lambda: self.launcher.install_remote_mod(
                channel,
                mod_id=mod_id,
                force=force,
                progress=progress,
            ),
            self._imported,
            mutates=True,
        )

    def _info(self) -> None:
        mod_id = self._selected()
        if mod_id is None:
            self.set_status("Select a mod first", "warning")
            return
        mod = self.launcher.mod(mod_id)
        assert isinstance(mod, Mod)
        self.app.push_screen(
            InfoModal(
                f"Mod: {mod.id}",
                f"name:        {mod.name}\n"
                f"version:     {mod.version}\n"
                f"author:      {mod.author}\n"
                f"description: {mod.description}\n"
                f"source:      {mod.source_ref}\n"
                f"sha256:      {mod.sha256}",
            )
        )

    def _remove(self) -> None:
        mod_id = self._selected()
        if mod_id is None:
            self.set_status("Select a mod first", "warning")
            return
        self.app.push_screen(
            ConfirmModal(
                f"Remove mod '{mod_id}' from the library and all instances?",
                confirm_label="Remove",
            ),
            lambda confirmed: self._remove_confirmed(mod_id, confirmed),
        )

    def _remove_confirmed(self, mod_id: str, confirmed: bool | None) -> None:
        if not confirmed:
            return
        self.run_operation(
            f"Removing {mod_id}…",
            lambda: self.launcher.remove_mod(mod_id),
            self._removed,
            mutates=True,
        )

    def _removed(self, result: object) -> None:
        assert isinstance(result, RemoveResult)
        suffix = (
            "; updated " + ", ".join(result.affected_profiles)
            if result.affected_profiles
            else ""
        )
        self.set_status(f"Removed {result.resource_id}{suffix}", "success")
