from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Grid, Horizontal
from textual.widgets import Button, Static

from core.models import DolCtlError
from core.profiles import get_profile, list_profiles
from core.root import load_config, load_state

from .base import RefreshableTab
from .run import RunTab


def _safe_get_profile(root, name: str):
    try:
        return get_profile(root, name)
    except DolCtlError:
        return None


class HomeTab(RefreshableTab):
    DEFAULT_CSS = """
    HomeTab Grid#metrics {
        grid-size: 2;
        grid-gutter: 1 2;
        grid-rows: auto;
        height: auto;
        padding-bottom: 1;
    }
    HomeTab .card {
        border: round;
        padding: 1 2;
        height: auto;
    }
    HomeTab .card-title {
        text-style: bold;
    }
    HomeTab Horizontal#actions {
        height: auto;
        padding-top: 1;
    }
    HomeTab Horizontal#actions Button {
        margin-right: 2;
    }
    """

    def compose(self) -> ComposeResult:
        with Grid(id="metrics"):
            yield Static("", id="card-root", classes="card")
            yield Static("", id="card-profile", classes="card")
            yield Static("", id="card-channels", classes="card")
            yield Static("", id="card-mods", classes="card")
        with Horizontal(id="actions"):
            yield Button("Run", id="btn-run", variant="primary")

    def refresh_from_disk(self) -> None:
        try:
            config = load_config(self.root)
            state = load_state(self.root)
        except DolCtlError as exc:
            self.set_status(f"error: {exc}", "error")
            return

        from core.mods import list_mods
        from core.versions import list_installed

        installed = list_installed(self.root)
        mods = list_mods(self.root)
        profiles = list_profiles(self.root)
        active = state.active_profile or config.default_profile
        active_profile = _safe_get_profile(self.root, active)

        self.query_one("#card-root", Static).update(
            f"[b]ROOT[/b]\n"
            f"{self.root}\n"
            f"{len(installed)} version(s) · {len(profiles)} profile(s)"
        )
        if active_profile is not None:
            self.query_one("#card-profile", Static).update(
                f"[b]ACTIVE PROFILE[/b]\n"
                f"{active}\n"
                f"version: {active_profile.version_id or '(none)'}\n"
                f"{len(active_profile.mod_order)} mod(s) enabled"
            )
        else:
            self.query_one("#card-profile", Static).update(
                f"[b]ACTIVE PROFILE[/b]\n"
                f"{active} (missing on disk)"
            )
        self.query_one("#card-channels", Static).update(
            f"[b]CHANNELS[/b]\n"
            + (
                "\n".join(f"· {n} → {c.repo}" for n, c in config.channels.items())
                if config.channels
                else "(none configured)"
            )
        )
        self.query_one("#card-mods", Static).update(
            f"[b]MODS LIBRARY[/b]\n"
            f"{len(mods)} installed\n"
            + (
                ", ".join(m.id for m in mods[:6])
                + ("…" if len(mods) > 6 else "")
                if mods
                else "(empty)"
            )
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-run":
            # Hand off to RunTab (single source of truth for build + serve)
            self.dolctl_app.action_switch_tab("run")
            run_tab = self.app.query_one(RunTab)
            run_tab.action_run()
