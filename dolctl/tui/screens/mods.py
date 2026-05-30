from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Button, DataTable, Static

from core.mods import add_mod_from_zip, get_mod_info, list_mods, remove_mod
from core.models import DolCtlError
from infra.net import is_url

from ..modals import ConfirmModal, InfoModal, InputField, InputModal
from .base import RefreshableTab


class ModsTab(RefreshableTab):
    DEFAULT_CSS = """
    ModsTab DataTable { height: 1fr; }
    ModsTab #actions { height: auto; padding-top: 1; }
    ModsTab #actions Button { margin-right: 1; }
    """

    def compose(self) -> ComposeResult:
        yield Static("[b]Installed mods[/b]")
        table = DataTable(id="mods-table", cursor_type="row")
        table.add_columns("id", "name", "version", "author", "source")
        yield table
        with Horizontal(id="actions"):
            yield Button("Add (path or URL)", id="btn-add", variant="primary")
            yield Button("Info", id="btn-info")
            yield Button("Remove", id="btn-remove", variant="error")

    def refresh_from_disk(self) -> None:
        table = self.query_one("#mods-table", DataTable)
        table.clear()
        for mod in list_mods(self.root):
            table.add_row(
                mod.id,
                mod.name,
                mod.version,
                mod.author,
                mod.source,
                key=mod.id,
            )

    def _selected(self) -> str | None:
        table = self.query_one("#mods-table", DataTable)
        if table.cursor_row is None or table.row_count == 0:
            return None
        row_key = table.coordinate_to_cell_key(table.cursor_coordinate).row_key
        return row_key.value if row_key else None

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id
        if bid == "btn-add":
            self._add()
        elif bid == "btn-info":
            self._info()
        elif bid == "btn-remove":
            self._remove()

    def _add(self) -> None:
        fields = [
            InputField(
                "path_or_url",
                "Path to .mod.zip or URL",
                placeholder="/abs/path/foo.mod.zip  or  https://...",
                required=True,
            ),
            InputField(
                "mod_id",
                "Override mod id (optional)",
                placeholder="(leave empty to derive from boot.json)",
            ),
            InputField("force", "Force overwrite (y/n)", default="n"),
        ]
        self.app.push_screen(
            InputModal("Add mod", fields),
            self._do_add,
        )

    def _do_add(self, values) -> None:
        if values is None:
            return
        path_or_url = values["path_or_url"]
        force = values["force"].lower() in {"y", "yes", "true", "1"}
        mod_id = values["mod_id"] or None

        def worker() -> None:
            try:
                installed = add_mod_from_zip(
                    self.root, path_or_url, mod_id=mod_id, force=force
                )
            except Exception as exc:  # noqa: BLE001 — surface HTTP / zip errors
                self.app.call_from_thread(self.set_status, f"error: {exc}")
                return
            self.app.call_from_thread(
                self.set_status, f"added mod {installed}"
            )
            self.app.call_from_thread(self.notify_data_changed)

        if is_url(path_or_url):
            self.set_status("downloading mod…")
            self.run_worker(worker, exclusive=True, thread=True)
        else:
            worker()

    def _info(self) -> None:
        mod_id = self._selected()
        if mod_id is None:
            self.set_status("select a mod row first")
            return
        try:
            m = get_mod_info(self.root, mod_id)
        except DolCtlError as exc:
            self.set_status(f"error: {exc}")
            return
        body = (
            f"id:          {m.id}\n"
            f"name:        {m.name}\n"
            f"version:     {m.version}\n"
            f"author:      {m.author}\n"
            f"description: {m.description}\n"
            f"source:      {m.source}\n"
            f"source_ref:  {m.source_ref}\n"
            f"installed:   {m.installed_at}\n"
            f"path:        {m.path}"
        )
        self.app.push_screen(InfoModal(f"Mod: {m.id}", body))

    def _remove(self) -> None:
        mod_id = self._selected()
        if mod_id is None:
            self.set_status("select a mod row first")
            return
        self.app.push_screen(
            ConfirmModal(f"Remove mod '{mod_id}'?", confirm_label="Remove"),
            lambda ok: self._do_remove(mod_id, ok),
        )

    def _do_remove(self, mod_id: str, ok: bool | None) -> None:
        if not ok:
            return
        try:
            remove_mod(self.root, mod_id)
        except DolCtlError as exc:
            self.set_status(f"error: {exc}")
            return
        self.set_status(f"removed mod {mod_id}")
        self.notify_data_changed()
