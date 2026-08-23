from __future__ import annotations

from pathlib import Path
from typing import Any

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, DataTable, Select, Static

from core.models import RemoteVersion, RemoveResult

from ..modals import ConfirmModal, InputField, InputModal
from .base import RefreshableTab


class VersionsTab(RefreshableTab):
    DEFAULT_CSS = """
    VersionsTab #tables { height: 1fr; }
    VersionsTab #tables > Vertical { padding-right: 1; }
    VersionsTab DataTable { height: 1fr; }
    VersionsTab #source-row,
    VersionsTab #actions { height: auto; padding-top: 1; }
    VersionsTab #source-row Select { width: 32; }
    VersionsTab Button { margin-right: 1; }
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._remote: dict[str, RemoteVersion] = {}

    def compose(self) -> ComposeResult:
        with Horizontal(id="tables"):
            with Vertical():
                yield Static("[b]Installed versions[/b]")
                installed: DataTable[str] = DataTable(id="installed", cursor_type="row")
                installed.add_columns("id", "channel", "name", "installed")
                yield installed
            with Vertical():
                yield Static("[b]Remote releases[/b]")
                with Horizontal(id="source-row"):
                    yield Select([], prompt="Source", id="source")
                    yield Button("Load", id="load")
                remote: DataTable[str] = DataTable(id="remote", cursor_type="row")
                remote.add_columns("id", "published", "asset")
                yield remote
        with Horizontal(id="actions"):
            yield Button("Install latest", id="latest")
            yield Button("Install selected", id="install-remote")
            yield Button("Import zip", id="import-zip")
            yield Button("Import directory", id="import-dir")
            yield Button("Remove", id="remove")

    def refresh_from_disk(self) -> None:
        snapshot = self.launcher.snapshot()
        table = self.query_one("#installed", DataTable)
        table.clear()
        for version in snapshot.versions:
            table.add_row(
                version.id,
                version.channel,
                version.display_name,
                version.installed_at,
                key=version.id,
            )
        select = self.query_one("#source", Select)
        previous = None if select.is_blank() else str(select.value)
        names = [name for name, _channel in snapshot.channels]
        select.set_options([(name, name) for name in names])
        selected: str | None = None
        if previous in names:
            select.value = previous
            selected = previous
        elif names:
            select.value = names[0]
            selected = names[0]
        if selected != previous:
            self._remote.clear()
            self.query_one("#remote", DataTable).clear()

    def _source(self) -> str | None:
        select = self.query_one("#source", Select)
        return None if select.is_blank() else str(select.value)

    @staticmethod
    def _selected(table: DataTable) -> str | None:
        if table.row_count == 0:
            return None
        key = table.coordinate_to_cell_key(table.cursor_coordinate).row_key
        return str(key.value) if key is not None else None

    def on_button_pressed(self, event: Button.Pressed) -> None:
        handlers = {
            "load": self._load,
            "latest": self._install_latest,
            "install-remote": self._install_selected,
            "import-zip": self._import_zip,
            "import-dir": self._import_directory,
            "remove": self._remove,
        }
        handler = handlers.get(event.button.id or "")
        if handler is not None:
            handler()

    def _load(self) -> None:
        source = self._source()
        if source is None:
            self.set_status("Select a source first", "warning")
            return
        self.run_operation(
            f"Loading releases from {source}…",
            lambda: self.launcher.remote_versions(source, refresh=True),
            self._remote_loaded,
        )

    def _remote_loaded(self, result: object) -> None:
        assert isinstance(result, list)
        releases = [item for item in result if isinstance(item, RemoteVersion)]
        self._remote = {item.id: item for item in releases}
        table = self.query_one("#remote", DataTable)
        table.clear()
        for release in releases:
            table.add_row(
                release.id,
                release.published_at,
                release.asset_name,
                key=release.id,
            )
        self.set_status(f"Loaded {len(releases)} release(s)", "success")

    def _install_latest(self) -> None:
        source = self._source()
        if source is None:
            self.set_status("Select a source first", "warning")
            return
        self._install_remote(source, "latest")

    def _install_selected(self) -> None:
        source = self._source()
        selected = self._selected(self.query_one("#remote", DataTable))
        if source is None or selected is None:
            self.set_status("Select a source and release first", "warning")
            return
        self._install_remote(source, selected)

    def _install_remote(self, source: str, selector: str) -> None:
        progress = self.progress_reporter(f"Downloading {selector}")
        self.run_operation(
            f"Installing {selector}…",
            lambda: self.launcher.install_remote_version(
                source,
                selector,
                progress=progress,
            ),
            lambda result: self.set_status(f"Installed version {result}", "success"),
            mutates=True,
        )

    def _import_zip(self) -> None:
        self.app.push_screen(
            InputModal(
                "Import version zip",
                [
                    InputField("path", "Zip path", required=True),
                    InputField("id", "Version id (optional)"),
                    InputField("channel", "Channel label", default="local"),
                    InputField("force", "Replace existing? y/N", default="n"),
                ],
            ),
            lambda values: self._import_local(values, directory=False),
        )

    def _import_directory(self) -> None:
        self.app.push_screen(
            InputModal(
                "Import extracted version",
                [
                    InputField("path", "Directory path", required=True),
                    InputField("id", "Version id (optional)"),
                    InputField("channel", "Channel label", default="local"),
                    InputField("force", "Replace existing? y/N", default="n"),
                ],
            ),
            lambda values: self._import_local(values, directory=True),
        )

    def _import_local(self, values: dict[str, str] | None, *, directory: bool) -> None:
        if values is None:
            return
        force = values["force"].lower() in {"1", "true", "y", "yes"}
        source = Path(values["path"])

        def operation() -> str:
            if directory:
                return self.launcher.install_version_directory(
                    source,
                    version_id=values["id"] or None,
                    channel=values["channel"] or "local",
                    force=force,
                )
            return self.launcher.install_version_file(
                source,
                version_id=values["id"] or None,
                channel=values["channel"] or "local",
                force=force,
            )

        self.run_operation(
            "Importing version…",
            operation,
            lambda result: self.set_status(f"Installed version {result}", "success"),
            mutates=True,
        )

    def _remove(self) -> None:
        selected = self._selected(self.query_one("#installed", DataTable))
        if selected is None:
            self.set_status("Select an installed version first", "warning")
            return
        self.app.push_screen(
            ConfirmModal(
                f"Remove version '{selected}' and detach affected instances?",
                confirm_label="Remove",
            ),
            lambda confirmed: self._remove_confirmed(selected, confirmed),
        )

    def _remove_confirmed(self, version_id: str, confirmed: bool | None) -> None:
        if not confirmed:
            return
        self.run_operation(
            f"Removing {version_id}…",
            lambda: self.launcher.remove_version(version_id, force=True),
            self._removed,
            mutates=True,
        )

    def _removed(self, result: object) -> None:
        assert isinstance(result, RemoveResult)
        suffix = (
            "; detached " + ", ".join(result.affected_profiles)
            if result.affected_profiles
            else ""
        )
        self.set_status(f"Removed {result.resource_id}{suffix}", "success")
