from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, DataTable, ListItem, ListView, Static

from core.models import ChannelConfig

from ..modals import ConfirmModal, InputField, InputModal
from .base import RefreshableTab


class ModSourceItem(ListItem):
    def __init__(self, key: str, label: str) -> None:
        super().__init__(Static(label))
        self.source_key = key


class SourcesTab(RefreshableTab):
    DEFAULT_CSS = """
    SourcesTab #main { height: 1fr; }
    SourcesTab #main > Vertical { padding-right: 1; }
    SourcesTab DataTable,
    SourcesTab ListView {
        height: 1fr;
        border: round ansi_blue;
        border-title-color: ansi_yellow;
        border-title-background: ansi_default;
        border-title-style: bold;
    }
    SourcesTab #actions { height: auto; padding-top: 1; }
    SourcesTab Button { margin-right: 1; }
    """

    def compose(self) -> ComposeResult:
        with Horizontal(id="main"):
            with Vertical():
                table: DataTable[str] = DataTable(id="sources", cursor_type="row")
                table.add_columns("name", "provider", "repository", "asset regex")
                table.border_title = " Configured Mod sources "
                yield table
            with Vertical():
                catalog = ListView(id="mod-source-catalog")
                catalog.border_title = " Mod sources "
                yield catalog
        with Horizontal(id="actions"):
            yield Button("Add source", id="add-source", classes="action-primary")
            yield Button("Add custom", id="add-custom", classes="action-accent")
            yield Button("Edit", id="edit")
            yield Button("Remove", id="remove", classes="action-danger")

    def refresh_from_disk(self) -> None:
        table = self.query_one("#sources", DataTable)
        table.clear()
        for name, source in self.launcher.channels():
            if source.kind != "mod":
                continue
            table.add_row(
                name,
                source.provider,
                source.repo,
                source.asset_regex,
                key=name,
            )
        catalog = self.query_one("#mod-source-catalog", ListView)
        catalog.clear()
        for key, preset in self.launcher.channel_presets(kind="mod"):
            catalog.append(
                ModSourceItem(
                    key,
                    f"{key}\n  {preset.description}",
                )
            )

    def _selected_source(self) -> str | None:
        table = self.query_one("#sources", DataTable)
        if table.row_count == 0:
            return None
        key = table.coordinate_to_cell_key(table.cursor_coordinate).row_key
        return str(key.value) if key is not None else None

    def _selected_catalog_source(self) -> str | None:
        item = self.query_one("#mod-source-catalog", ListView).highlighted_child
        return item.source_key if isinstance(item, ModSourceItem) else None

    def on_button_pressed(self, event: Button.Pressed) -> None:
        handlers = {
            "add-source": self._add_catalog_source,
            "add-custom": self._add_custom,
            "edit": self._edit,
            "remove": self._remove,
        }
        handler = handlers.get(event.button.id or "")
        if handler is not None:
            handler()

    def _add_catalog_source(self) -> None:
        source_key = self._selected_catalog_source()
        if source_key is None:
            self.set_status("Select a Mod source first", "warning")
            return
        suggested = source_key.removeprefix("dol-")
        existing = {name for name, _source in self.launcher.channels()}
        if suggested not in existing:
            self._create_source(suggested, preset=source_key)
            return
        self.app.push_screen(
            InputModal(
                f"Add Mod source {source_key}",
                [InputField("name", "Source name", default=f"{suggested}-2")],
            ),
            lambda values: (
                self._create_source(values["name"], preset=source_key)
                if values is not None
                else None
            ),
        )

    def _add_custom(self) -> None:
        self.app.push_screen(
            InputModal(
                "Add custom Mod source",
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
            kind="mod",
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
