from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import (
    Button,
    DataTable,
    ListItem,
    ListView,
    Select,
    Static,
)

from core.models import DolCtlError
from core.profiles import (
    add_mod_to_profile,
    create_profile,
    get_profile,
    list_profiles,
    remove_mod_from_profile,
    reorder_mods,
    set_active_profile,
    set_profile_version,
)
from core.mods import list_mods
from core.versions import list_installed
from core.root import load_state

from ..modals import ConfirmModal, InputField, InputModal
from .base import RefreshableTab


class ProfileItem(ListItem):
    """ListItem that remembers which profile name it represents.

    Same rationale as channels.py:PresetItem — avoids DuplicateIds when
    refresh_from_disk re-populates the ListView and the prior items
    haven't been unmounted yet.
    """

    def __init__(self, profile_name: str, label: str) -> None:
        super().__init__(Static(label))
        self.profile_name = profile_name


class ProfilesTab(RefreshableTab):
    """Profile management with inline mod toggle + reorder."""

    DEFAULT_CSS = """
    ProfilesTab #cols { height: 1fr; }
    ProfilesTab #left { width: 35; padding-right: 1; }
    ProfilesTab ListView { height: 1fr; }
    ProfilesTab #right { padding-left: 1; }
    ProfilesTab #version-row { height: auto; padding-bottom: 1; }
    ProfilesTab #version-row Select { width: 40; }
    ProfilesTab DataTable { height: 1fr; }
    ProfilesTab #profile-actions { height: auto; padding-top: 1; }
    ProfilesTab #profile-actions Button { margin-right: 1; }
    ProfilesTab #mods-help { color: $text-muted; padding-bottom: 1; }
    """

    BINDINGS = [
        Binding("space", "toggle_mod", "Toggle", show=False),
        Binding("plus", "move_mod(-1)", "Move up", show=False),
        Binding("minus", "move_mod(1)", "Move down", show=False),
    ]

    _selected_profile: str | None = None

    def compose(self) -> ComposeResult:
        with Horizontal(id="cols"):
            with Vertical(id="left"):
                yield Static("[b]Profiles[/b]")
                yield ListView(id="profile-list")
                with Horizontal(id="profile-actions"):
                    yield Button("New", id="btn-new")
                    yield Button("Use", id="btn-use")
                    yield Button("Delete", id="btn-delete", variant="error")
            with Vertical(id="right"):
                yield Static("[b]Profile detail[/b]")
                with Horizontal(id="version-row"):
                    yield Static("version: ", id="version-label")
                    yield Select([], id="version-select", prompt="(none)")
                yield Static(
                    "space = toggle enabled · +/- = move selected mod up/down",
                    id="mods-help",
                )
                table = DataTable(id="profile-mods-table", cursor_type="row")
                table.add_columns("on", "order", "id", "name", "version")
                yield table

    def refresh_from_disk(self) -> None:
        state = load_state(self.root)
        active = state.active_profile

        profiles = list_profiles(self.root)
        if self._selected_profile not in profiles:
            self._selected_profile = active if active in profiles else (profiles[0] if profiles else None)

        # Left list -----------------------------------------------------
        listview = self.query_one("#profile-list", ListView)
        listview.clear()
        for name in profiles:
            label = name + ("  (active)" if name == active else "")
            listview.append(ProfileItem(name, label))

        # Version dropdown ---------------------------------------------
        installed = list_installed(self.root)
        select = self.query_one("#version-select", Select)
        options = [(v.id, v.id) for v in installed]
        select.set_options(options)

        if self._selected_profile is None:
            self._clear_right_pane()
            return

        try:
            profile = get_profile(self.root, self._selected_profile)
        except DolCtlError:
            self._clear_right_pane()
            return

        if profile.version_id and profile.version_id in {v.id for v in installed}:
            select.value = profile.version_id

        # Mod list -----------------------------------------------------
        enabled = list(profile.mod_order)
        enabled_set = set(enabled)
        all_mods = list_mods(self.root)
        # Order: enabled mods first (in profile order), then disabled (id sort)
        mod_lookup = {m.id: m for m in all_mods}
        ordered: list[tuple[str, bool, int | None]] = []
        for idx, mid in enumerate(enabled, 1):
            if mid in mod_lookup:
                ordered.append((mid, True, idx))
        for m in all_mods:
            if m.id not in enabled_set:
                ordered.append((m.id, False, None))

        table = self.query_one("#profile-mods-table", DataTable)
        table.clear()
        for mid, on, order in ordered:
            m = mod_lookup.get(mid)
            table.add_row(
                "[green]✓[/green]" if on else " ",
                str(order) if order is not None else "",
                mid,
                m.name if m else "(missing)",
                m.version if m else "",
                key=mid,
            )

    def _clear_right_pane(self) -> None:
        self.query_one("#profile-mods-table", DataTable).clear()
        select = self.query_one("#version-select", Select)
        select.set_options([])

    # ----- events -------------------------------------------------------

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if not isinstance(event.item, ProfileItem):
            return
        self._selected_profile = event.item.profile_name
        self.refresh_from_disk()

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id != "version-select":
            return
        if self._selected_profile is None:
            return
        # Check event.value (captured at fire time), not select.is_blank()
        # (reads current widget state). When refresh_from_disk runs
        # set_options(...) immediately followed by select.value = X, the
        # first event fires AFTER the second assignment lands, so the
        # widget reports non-blank while event.value is still NULL — and
        # str(Select.NULL) is the literal "Select.NULL".
        if event.value == Select.NULL:
            return
        new_value = str(event.value)
        # Avoid an infinite refresh loop: refresh_from_disk re-assigns
        # the dropdown value, which fires this handler. Only write when
        # the user actually changed the binding.
        try:
            current = get_profile(self.root, self._selected_profile).version_id
        except DolCtlError as exc:
            self.set_status(f"error: {exc}")
            return
        if current == new_value:
            return
        try:
            set_profile_version(self.root, self._selected_profile, new_value)
        except DolCtlError as exc:
            self.set_status(f"error: {exc}")
            return
        self.set_status(
            f"profile {self._selected_profile} now uses {new_value}"
        )
        self.notify_data_changed()

    # ----- buttons ------------------------------------------------------

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id
        if bid == "btn-new":
            self._new_profile()
        elif bid == "btn-use":
            self._use_selected()
        elif bid == "btn-delete":
            self._delete_selected()

    def _new_profile(self) -> None:
        self.app.push_screen(
            InputModal(
                "Create profile",
                [InputField("name", "Profile name", required=True)],
            ),
            self._do_new_profile,
        )

    def _do_new_profile(self, values) -> None:
        if values is None:
            return
        try:
            create_profile(self.root, values["name"])
        except DolCtlError as exc:
            self.set_status(f"error: {exc}")
            return
        self._selected_profile = values["name"]
        self.set_status(f"created profile {values['name']}")
        self.notify_data_changed()

    def _use_selected(self) -> None:
        if self._selected_profile is None:
            self.set_status("select a profile first")
            return
        try:
            set_active_profile(self.root, self._selected_profile)
        except DolCtlError as exc:
            self.set_status(f"error: {exc}")
            return
        self.set_status(f"active profile: {self._selected_profile}")
        self.notify_data_changed()

    def _delete_selected(self) -> None:
        if self._selected_profile is None:
            self.set_status("select a profile first")
            return
        if self._selected_profile == "default":
            self.set_status("refusing to delete the 'default' profile")
            return
        name = self._selected_profile
        self.app.push_screen(
            ConfirmModal(f"Delete profile '{name}'?", confirm_label="Delete"),
            lambda ok: self._do_delete(name, ok),
        )

    def _do_delete(self, name: str, ok: bool | None) -> None:
        if not ok:
            return
        import shutil

        path = self.root / "profiles" / name
        try:
            shutil.rmtree(path)
        except OSError as exc:
            self.set_status(f"error: {exc}")
            return
        self._selected_profile = None
        self.set_status(f"deleted profile {name}")
        self.notify_data_changed()

    # ----- mod toggle / reorder ----------------------------------------

    def _selected_mod_id(self) -> str | None:
        table = self.query_one("#profile-mods-table", DataTable)
        if table.row_count == 0:
            return None
        row_key = table.coordinate_to_cell_key(table.cursor_coordinate).row_key
        return row_key.value if row_key else None

    def action_toggle_mod(self) -> None:
        if self._selected_profile is None:
            return
        mid = self._selected_mod_id()
        if mid is None:
            return
        try:
            profile = get_profile(self.root, self._selected_profile)
        except DolCtlError as exc:
            self.set_status(f"error: {exc}")
            return
        try:
            if mid in profile.mod_order:
                remove_mod_from_profile(self.root, self._selected_profile, mid)
                self.set_status(f"disabled {mid}")
            else:
                add_mod_to_profile(self.root, self._selected_profile, mid)
                self.set_status(f"enabled {mid}")
        except DolCtlError as exc:
            self.set_status(f"error: {exc}")
            return
        self.notify_data_changed()

    def action_move_mod(self, delta: int) -> None:
        if self._selected_profile is None:
            return
        mid = self._selected_mod_id()
        if mid is None:
            return
        try:
            profile = get_profile(self.root, self._selected_profile)
        except DolCtlError:
            return
        order = list(profile.mod_order)
        if mid not in order:
            self.set_status("only enabled mods can be reordered")
            return
        idx = order.index(mid)
        new_idx = max(0, min(len(order) - 1, idx + delta))
        if new_idx == idx:
            return
        order.insert(new_idx, order.pop(idx))
        try:
            reorder_mods(self.root, self._selected_profile, order)
        except DolCtlError as exc:
            self.set_status(f"error: {exc}")
            return
        self.set_status(f"moved {mid} to position {new_idx + 1}")
        self.notify_data_changed()
