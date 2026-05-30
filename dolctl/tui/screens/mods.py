from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Button, Checkbox, DataTable, Input, Static

from core.mods import add_mod_from_zip, get_mod_info, list_mods, remove_mod
from core.models import DolCtlError
from infra.net import is_url

from ..modals import ConfirmModal, InfoModal
from .base import RefreshableTab, make_progress_reporter


class ModsTab(RefreshableTab):
    DEFAULT_CSS = """
    ModsTab DataTable { height: 1fr; }
    ModsTab #add-row { height: auto; padding-bottom: 1; }
    ModsTab #add-row Input { width: 1fr; margin-right: 1; }
    ModsTab #add-row #mod-id { width: 24; }
    ModsTab #add-row Checkbox { width: auto; margin-right: 1; }
    ModsTab #add-row Button { width: auto; }
    ModsTab #actions { height: auto; padding-top: 1; }
    ModsTab #actions Button { margin-right: 1; }
    """

    def compose(self) -> ComposeResult:
        yield Static("[b]Installed mods[/b]")
        # Inline add form — typing the path/URL and pressing Enter (or
        # clicking Add) imports the mod without a modal round-trip.
        with Horizontal(id="add-row"):
            yield Input(
                placeholder="path to .mod.zip or https://… (Enter to add)",
                id="add-input",
            )
            yield Input(placeholder="override id (optional)", id="mod-id")
            yield Checkbox("force", id="force")
            yield Button("Add", id="btn-add", variant="primary")
        table = DataTable(id="mods-table", cursor_type="row")
        table.add_columns("id", "name", "version", "author", "source")
        yield table
        with Horizontal(id="actions"):
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

    def on_input_submitted(self, event: Input.Submitted) -> None:
        # Pressing Enter inside the path/URL field triggers Add.
        if event.input.id in {"add-input", "mod-id"}:
            self._add()

    def _add(self) -> None:
        path_or_url = self.query_one("#add-input", Input).value.strip()
        if not path_or_url:
            self.set_status("type a path or URL to add", "warn")
            return
        mod_id = self.query_one("#mod-id", Input).value.strip() or None
        force = self.query_one("#force", Checkbox).value

        url_download = is_url(path_or_url)
        progress = (
            make_progress_reporter(self.app, self.set_status, "downloading mod")
            if url_download
            else None
        )

        def worker() -> None:
            try:
                installed = add_mod_from_zip(
                    self.root, path_or_url, mod_id=mod_id, force=force, progress=progress
                )
            except Exception as exc:  # noqa: BLE001 — surface HTTP / zip errors
                self.app.call_from_thread(self.set_status, f"error: {exc}", "error")
                return
            self.app.call_from_thread(
                self.set_status, f"added mod {installed}", "success")
            self.app.call_from_thread(self._reset_add_form)
            self.app.call_from_thread(self.notify_data_changed)

        if url_download:
            self.set_status("downloading mod…")
        else:
            self.set_status("importing mod…")
        # Always offload to a worker thread — even local-file imports
        # touch the filesystem (zip read + flatten + copy) and the worker
        # body uses ``call_from_thread`` for UI updates, which would
        # error out if it ran on the UI thread.
        self.run_worker(worker, exclusive=True, thread=True)

    def _reset_add_form(self) -> None:
        self.query_one("#add-input", Input).value = ""
        self.query_one("#mod-id", Input).value = ""
        self.query_one("#force", Checkbox).value = False

    def _info(self) -> None:
        mod_id = self._selected()
        if mod_id is None:
            self.set_status("select a mod row first", "warn")
            return
        try:
            m = get_mod_info(self.root, mod_id)
        except DolCtlError as exc:
            self.set_status(f"error: {exc}", "error")
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
            self.set_status("select a mod row first", "warn")
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
            self.set_status(f"error: {exc}", "error")
            return
        self.set_status(f"removed mod {mod_id}", "success")
        self.notify_data_changed()
