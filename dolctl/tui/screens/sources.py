from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, DataTable, ListItem, ListView, Static

from core.models import ChannelConfig

from ..modals import ConfirmModal, InputField, InputModal
from .base import RefreshableTab


class PresetItem(ListItem):
    def __init__(self, key: str, label: str) -> None:
        super().__init__(Static(label))
        self.preset_key = key


class SourcesTab(RefreshableTab):
    DEFAULT_CSS = """
    SourcesTab #main { height: 1fr; }
    SourcesTab #main > Vertical { padding-right: 1; }
    SourcesTab DataTable,
    SourcesTab ListView { height: 1fr; }
    SourcesTab #actions { height: auto; padding-top: 1; }
    SourcesTab Button { margin-right: 1; }
    """

    def compose(self) -> ComposeResult:
        with Horizontal(id="main"):
            with Vertical():
                yield Static("[b]Configured sources[/b]")
                table: DataTable[str] = DataTable(id="sources", cursor_type="row")
                table.add_columns("name", "provider", "repository", "asset regex")
                yield table
            with Vertical():
                yield Static("[b]Built-in presets[/b]")
                yield ListView(id="presets")
        with Horizontal(id="actions"):
            yield Button("Add preset", id="add-preset", variant="primary")
            yield Button("Add custom", id="add-custom")
            yield Button("Edit", id="edit")
            yield Button("Remove", id="remove", variant="error")

    def refresh_from_disk(self) -> None:
        table = self.query_one("#sources", DataTable)
        table.clear()
        for name, source in self.launcher.channels():
            table.add_row(
                name,
                source.provider,
                source.repo,
                source.asset_regex,
                key=name,
            )
        presets = self.query_one("#presets", ListView)
        presets.clear()
        for key, preset in self.launcher.channel_presets():
            presets.append(PresetItem(key, f"{key}\n  {preset.description}"))

    def _selected_source(self) -> str | None:
        table = self.query_one("#sources", DataTable)
        if table.row_count == 0:
            return None
        key = table.coordinate_to_cell_key(table.cursor_coordinate).row_key
        return str(key.value) if key is not None else None

    def _selected_preset(self) -> str | None:
        item = self.query_one("#presets", ListView).highlighted_child
        return item.preset_key if isinstance(item, PresetItem) else None

    def on_button_pressed(self, event: Button.Pressed) -> None:
        handlers = {
            "add-preset": self._add_preset,
            "add-custom": self._add_custom,
            "edit": self._edit,
            "remove": self._remove,
        }
        handler = handlers.get(event.button.id or "")
        if handler is not None:
            handler()

    def _add_preset(self) -> None:
        preset = self._selected_preset()
        if preset is None:
            self.set_status("Select a preset first", "warning")
            return
        suggested = preset.removeprefix("dol-")
        existing = {name for name, _source in self.launcher.channels()}
        if suggested not in existing:
            self._create_source(suggested, preset=preset)
            return
        self.app.push_screen(
            InputModal(
                f"Add preset {preset}",
                [InputField("name", "Source name", default=f"{suggested}-2")],
            ),
            lambda values: (
                self._create_source(values["name"], preset=preset)
                if values is not None
                else None
            ),
        )

    def _add_custom(self) -> None:
        self.app.push_screen(
            InputModal(
                "Add GitHub source",
                [
                    InputField("name", "Source name", required=True),
                    InputField("repo", "Repository (owner/name)", required=True),
                    InputField("regex", "Asset regex", default=r".*\.zip"),
                ],
            ),
            self._custom_from_modal,
        )

    def _custom_from_modal(self, values: dict[str, str] | None) -> None:
        if values is None:
            return
        self._create_source(
            values["name"],
            repo=values["repo"],
            asset_regex=values["regex"],
        )

    def _create_source(self, name: str, **fields: object) -> None:
        self.run_operation(
            f"Adding source {name}…",
            lambda: self.launcher.add_channel(name, **fields),
            self._source_saved,
            mutates=True,
        )

    def _source_saved(self, result: object) -> None:
        assert isinstance(result, ChannelConfig)
        self.set_status(f"Saved source {result.repo}", "success")

    def _edit(self) -> None:
        name = self._selected_source()
        if name is None:
            self.set_status("Select a source first", "warning")
            return
        current = dict(self.launcher.channels())[name]
        self.app.push_screen(
            InputModal(
                f"Edit source {name}",
                [
                    InputField("repo", "Repository", default=current.repo),
                    InputField("regex", "Asset regex", default=current.asset_regex),
                ],
            ),
            lambda values: self._edit_from_modal(name, values),
        )

    def _edit_from_modal(self, name: str, values: dict[str, str] | None) -> None:
        if values is None:
            return
        self.run_operation(
            f"Updating source {name}…",
            lambda: self.launcher.update_channel(
                name,
                repo=values["repo"],
                asset_regex=values["regex"],
            ),
            self._source_saved,
            mutates=True,
        )

    def _remove(self) -> None:
        name = self._selected_source()
        if name is None:
            self.set_status("Select a source first", "warning")
            return
        self.app.push_screen(
            ConfirmModal(f"Remove source '{name}'?", confirm_label="Remove"),
            lambda confirmed: self._remove_confirmed(name, confirmed),
        )

    def _remove_confirmed(self, name: str, confirmed: bool | None) -> None:
        if not confirmed:
            return
        self.run_operation(
            f"Removing source {name}…",
            lambda: self.launcher.remove_channel(name),
            lambda _result: self.set_status(f"Removed source {name}", "success"),
            mutates=True,
        )
