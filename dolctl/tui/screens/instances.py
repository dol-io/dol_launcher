from __future__ import annotations

from typing import Any

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import (
    Button,
    DataTable,
    Input,
    ListItem,
    ListView,
    RichLog,
    Select,
    Static,
)

from core.models import BuildResult, DolCtlError, Profile, RemoveResult
from core.launcher import LaunchSession

from ..modals import ConfirmModal, InputField, InputModal
from .base import RefreshableTab


class InstanceItem(ListItem):
    def __init__(self, name: str, label: str) -> None:
        super().__init__(Static(label))
        self.instance_name = name


class InstancesTab(RefreshableTab):
    DEFAULT_CSS = """
    InstancesTab #main { height: 3fr; }
    InstancesTab #left { width: 30; padding-right: 1; }
    InstancesTab #right { padding-left: 1; }
    InstancesTab ListView { height: 1fr; }
    InstancesTab #instance-actions,
    InstancesTab #settings,
    InstancesTab #mod-actions,
    InstancesTab #launch-actions { height: auto; padding-top: 1; }
    InstancesTab Button { margin-right: 1; }
    InstancesTab #settings Select { width: 30; margin-right: 1; }
    InstancesTab #settings Input { width: 12; margin-right: 1; }
    InstancesTab DataTable { height: 1fr; }
    InstancesTab RichLog { height: 1fr; border: round; margin-top: 1; }
    """

    BINDINGS = [
        Binding("space", "toggle_mod", "Toggle mod"),
        Binding("plus", "move_mod(-1)", "Move up"),
        Binding("minus", "move_mod(1)", "Move down"),
    ]

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._selected_name: str | None = None
        self._session: LaunchSession | None = None

    def compose(self) -> ComposeResult:
        with Horizontal(id="main"):
            with Vertical(id="left"):
                yield Static("[b]Instances[/b]")
                yield ListView(id="instance-list")
                with Horizontal(id="instance-actions"):
                    yield Button("New", id="new")
                    yield Button("Select", id="select", variant="primary")
                    yield Button("Delete", id="delete", variant="error")
            with Vertical(id="right"):
                yield Static("Select an instance", id="summary")
                with Horizontal(id="settings"):
                    yield Select([], prompt="Version", id="version")
                    yield Input(placeholder="default port", id="port")
                    yield Select(
                        [
                            ("Browser: global", "default"),
                            ("Browser: open", "yes"),
                            ("Browser: do not open", "no"),
                        ],
                        value="default",
                        id="browser",
                    )
                    yield Button("Save", id="save")
                table: DataTable[str] = DataTable(id="mods", cursor_type="row")
                table.add_columns("on", "order", "id", "name", "version")
                yield table
                with Horizontal(id="mod-actions"):
                    yield Button("Toggle", id="toggle-mod")
                    yield Button("Up", id="mod-up")
                    yield Button("Down", id="mod-down")
                with Horizontal(id="launch-actions"):
                    yield Button("Build", id="build")
                    yield Button("Launch", id="launch", variant="primary")
                    yield Button("Stop", id="stop", variant="error", disabled=True)
        yield RichLog(id="log", markup=False, highlight=False)

    def refresh_from_disk(self) -> None:
        try:
            snapshot = self.launcher.snapshot()
        except DolCtlError as exc:
            self.set_status(str(exc), "error")
            return
        names = [profile.name for profile in snapshot.profiles]
        if self._selected_name not in names:
            self._selected_name = (
                snapshot.active_profile
                if snapshot.active_profile in names
                else (names[0] if names else None)
            )

        instance_list = self.query_one("#instance-list", ListView)
        instance_list.clear()
        for profile in snapshot.profiles:
            marker = "  (selected)" if profile.name == snapshot.active_profile else ""
            instance_list.append(InstanceItem(profile.name, profile.name + marker))

        version_select = self.query_one("#version", Select)
        version_select.set_options(
            [("(no version)", ""), *[(item.id, item.id) for item in snapshot.versions]]
        )
        table = self.query_one("#mods", DataTable)
        table.clear()
        if self._selected_name is None:
            self.query_one("#summary", Static).update("No instance available")
            self._sync_server_buttons()
            return

        profile = next(
            item for item in snapshot.profiles if item.name == self._selected_name
        )
        version_select.value = profile.version_id
        self.query_one("#port", Input).value = (
            str(profile.port) if profile.port is not None else ""
        )
        browser_value = (
            "default"
            if profile.open_browser is None
            else ("yes" if profile.open_browser else "no")
        )
        self.query_one("#browser", Select).value = browser_value
        self.query_one("#summary", Static).update(
            f"[b]{profile.name}[/b]  ·  version {profile.version_id or '(none)'}  ·  "
            f"{len(profile.mod_order)} enabled mod(s)"
        )

        mod_lookup = {mod.id: mod for mod in snapshot.mods}
        rows: list[tuple[str, bool, int | None]] = []
        for index, mod_id in enumerate(profile.mod_order, 1):
            rows.append((mod_id, True, index))
        for available_mod in snapshot.mods:
            if available_mod.id not in profile.mod_order:
                rows.append((available_mod.id, False, None))
        for mod_id, enabled, order in rows:
            mod = mod_lookup.get(mod_id)
            table.add_row(
                "✓" if enabled else "",
                str(order or ""),
                mod_id,
                mod.name if mod else "(missing)",
                mod.version if mod else "",
                key=mod_id,
            )
        self._sync_server_buttons()

    def _profile(self) -> Profile | None:
        if self._selected_name is None:
            return None
        try:
            return self.launcher.instance(self._selected_name)
        except DolCtlError as exc:
            self.set_status(str(exc), "error")
            return None

    def _selected_mod(self) -> str | None:
        table = self.query_one("#mods", DataTable)
        if table.row_count == 0:
            return None
        key = table.coordinate_to_cell_key(table.cursor_coordinate).row_key
        return str(key.value) if key is not None else None

    def _sync_server_buttons(self) -> None:
        if not self.is_mounted:
            return
        running = self._session is not None and self._session.server.running
        self.query_one("#launch", Button).disabled = running or self._busy
        self.query_one("#build", Button).disabled = running or self._busy
        self.query_one("#stop", Button).disabled = not running or self._busy

    def set_busy(self, busy: bool) -> None:
        super().set_busy(busy)
        self._sync_server_buttons()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if isinstance(event.item, InstanceItem):
            self._selected_name = event.item.instance_name
            self.refresh_from_disk()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        handlers = {
            "new": self._new,
            "select": self._select,
            "delete": self._delete,
            "save": self._save,
            "toggle-mod": self.action_toggle_mod,
            "mod-up": lambda: self.action_move_mod(-1),
            "mod-down": lambda: self.action_move_mod(1),
            "build": self._build,
            "launch": self._launch,
            "stop": self._stop,
        }
        handler = handlers.get(event.button.id or "")
        if handler is not None:
            handler()

    def _new(self) -> None:
        self.app.push_screen(
            InputModal(
                "Create instance",
                [
                    InputField("name", "Name", required=True),
                    InputField("version", "Version id (optional)"),
                ],
            ),
            self._create_from_modal,
        )

    def _create_from_modal(self, values: dict[str, str] | None) -> None:
        if values is None:
            return
        self.run_operation(
            f"Creating {values['name']}…",
            lambda: self.launcher.create_instance(
                values["name"], version_id=values["version"] or None
            ),
            self._created,
            mutates=True,
        )

    def _created(self, result: object) -> None:
        assert isinstance(result, Profile)
        self._selected_name = result.name
        self.set_status(f"Created instance {result.name}", "success")

    def _select(self) -> None:
        if self._selected_name is None:
            self.set_status("Select an instance first", "warning")
            return
        name = self._selected_name
        self.run_operation(
            f"Selecting {name}…",
            lambda: self.launcher.select_instance(name),
            lambda _result: self.set_status(f"Selected {name}", "success"),
            mutates=True,
        )

    def _delete(self) -> None:
        if self._selected_name is None:
            self.set_status("Select an instance first", "warning")
            return
        name = self._selected_name
        self.app.push_screen(
            ConfirmModal(f"Delete instance '{name}'?", confirm_label="Delete"),
            lambda confirmed: self._delete_confirmed(name, confirmed),
        )

    def _delete_confirmed(self, name: str, confirmed: bool | None) -> None:
        if not confirmed:
            return
        self.run_operation(
            f"Deleting {name}…",
            lambda: self.launcher.delete_instance(name),
            self._deleted,
            mutates=True,
        )

    def _deleted(self, result: object) -> None:
        assert isinstance(result, RemoveResult)
        self._selected_name = None
        self.set_status(f"Deleted instance {result.resource_id}", "success")

    def _save(self) -> None:
        if self._selected_name is None:
            self.set_status("Select an instance first", "warning")
            return
        version_widget = self.query_one("#version", Select)
        version = "" if version_widget.is_blank() else str(version_widget.value)
        port_text = self.query_one("#port", Input).value.strip()
        try:
            port = int(port_text) if port_text else None
        except ValueError:
            self.set_status("Port must be a number", "error")
            return
        browser_value = str(self.query_one("#browser", Select).value)
        browser = None if browser_value == "default" else browser_value == "yes"
        name = self._selected_name
        self.run_operation(
            f"Saving {name}…",
            lambda: self.launcher.configure_instance(
                name,
                version_id=version or None,
                port=port,
                open_browser=browser,
            ),
            lambda _result: self.set_status(f"Saved {name}", "success"),
            mutates=True,
        )

    def action_toggle_mod(self) -> None:
        profile = self._profile()
        mod_id = self._selected_mod()
        if profile is None or mod_id is None:
            self.set_status("Select a mod row first", "warning")
            return
        enabled = mod_id in profile.mod_order

        def operation() -> Profile:
            if enabled:
                return self.launcher.disable_mod(profile.name, mod_id)
            return self.launcher.enable_mod(profile.name, mod_id)

        self.run_operation(
            f"{'Disabling' if enabled else 'Enabling'} {mod_id}…",
            operation,
            lambda _result: self.set_status(
                f"{'Disabled' if enabled else 'Enabled'} {mod_id}", "success"
            ),
            mutates=True,
        )

    def action_move_mod(self, delta: int) -> None:
        profile = self._profile()
        mod_id = self._selected_mod()
        if profile is None or mod_id is None:
            return
        if mod_id not in profile.mod_order:
            self.set_status("Only enabled mods have a load order", "warning")
            return
        order = list(profile.mod_order)
        old_index = order.index(mod_id)
        new_index = max(0, min(len(order) - 1, old_index + delta))
        if old_index == new_index:
            return
        order.insert(new_index, order.pop(old_index))
        self.run_operation(
            f"Moving {mod_id}…",
            lambda: self.launcher.reorder_instance_mods(profile.name, order),
            lambda _result: self.set_status(
                f"Moved {mod_id} to position {new_index + 1}", "success"
            ),
            mutates=True,
        )

    def _build(self) -> None:
        if self._selected_name is None:
            self.set_status("Select an instance first", "warning")
            return
        name = self._selected_name
        self.run_operation(
            f"Building {name}…",
            lambda: self.launcher.build(name),
            self._built,
            mutates=True,
        )

    def _built(self, result: object) -> None:
        assert isinstance(result, BuildResult)
        self.query_one("#log", RichLog).write(
            f"{result.status}: {result.profile} -> {result.output_dir}"
        )
        self.set_status(f"{result.status}: {result.profile}", "success")

    def _launch(self) -> None:
        if self._selected_name is None:
            self.set_status("Select an instance first", "warning")
            return
        if self._session is not None and self._session.server.running:
            self.set_status("A game server is already running", "warning")
            return
        name = self._selected_name

        def start() -> LaunchSession:
            session = self.launcher.prepare_run(name)
            try:
                session.start()
                session.open_browser()
            except BaseException:
                session.stop()
                raise
            return session

        self.run_operation(f"Launching {name}…", start, self._launched, mutates=True)

    def _launched(self, result: object) -> None:
        assert isinstance(result, LaunchSession)
        self._session = result
        self.query_one("#log", RichLog).write(f"Serving {result.url}")
        self.set_status(f"Serving {result.url}", "success")
        self._sync_server_buttons()

    def _stop(self) -> None:
        session = self._session
        if session is None:
            return
        self.run_operation("Stopping server…", session.stop, self._stopped)

    def _stopped(self, _result: object) -> None:
        self._session = None
        self.query_one("#log", RichLog).write("Server stopped")
        self.set_status("Server stopped", "success")
        self._sync_server_buttons()

    def on_unmount(self) -> None:
        if self._session is not None:
            self._session.stop()
            self._session = None
