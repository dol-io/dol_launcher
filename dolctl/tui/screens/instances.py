from __future__ import annotations

from typing import Any

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, DataTable, OptionList, RichLog, Static
from textual.widgets.option_list import Option

from core.launcher import LauncherSnapshot, LaunchSession
from core.models import BuildResult, DolCtlError, Profile, RemoveResult

from ..modals import (
    ConfirmModal,
    CreateInstanceModal,
    CreateInstanceValues,
    InstanceSettings,
    InstanceSettingsModal,
    ModManagerModal,
)
from .base import RefreshableTab


class InstancesTab(RefreshableTab):
    """The normal launch workflow: pick an instance, inspect it, then play."""

    DEFAULT_CSS = """
    InstancesTab {
        padding: 1 2;
    }

    InstancesTab #instance-workspace {
        height: 1fr;
    }

    InstancesTab #instance-sidebar {
        width: 30;
        padding-right: 1;
    }

    InstancesTab #instance-list {
        height: 1fr;
        border: round ansi_blue;
        border-title-color: ansi_yellow;
        border-title-background: ansi_default;
        border-title-style: bold;
        padding: 0 1;
    }

    InstancesTab #instance-list-actions,
    InstancesTab #play-actions,
    InstancesTab #manage-actions {
        height: auto;
        padding-top: 1;
    }

    InstancesTab Button {
        margin-right: 1;
    }

    InstancesTab #instance-detail {
        padding-left: 2;
        overflow-y: auto;
    }

    InstancesTab #instance-summary,
    InstancesTab #instance-facts,
    InstancesTab #empty-state {
        height: auto;
    }

    InstancesTab #instance-facts {
        margin-top: 1;
        padding: 0 1;
        border: round ansi_blue;
        border-title-color: ansi_yellow;
        border-title-background: ansi_default;
        border-title-style: bold;
    }

    InstancesTab #enabled-mods {
        height: 1fr;
        min-height: 6;
        margin-top: 1;
        border: round ansi_blue;
        border-title-color: ansi_yellow;
        border-title-background: ansi_default;
        border-title-style: bold;
    }

    InstancesTab #activity-log {
        height: 6;
        margin-top: 1;
        border: round ansi_blue;
        border-title-color: ansi_yellow;
        border-title-background: ansi_default;
        border-title-style: bold;
    }
    """

    BINDINGS = [
        Binding("n", "new_instance", "New instance", show=False),
        Binding("a", "make_active", "Make active", show=False),
        Binding("e", "edit_instance", "Configure", show=False),
        Binding("m", "manage_mods", "Manage mods", show=False),
        Binding("b", "build_instance", "Build", show=False),
        Binding("l", "launch_instance", "Launch", show=False),
        Binding("x", "stop_instance", "Stop", show=False),
    ]

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._selected_name: str | None = None
        self._snapshot: LauncherSnapshot | None = None
        self._session: LaunchSession | None = None
        self._session_instance: str | None = None
        self._refreshing = False

    def compose(self) -> ComposeResult:
        with Horizontal(id="instance-workspace"):
            with Vertical(id="instance-sidebar"):
                instance_list = OptionList(id="instance-list", markup=False)
                instance_list.border_title = " Instances "
                yield instance_list
                with Horizontal(id="instance-list-actions"):
                    yield Button("New", id="new-instance", classes="action-accent")
                    yield Button(
                        "Delete",
                        id="delete-instance",
                        classes="action-danger",
                    )
            with Vertical(id="instance-detail"):
                yield Static("Select an instance", id="instance-summary")
                yield Static("", id="empty-state", markup=False)
                with Horizontal(id="play-actions"):
                    yield Button(
                        "Launch",
                        id="launch-instance",
                        classes="action-primary",
                    )
                    yield Button(
                        "Stop",
                        id="stop-instance",
                        classes="action-danger",
                        disabled=True,
                    )
                    yield Button(
                        "Build",
                        id="build-instance",
                        classes="action-accent",
                    )
                instance_facts = Static("", id="instance-facts", markup=False)
                instance_facts.border_title = " Overview "
                yield instance_facts
                with Horizontal(id="manage-actions"):
                    yield Button("Configure", id="edit-instance")
                    yield Button("Manage mods", id="manage-mods")
                    yield Button(
                        "Make active",
                        id="make-active",
                        classes="action-accent",
                    )
                mods: DataTable[str] = DataTable(id="enabled-mods", cursor_type="row")
                mods.add_columns("order", "id", "name", "version")
                mods.border_title = " Enabled mods "
                yield mods
                activity = RichLog(
                    id="activity-log",
                    markup=False,
                    highlight=False,
                    wrap=True,
                )
                activity.border_title = " Activity "
                yield activity

    def refresh_from_disk(self) -> None:
        snapshot = self.launcher.snapshot()
        self._snapshot = snapshot
        names = [profile.name for profile in snapshot.profiles]
        if self._selected_name not in names:
            self._selected_name = (
                snapshot.active_profile
                if snapshot.active_profile in names
                else (names[0] if names else None)
            )

        instance_list = self.query_one("#instance-list", OptionList)
        self._refreshing = True
        instance_list.clear_options()
        instance_list.add_options(
            Option(
                self._instance_label(profile.name, snapshot.active_profile),
                id=profile.name,
            )
            for profile in snapshot.profiles
        )
        if self._selected_name in names:
            instance_list.highlighted = names.index(self._selected_name)
        self._refreshing = False
        self._render_selected(snapshot)

    def _instance_label(self, name: str, active_name: str) -> Text:
        label = Text(name)
        if name == active_name:
            label.append("  [active]", style="bold yellow")
        if name == self._session_instance and self._server_running:
            label.append("  [running]", style="bold green")
        return label

    @property
    def _server_running(self) -> bool:
        return self._session is not None and self._session.server.running

    def _selected_profile(self) -> Profile | None:
        if self._selected_name is None:
            return None
        if self._snapshot is not None:
            profile = next(
                (
                    item
                    for item in self._snapshot.profiles
                    if item.name == self._selected_name
                ),
                None,
            )
            if profile is not None:
                return profile
        try:
            return self.launcher.instance(self._selected_name)
        except DolCtlError as exc:
            self.set_status(str(exc), "error")
            return None

    def _render_selected(self, snapshot: LauncherSnapshot) -> None:
        table = self.query_one("#enabled-mods", DataTable)
        table.clear()
        profile = self._selected_profile()
        empty = self.query_one("#empty-state", Static)
        facts = self.query_one("#instance-facts", Static)
        if profile is None:
            self.query_one("#instance-summary", Static).update(
                Text("No instances", style="bold yellow")
            )
            empty.update("Create an instance to begin.")
            facts.update("")
            self._sync_buttons()
            return

        empty.update("")
        self.query_one("#instance-summary", Static).update(
            Text(profile.name, style="bold bright_cyan")
        )
        installed_versions = {version.id for version in snapshot.versions}
        if not profile.version_id:
            version_text = "not selected — install or choose one in Library"
        elif profile.version_id not in installed_versions:
            version_text = f"{profile.version_id} (missing)"
        else:
            version_text = profile.version_id
        browser_text = {
            None: "global default",
            True: "open after launch",
            False: "do not open",
        }[profile.open_browser]
        active_text = "yes" if profile.name == snapshot.active_profile else "no"
        if self._server_running:
            assert self._session is not None
            server_text = f"{self._session_instance} at {self._session.url}"
        else:
            server_text = "stopped"
        fact_values = (
            (
                "Version",
                version_text,
                "red"
                if profile.version_id and profile.version_id not in installed_versions
                else "",
            ),
            ("Mods", f"{len(profile.mod_order)} enabled", ""),
            (
                "Port",
                str(profile.port) if profile.port is not None else "global default",
                "",
            ),
            ("Browser", browser_text, ""),
            ("Active", active_text, "yellow" if active_text == "yes" else ""),
            (
                "Server",
                server_text,
                "green" if self._server_running else "",
            ),
        )
        fact_lines: list[Text] = []
        for label, value, style in fact_values:
            line = Text()
            line.append(f"{label:<11}", style="bold yellow")
            line.append(value, style=style)
            fact_lines.append(line)
        facts.update(Text("\n").join(fact_lines))

        mod_lookup = {mod.id: mod for mod in snapshot.mods}
        for position, mod_id in enumerate(profile.mod_order, 1):
            mod = mod_lookup.get(mod_id)
            table.add_row(
                str(position),
                mod_id,
                mod.name if mod is not None else "(missing)",
                mod.version if mod is not None else "",
                key=mod_id,
            )
        self._sync_buttons()

    def _sync_buttons(self) -> None:
        if not self.is_mounted:
            return
        profile = self._selected_profile()
        running = self._server_running
        active_name = self._snapshot.active_profile if self._snapshot else None
        self.query_one("#new-instance", Button).disabled = self._busy
        if profile is None:
            for button_id in (
                "delete-instance",
                "launch-instance",
                "build-instance",
                "edit-instance",
                "manage-mods",
                "make-active",
            ):
                self.query_one(f"#{button_id}", Button).disabled = True
            self.query_one("#stop-instance", Button).disabled = (
                self._busy or not running
            )
            return
        self.query_one("#delete-instance", Button).disabled = (
            self._busy
            or profile.name == "default"
            or (running and profile.name == self._session_instance)
        )
        self.query_one("#launch-instance", Button).disabled = self._busy or running
        self.query_one("#stop-instance", Button).disabled = self._busy or not running
        self.query_one("#build-instance", Button).disabled = self._busy or running
        self.query_one("#edit-instance", Button).disabled = self._busy
        self.query_one("#manage-mods", Button).disabled = self._busy
        self.query_one("#make-active", Button).disabled = (
            self._busy or profile.name == active_name
        )

    def set_busy(self, busy: bool) -> None:
        super().set_busy(busy)
        self._sync_buttons()

    def on_option_list_option_highlighted(
        self, event: OptionList.OptionHighlighted
    ) -> None:
        if self._refreshing or event.option_id is None:
            return
        self._selected_name = event.option_id
        if self._snapshot is not None:
            self._render_selected(self._snapshot)

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option_id is not None:
            self._selected_name = event.option_id
            if self._snapshot is not None:
                self._render_selected(self._snapshot)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        handlers = {
            "new-instance": self._new,
            "delete-instance": self._delete,
            "launch-instance": self._launch,
            "stop-instance": self._stop,
            "build-instance": self._build,
            "edit-instance": self._edit,
            "manage-mods": self._manage_mods,
            "make-active": self._make_active,
        }
        handler = handlers.get(event.button.id or "")
        if handler is not None:
            handler()

    def action_new_instance(self) -> None:
        self._new()

    def action_make_active(self) -> None:
        self._make_active()

    def action_edit_instance(self) -> None:
        self._edit()

    def action_manage_mods(self) -> None:
        self._manage_mods()

    def action_build_instance(self) -> None:
        self._build()

    def action_launch_instance(self) -> None:
        self._launch()

    def action_stop_instance(self) -> None:
        self._stop()

    def _new(self) -> None:
        snapshot = self._snapshot or self.launcher.snapshot()
        self.app.push_screen(
            CreateInstanceModal([version.id for version in snapshot.versions]),
            self._create_from_modal,
        )

    def _create_from_modal(self, values: CreateInstanceValues | None) -> None:
        if values is None:
            return
        self.run_operation(
            f"Creating {values.name}…",
            lambda: self.launcher.create_instance(
                values.name, version_id=values.version_id
            ),
            self._created,
            mutates=True,
        )

    def _created(self, result: object) -> None:
        assert isinstance(result, Profile)
        self._selected_name = result.name
        self.set_status(f"Created instance {result.name}", "success")

    def _make_active(self) -> None:
        profile = self._selected_profile()
        if profile is None:
            self.set_status("Choose an instance first", "warning")
            return
        self.run_operation(
            f"Making {profile.name} active…",
            lambda: self.launcher.select_instance(profile.name),
            lambda _result: self.set_status(f"{profile.name} is now active", "success"),
            mutates=True,
        )

    def _edit(self) -> None:
        profile = self._selected_profile()
        if profile is None:
            self.set_status("Choose an instance first", "warning")
            return
        snapshot = self._snapshot or self.launcher.snapshot()
        self.app.push_screen(
            InstanceSettingsModal(
                profile,
                [version.id for version in snapshot.versions],
            ),
            lambda settings: self._save_settings(profile.name, settings),
        )

    def _save_settings(self, name: str, settings: InstanceSettings | None) -> None:
        if settings is None:
            return
        self.run_operation(
            f"Saving {name}…",
            lambda: self.launcher.configure_instance(
                name,
                version_id=settings.version_id,
                port=settings.port,
                open_browser=settings.open_browser,
            ),
            lambda _result: self.set_status(f"Saved {name}", "success"),
            mutates=True,
        )

    def _manage_mods(self) -> None:
        profile = self._selected_profile()
        if profile is None:
            self.set_status("Choose an instance first", "warning")
            return
        snapshot = self._snapshot or self.launcher.snapshot()
        self.app.push_screen(
            ModManagerModal(profile, snapshot.mods),
            lambda order: self._save_mod_order(profile, order),
        )

    def _save_mod_order(self, profile: Profile, order: list[str] | None) -> None:
        if order is None:
            return
        if order == profile.mod_order:
            self.set_status("Mod selection unchanged")
            return
        self.run_operation(
            f"Saving mods for {profile.name}…",
            lambda: self.launcher.set_instance_mods(profile.name, order),
            lambda _result: self.set_status(
                f"Saved mods for {profile.name}", "success"
            ),
            mutates=True,
        )

    def _delete(self) -> None:
        profile = self._selected_profile()
        if profile is None:
            self.set_status("Choose an instance first", "warning")
            return
        self.app.push_screen(
            ConfirmModal(
                f"Delete instance '{profile.name}'?",
                confirm_label="Delete",
            ),
            lambda confirmed: self._delete_confirmed(profile.name, confirmed),
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

    def _build(self) -> None:
        profile = self._selected_profile()
        if profile is None:
            self.set_status("Choose an instance first", "warning")
            return
        self.run_operation(
            f"Building {profile.name}…",
            lambda: self.launcher.build(profile.name),
            self._built,
            mutates=True,
        )

    def _built(self, result: object) -> None:
        assert isinstance(result, BuildResult)
        self.query_one("#activity-log", RichLog).write(
            f"{result.status}: {result.profile} -> {result.output_dir}"
        )
        self.set_status(f"{result.status}: {result.profile}", "success")

    def _launch(self) -> None:
        profile = self._selected_profile()
        if profile is None:
            self.set_status("Choose an instance first", "warning")
            return
        if self._server_running:
            self.set_status("A game server is already running", "warning")
            return
        name = profile.name

        def start() -> LaunchSession:
            session = self.launcher.prepare_run(name)
            try:
                session.start()
                session.open_browser()
                self.launcher.select_instance(name)
            except BaseException:
                session.stop()
                raise
            return session

        self.run_operation(f"Launching {name}…", start, self._launched, mutates=True)

    def _launched(self, result: object) -> None:
        assert isinstance(result, LaunchSession)
        self._session = result
        self._session_instance = result.profile
        self.query_one("#activity-log", RichLog).write(f"Serving {result.url}")
        self.set_status(f"Serving {result.url}", "success")
        if self._snapshot is not None:
            self._render_selected(self._snapshot)

    def _stop(self) -> None:
        session = self._session
        if session is None:
            return
        self.run_operation("Stopping server…", session.stop, self._stopped)

    def _stopped(self, _result: object) -> None:
        self._session = None
        self._session_instance = None
        self.query_one("#activity-log", RichLog).write("Server stopped")
        self.set_status("Server stopped", "success")
        if self._snapshot is not None:
            self._render_selected(self._snapshot)

    def on_unmount(self) -> None:
        if self._session is not None:
            self._session.stop()
            self._session = None
            self._session_instance = None
