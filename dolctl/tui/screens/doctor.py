from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Button, Static

from core.root import load_config, load_state
from core.versions import list_installed

from .base import RefreshableTab


@dataclass
class Check:
    ok: bool
    note: str

    @property
    def symbol(self) -> str:
        return "[green]✓[/green]" if self.ok else "[yellow]⚠[/yellow]"


def _run_checks(root: Path) -> list[Check]:
    checks: list[Check] = []
    checks.append(Check(root.exists(), f"root exists: {root}"))
    for sub in (".dolctl", "versions", "mods", "profiles", "runtime"):
        path = root / sub
        checks.append(Check(path.is_dir(), f"{sub}/ present"))

    try:
        config = load_config(root)
        state = load_state(root)
    except Exception as exc:
        checks.append(Check(False, f"config/state load: {exc}"))
        return checks

    if config.channels:
        checks.append(Check(True, f"{len(config.channels)} channel(s) configured"))
    else:
        checks.append(Check(False, "no channels configured (only local installs work)"))

    active = state.active_profile or config.default_profile
    profile_path = root / "profiles" / active / "profile.toml"
    checks.append(
        Check(profile_path.exists(), f"active profile '{active}' exists on disk")
    )

    installed = {v.id: v for v in list_installed(root)}
    profiles_dir = root / "profiles"
    if profiles_dir.exists():
        for entry in sorted(profiles_dir.iterdir()):
            ptoml = entry / "profile.toml"
            if not ptoml.exists():
                continue
            from infra.toml import read_toml

            data = read_toml(ptoml)
            vid = str(data.get("version_id") or "")
            if not vid:
                checks.append(Check(True, f"profile '{entry.name}' has no version bound"))
            elif vid in installed:
                checks.append(
                    Check(True, f"profile '{entry.name}' → version '{vid}' present")
                )
            else:
                checks.append(
                    Check(
                        False,
                        f"profile '{entry.name}' references missing version '{vid}'",
                    )
                )
    return checks


class DoctorTab(RefreshableTab):
    DEFAULT_CSS = """
    DoctorTab #check-list { padding: 1 0; height: 1fr; }
    DoctorTab #actions { height: auto; padding-top: 1; }
    """

    def compose(self) -> ComposeResult:
        yield Static("[b]Diagnostics[/b]")
        yield Static("", id="check-list")
        with Horizontal(id="actions"):
            yield Button("Re-run", id="btn-rerun", variant="primary")

    def refresh_from_disk(self) -> None:
        results = _run_checks(self.root)
        body = "\n".join(f"{c.symbol} {c.note}" for c in results)
        self.query_one("#check-list", Static).update(body or "(no checks ran)")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-rerun":
            self.refresh_from_disk()
            self.set_status("diagnostics refreshed")
