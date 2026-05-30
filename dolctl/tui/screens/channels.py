from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, DataTable, ListItem, ListView, Static

from core.channel_presets import PRESETS
from core.channels import add_channel, get_channel, list_channels, remove_channel, set_channel_fields
from core.models import DolCtlError

from ..modals import ConfirmModal, InputField, InputModal
from .base import RefreshableTab


class PresetItem(ListItem):
    """ListItem that remembers which preset key it represents.

    We can't use widget ``id`` for this because ``refresh_from_disk``
    re-populates the ListView, and Textual's clear() is async — adding
    items with the same id during the same tick raises DuplicateIds.
    """

    def __init__(self, preset_key: str, label: str) -> None:
        super().__init__(Static(label))
        self.preset_key = preset_key


class ChannelsTab(RefreshableTab):
    DEFAULT_CSS = """
    ChannelsTab #cols { height: 1fr; }
    ChannelsTab #cols > Vertical { padding-right: 1; }
    ChannelsTab DataTable { height: 1fr; }
    ChannelsTab ListView { height: 1fr; }
    ChannelsTab #actions { height: auto; padding-top: 1; }
    ChannelsTab #actions Button { margin-right: 1; }
    """

    def compose(self) -> ComposeResult:
        with Horizontal(id="cols"):
            with Vertical():
                yield Static("[b]Configured channels[/b]")
                table = DataTable(id="channels-table", cursor_type="row")
                table.add_columns("name", "provider", "repo", "asset_regex")
                yield table
            with Vertical():
                yield Static("[b]Available presets[/b]")
                yield ListView(id="presets-list")
        with Horizontal(id="actions"):
            yield Button("Add (preset)", id="btn-add-preset")
            yield Button("Add (custom)", id="btn-add-custom")
            yield Button("Edit", id="btn-edit")
            yield Button("Remove", id="btn-remove", variant="error")

    def refresh_from_disk(self) -> None:
        table = self.query_one("#channels-table", DataTable)
        table.clear()
        for name, cfg in list_channels(self.root):
            table.add_row(name, cfg.provider, cfg.repo, cfg.asset_regex, key=name)
        presets = self.query_one("#presets-list", ListView)
        presets.clear()
        for key, preset in sorted(PRESETS.items()):
            description = f"{key}  ({preset.provider}: {preset.repo})"
            presets.append(PresetItem(key, description))

    # ----- helpers ------------------------------------------------------

    def _selected_channel(self) -> str | None:
        table = self.query_one("#channels-table", DataTable)
        if table.cursor_row is None or table.row_count == 0:
            return None
        row_key = table.coordinate_to_cell_key(table.cursor_coordinate).row_key
        return row_key.value if row_key else None

    def _selected_preset(self) -> str | None:
        listview = self.query_one("#presets-list", ListView)
        item = listview.highlighted_child
        if isinstance(item, PresetItem):
            return item.preset_key
        return None

    # ----- button handlers ---------------------------------------------

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id
        if bid == "btn-add-preset":
            self._add_preset()
        elif bid == "btn-add-custom":
            self._add_custom()
        elif bid == "btn-edit":
            self._edit_selected()
        elif bid == "btn-remove":
            self._remove_selected()

    def _add_preset(self) -> None:
        preset_key = self._selected_preset()
        if preset_key is None:
            self.set_status("select a preset on the right first", "warn")
            return
        fields = [
            InputField(
                "name",
                "Channel name",
                placeholder="e.g. vanilla",
                default=preset_key.split("-", 1)[-1],
                required=True,
            ),
        ]
        self.app.push_screen(
            InputModal(f"Add channel from preset: {preset_key}", fields),
            lambda values: self._do_add_preset(preset_key, values),
        )

    def _do_add_preset(self, preset_key: str, values) -> None:
        if values is None:
            return
        try:
            add_channel(self.root, values["name"], preset=preset_key)
        except DolCtlError as exc:
            self.set_status(f"error: {exc}", "error")
            return
        self.set_status(f"added channel {values['name']} (preset {preset_key})", "success")
        self.notify_data_changed()

    def _add_custom(self) -> None:
        fields = [
            InputField("name", "Channel name", required=True),
            InputField("provider", "Provider", default="github", required=True),
            InputField("repo", "Repo (owner/name)", required=True),
            InputField(
                "asset_regex", "Asset regex", default=r".*\.zip$", required=False
            ),
        ]
        self.app.push_screen(
            InputModal("Add custom channel", fields),
            self._do_add_custom,
        )

    def _do_add_custom(self, values) -> None:
        if values is None:
            return
        try:
            add_channel(
                self.root,
                values["name"],
                provider=values["provider"],
                repo=values["repo"],
                asset_regex=values["asset_regex"] or None,
            )
        except DolCtlError as exc:
            self.set_status(f"error: {exc}", "error")
            return
        self.set_status(f"added channel {values['name']}", "success")
        self.notify_data_changed()

    def _edit_selected(self) -> None:
        name = self._selected_channel()
        if name is None:
            self.set_status("select a channel row first", "warn")
            return
        try:
            cfg = get_channel(self.root, name)
        except DolCtlError as exc:
            self.set_status(f"error: {exc}", "error")
            return
        fields = [
            InputField("provider", "Provider", default=cfg.provider, required=True),
            InputField("repo", "Repo", default=cfg.repo, required=True),
            InputField("asset_regex", "Asset regex", default=cfg.asset_regex),
        ]
        self.app.push_screen(
            InputModal(f"Edit channel: {name}", fields),
            lambda values: self._do_edit(name, values),
        )

    def _do_edit(self, name: str, values) -> None:
        if values is None:
            return
        try:
            set_channel_fields(
                self.root,
                name,
                provider=values["provider"],
                repo=values["repo"],
                asset_regex=values["asset_regex"] or None,
            )
        except DolCtlError as exc:
            self.set_status(f"error: {exc}", "error")
            return
        self.set_status(f"updated channel {name}", "success")
        self.notify_data_changed()

    def _remove_selected(self) -> None:
        name = self._selected_channel()
        if name is None:
            self.set_status("select a channel row first", "warn")
            return
        self.app.push_screen(
            ConfirmModal(f"Remove channel '{name}'?", confirm_label="Remove"),
            lambda ok: self._do_remove(name, ok),
        )

    def _do_remove(self, name: str, ok: bool | None) -> None:
        if not ok:
            return
        try:
            remove_channel(self.root, name)
        except DolCtlError as exc:
            self.set_status(f"error: {exc}", "error")
            return
        self.set_status(f"removed channel {name}", "success")
        self.notify_data_changed()
