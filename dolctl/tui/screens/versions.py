from __future__ import annotations

from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, DataTable, Select, Static

from core.models import DolCtlError
from core.profiles import set_profile_version
from core.root import load_config, load_state
from core.versions import (
    install_from_dir,
    install_from_file,
    install_from_remote,
    list_installed,
    list_remote_versions,
    remove_version,
)

from ..modals import ConfirmModal, InputField, InputModal
from .base import RefreshableTab, make_progress_reporter


class VersionsTab(RefreshableTab):
    DEFAULT_CSS = """
    VersionsTab #cols { height: 1fr; }
    VersionsTab #cols > Vertical { padding-right: 1; }
    VersionsTab DataTable { height: 1fr; }
    VersionsTab #channel-row { height: auto; padding: 0 0 1 0; }
    VersionsTab #channel-row Select { width: 30; }
    VersionsTab #channel-row Button { margin-left: 1; }
    VersionsTab #actions { height: auto; padding-top: 1; }
    VersionsTab #actions Button { margin-right: 1; }
    """

    def compose(self) -> ComposeResult:
        with Horizontal(id="cols"):
            with Vertical():
                yield Static("[b]Installed versions[/b]")
                table = DataTable(id="installed-table", cursor_type="row")
                table.add_columns("id", "channel", "installed_at", "entry")
                yield table
            with Vertical():
                yield Static("[b]Remote versions[/b]")
                with Horizontal(id="channel-row"):
                    yield Select([], id="channel-select", prompt="(pick channel)")
                    yield Button("Refresh", id="btn-refresh-remote")
                remote = DataTable(id="remote-table", cursor_type="row")
                remote.add_columns("id", "published_at", "asset")
                yield remote
        with Horizontal(id="actions"):
            yield Button("Install latest", id="btn-install-latest", variant="primary")
            yield Button("Install selected", id="btn-install-remote")
            yield Button("Install local zip", id="btn-install-zip")
            yield Button("Install local dir", id="btn-install-dir")
            yield Button("Use", id="btn-use")
            yield Button("Remove", id="btn-remove", variant="error")

    def refresh_from_disk(self) -> None:
        # Installed
        table = self.query_one("#installed-table", DataTable)
        table.clear()
        for v in list_installed(self.root):
            table.add_row(v.id, v.channel, v.installed_at, v.entry, key=v.id)
        # Channel options
        config = load_config(self.root)
        select = self.query_one("#channel-select", Select)
        options = [(name, name) for name in sorted(config.channels)]
        select.set_options(options)

    # ----- helpers ------------------------------------------------------

    def _selected_installed(self) -> str | None:
        table = self.query_one("#installed-table", DataTable)
        if table.row_count == 0:
            return None
        row_key = table.coordinate_to_cell_key(table.cursor_coordinate).row_key
        return row_key.value if row_key else None

    def _selected_remote(self) -> str | None:
        table = self.query_one("#remote-table", DataTable)
        if table.row_count == 0:
            return None
        row_key = table.coordinate_to_cell_key(table.cursor_coordinate).row_key
        return row_key.value if row_key else None

    def _selected_channel(self) -> str | None:
        select = self.query_one("#channel-select", Select)
        if select.is_blank():
            return None
        return str(select.value)

    # ----- handlers -----------------------------------------------------

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id
        if bid == "btn-refresh-remote":
            self._refresh_remote()
        elif bid == "btn-install-zip":
            self._install_zip()
        elif bid == "btn-install-dir":
            self._install_dir()
        elif bid == "btn-install-remote":
            self._install_remote()
        elif bid == "btn-install-latest":
            self._install_latest()
        elif bid == "btn-use":
            self._use_selected()
        elif bid == "btn-remove":
            self._remove_selected()

    def on_select_changed(self, event: Select.Changed) -> None:
        # Auto-refresh the remote list when the user picks a channel —
        # otherwise the flow needs four steps (pick → Refresh → row → Install)
        # and the second step is non-obvious.
        if event.select.id != "channel-select":
            return
        if event.value == Select.NULL:
            return
        # Skip programmatic resets posted by set_options(...). The widget's
        # live value matches event.value only when the user actually
        # changed the selection.
        if event.select.value != event.value:
            return
        self._refresh_remote()

    def _refresh_remote(self) -> None:
        channel = self._selected_channel()
        if channel is None:
            self.set_status("pick a channel first", "warn")
            return
        self.set_status(f"fetching remote versions ({channel})…")

        def worker() -> None:
            try:
                versions = list_remote_versions(self.root, channel, refresh=True)
            except Exception as exc:  # noqa: BLE001 — surface HTTP / network errors to user
                self.app.call_from_thread(self.set_status, f"error: {exc}", "error")
                return
            self.app.call_from_thread(self._fill_remote_table, channel, versions)

        self.run_worker(worker, exclusive=True, thread=True)

    def _fill_remote_table(self, channel: str, versions) -> None:
        table = self.query_one("#remote-table", DataTable)
        table.clear()
        for v in versions:
            table.add_row(v.id, v.published_at, v.asset_name, key=v.id)
        self.set_status(f"loaded {len(versions)} remote version(s) for {channel}", "success")

    def _install_zip(self) -> None:
        fields = [
            InputField("file", "Path to .zip", required=True),
            InputField("as_id", "Version id (optional)"),
            InputField("channel", "Channel", default="vanilla", required=True),
            InputField("force", "Force overwrite (y/n)", default="n"),
        ]
        self.app.push_screen(InputModal("Install from local zip", fields), self._do_install_zip)

    def _do_install_zip(self, values) -> None:
        if values is None:
            return
        force = values["force"].lower() in {"y", "yes", "true", "1"}

        def worker() -> None:
            try:
                vid = install_from_file(
                    self.root,
                    Path(values["file"]),
                    values["as_id"] or None,
                    values["channel"],
                    force=force,
                )
            except Exception as exc:  # noqa: BLE001 — surface filesystem / extraction errors
                self.app.call_from_thread(self.set_status, f"error: {exc}", "error")
                return
            self.app.call_from_thread(self.set_status, f"installed {vid}", "success")
            self.app.call_from_thread(self.notify_data_changed)

        self.set_status("installing from zip…")
        self.run_worker(worker, exclusive=True, thread=True)

    def _install_dir(self) -> None:
        fields = [
            InputField("dir", "Path to extracted DoL directory", required=True),
            InputField("as_id", "Version id (optional)"),
            InputField("channel", "Channel", default="vanilla", required=True),
            InputField("force", "Force overwrite (y/n)", default="n"),
        ]
        self.app.push_screen(InputModal("Install from local directory", fields), self._do_install_dir)

    def _do_install_dir(self, values) -> None:
        if values is None:
            return
        force = values["force"].lower() in {"y", "yes", "true", "1"}

        def worker() -> None:
            try:
                vid = install_from_dir(
                    self.root,
                    Path(values["dir"]),
                    values["as_id"] or None,
                    values["channel"],
                    force=force,
                )
            except Exception as exc:  # noqa: BLE001
                self.app.call_from_thread(self.set_status, f"error: {exc}", "error")
                return
            self.app.call_from_thread(self.set_status, f"installed {vid}", "success")
            self.app.call_from_thread(self.notify_data_changed)

        self.set_status("installing from directory…")
        self.run_worker(worker, exclusive=True, thread=True)

    def _install_remote(self) -> None:
        channel = self._selected_channel()
        if channel is None:
            self.set_status("pick a channel first", "warn")
            return
        selector = self._selected_remote()
        if selector is None:
            self.set_status("pick a remote version row first", "warn")
            return
        self.app.push_screen(
            ConfirmModal(
                f"Download and install '{selector}' from channel '{channel}'?",
                confirm_label="Install",
            ),
            lambda ok: self._do_install_remote(channel, selector, ok),
        )

    def _install_latest(self) -> None:
        """One-click: install the most recently published remote version
        for the picked channel. Always fetches fresh from the network.
        """
        channel = self._selected_channel()
        if channel is None:
            self.set_status("pick a channel first", "warn")
            return

        progress = make_progress_reporter(
            self.app, self.set_status, f"downloading latest {channel}"
        )

        def worker() -> None:
            try:
                # ``latest`` selector resolves to the newest published
                # release inside install_from_remote (see core.versions).
                vid = install_from_remote(self.root, channel, "latest", progress=progress)
            except Exception as exc:  # noqa: BLE001 — surface HTTP / extraction errors
                self.app.call_from_thread(self.set_status, f"error: {exc}", "error")
                return
            self.app.call_from_thread(self.set_status, f"installed latest: {vid}", "success")
            self.app.call_from_thread(self.notify_data_changed)

        self.set_status(f"installing latest {channel}…")
        self.run_worker(worker, exclusive=True, thread=True)

    def _do_install_remote(self, channel: str, selector: str, ok: bool | None) -> None:
        if not ok:
            return

        progress = make_progress_reporter(
            self.app, self.set_status, f"downloading {selector}"
        )

        def worker() -> None:
            try:
                vid = install_from_remote(
                    self.root, channel, selector, progress=progress
                )
            except Exception as exc:  # noqa: BLE001 — surface HTTP / extraction errors
                self.app.call_from_thread(self.set_status, f"error: {exc}", "error")
                return
            self.app.call_from_thread(self.set_status, f"installed {vid}", "success")
            self.app.call_from_thread(self.notify_data_changed)

        self.set_status(f"downloading {selector}…")
        self.run_worker(worker, exclusive=True, thread=True)

    def _use_selected(self) -> None:
        version_id = self._selected_installed()
        if version_id is None:
            self.set_status("select an installed version first", "warn")
            return
        state = load_state(self.root)
        config = load_config(self.root)
        profile = state.active_profile or config.default_profile
        try:
            set_profile_version(self.root, profile, version_id)
        except DolCtlError as exc:
            self.set_status(f"error: {exc}", "error")
            return
        self.set_status(f"profile {profile} now uses {version_id}", "success")
        self.notify_data_changed()

    def _remove_selected(self) -> None:
        version_id = self._selected_installed()
        if version_id is None:
            self.set_status("select an installed version first", "warn")
            return
        self.app.push_screen(
            ConfirmModal(
                f"Remove installed version '{version_id}'?",
                confirm_label="Remove",
            ),
            lambda ok: self._do_remove(version_id, ok),
        )

    def _do_remove(self, version_id: str, ok: bool | None) -> None:
        if not ok:
            return
        try:
            affected = remove_version(self.root, version_id)
        except DolCtlError as exc:
            self.set_status(f"error: {exc}", "error")
            return
        if affected:
            self.set_status(
                f"removed {version_id}; affected profiles: {', '.join(affected)}",
                "success",
            )
        else:
            self.set_status(f"removed {version_id}", "success")
        self.notify_data_changed()
