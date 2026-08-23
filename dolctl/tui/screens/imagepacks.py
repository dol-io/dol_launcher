from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Button, Checkbox, DataTable, Input

from .base import RefreshableTab


class ImagepacksTab(RefreshableTab):
    DEFAULT_CSS = """
    ImagepacksTab DataTable {
        height: 1fr;
        border: round ansi_blue;
        border-title-color: ansi_yellow;
        border-title-background: ansi_default;
        border-title-style: bold;
    }
    ImagepacksTab #actions { height: auto; padding-top: 1; }
    ImagepacksTab #imagepack-id { width: 28; margin-right: 1; }
    ImagepacksTab Checkbox { width: auto; margin-right: 1; }
    ImagepacksTab Button { margin-right: 1; }
    """

    def compose(self) -> ComposeResult:
        table: DataTable[str] = DataTable(id="imagepacks", cursor_type="row")
        table.add_columns("id", "name", "source", "description")
        table.border_title = " Imagepack catalog "
        yield table
        with Horizontal(id="actions"):
            yield Input(placeholder="mod id override", id="imagepack-id")
            yield Checkbox("replace", id="imagepack-force")
            yield Button(
                "Build & install",
                id="install-imagepack",
                classes="action-primary",
            )

    def refresh_from_disk(self) -> None:
        table = self.query_one("#imagepacks", DataTable)
        table.clear()
        for recipe in self.launcher.imagepacks():
            table.add_row(
                recipe.id,
                recipe.name,
                recipe.source_label,
                recipe.description,
                key=recipe.id,
            )

    def _selected(self) -> str | None:
        table = self.query_one("#imagepacks", DataTable)
        if table.row_count == 0:
            return None
        key = table.coordinate_to_cell_key(table.cursor_coordinate).row_key
        return str(key.value) if key is not None else None

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "imagepack-id":
            self._install()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "install-imagepack":
            self._install()

    def _install(self) -> None:
        recipe_id = self._selected()
        if recipe_id is None:
            self.set_status("Select an imagepack first", "warning")
            return
        mod_id = self.query_one("#imagepack-id", Input).value.strip() or None
        force = self.query_one("#imagepack-force", Checkbox).value
        progress = self.progress_reporter("Downloading imagepack")
        self.run_operation(
            f"Building {recipe_id}…",
            lambda: self.launcher.install_imagepack(
                recipe_id,
                mod_id=mod_id,
                force=force,
                progress=progress,
            ),
            self._installed,
            mutates=True,
        )

    def _installed(self, result: object) -> None:
        assert isinstance(result, str)
        self.query_one("#imagepack-id", Input).value = ""
        self.query_one("#imagepack-force", Checkbox).value = False
        self.set_status(
            f"Installed imagepack as Mod {result}; enable it in an instance",
            "success",
        )
