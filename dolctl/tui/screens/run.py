from __future__ import annotations

import logging
import threading
import webbrowser

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Checkbox, Input, RichLog, Select, Static

from core.build import build_runtime
from core.models import DolCtlError
from core.profiles import get_profile, list_profiles
from core.root import load_config, load_state
from core.serve import create_server
from core.versions import list_installed

from ..log_handler import RichLogHandler
from .base import RefreshableTab


class RunTab(RefreshableTab):
    """Combined build + serve pane with a live log."""

    DEFAULT_CSS = """
    RunTab #top { height: auto; padding-bottom: 1; }
    RunTab #top > Vertical { padding-right: 2; }
    RunTab #top Static.col-title { text-style: bold; }
    RunTab #opts { height: auto; }
    RunTab #opts Input { width: 20; }
    RunTab #actions { height: auto; padding-top: 1; }
    RunTab #actions Button { margin-right: 1; }
    RunTab RichLog { height: 1fr; border: round; }
    """

    _server = None
    _server_thread: threading.Thread | None = None
    _log_handler: RichLogHandler | None = None

    def compose(self) -> ComposeResult:
        with Horizontal(id="top"):
            with Vertical():
                yield Static("Profile", classes="col-title")
                yield Select([], id="profile-select", prompt="(active)")
                yield Checkbox("--clean (full rebuild)", id="opt-clean")
            with Vertical():
                yield Static("Server", classes="col-title")
                with Horizontal(id="opts"):
                    yield Static("Port: ")
                    yield Input(value="8799", id="port")
                yield Checkbox("--no-browser", id="opt-no-browser")
                yield Checkbox("--allow-lan", id="opt-allow-lan")
        with Horizontal(id="actions"):
            yield Button("Build", id="btn-build")
            yield Button("Run", id="btn-run", variant="primary")
            yield Button("Stop", id="btn-stop", variant="error", disabled=True)
        yield RichLog(id="log", highlight=False, markup=False)

    def on_mount(self) -> None:
        super().on_mount()
        # Attach our handler to the root dolctl logger so info-level
        # messages from core.* surface in the in-tab log pane.
        logger = logging.getLogger("dolctl")
        widget = self.query_one("#log", RichLog)
        self._log_handler = RichLogHandler(self.app, widget)
        logger.addHandler(self._log_handler)

    def on_unmount(self) -> None:
        if self._log_handler is not None:
            logging.getLogger("dolctl").removeHandler(self._log_handler)
            self._log_handler = None
        self._stop_server()

    def refresh_from_disk(self) -> None:
        profiles = list_profiles(self.root)
        select = self.query_one("#profile-select", Select)
        select.set_options([(p, p) for p in profiles])

    # ----- helpers ------------------------------------------------------

    def _profile_name(self) -> str:
        select = self.query_one("#profile-select", Select)
        if not select.is_blank():
            return str(select.value)
        state = load_state(self.root)
        config = load_config(self.root)
        return state.active_profile or config.default_profile

    def _opts(self) -> tuple[int, bool, bool, bool]:
        port_str = self.query_one("#port", Input).value.strip() or "8799"
        port = int(port_str)
        clean = self.query_one("#opt-clean", Checkbox).value
        no_browser = self.query_one("#opt-no-browser", Checkbox).value
        allow_lan = self.query_one("#opt-allow-lan", Checkbox).value
        return port, clean, no_browser, allow_lan

    # ----- buttons ------------------------------------------------------

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id
        if bid == "btn-build":
            self._build()
        elif bid == "btn-run":
            self.action_run()
        elif bid == "btn-stop":
            self._stop_server()

    def action_run(self) -> None:
        """Public entry point so other tabs (Home) can trigger Run."""
        self._run()

    def _build(self) -> None:
        profile = self._profile_name()
        _port, clean, _nb, _lan = self._opts()

        def worker() -> None:
            try:
                result = build_runtime(self.root, profile, clean=clean)
            except Exception as exc:  # noqa: BLE001 — surface unexpected build errors
                self.app.call_from_thread(self.set_status, f"build error: {exc}", "error")
                return
            self.app.call_from_thread(
                self.set_status, f"built {profile} → {result.output_dir}", "success")
            self.app.call_from_thread(self.notify_data_changed)

        self.set_status(f"building {profile}…")
        self.run_worker(worker, exclusive=True, thread=True)

    def _run(self) -> None:
        if self._server is not None:
            self.set_status("server already running; press Stop first", "warn")
            return

        profile_name = self._profile_name()
        port, clean, no_browser, allow_lan = self._opts()

        def worker() -> None:
            try:
                result = build_runtime(self.root, profile_name, clean=clean)
                profile = get_profile(self.root, profile_name)
                installed = {v.id: v for v in list_installed(self.root)}
                entry = (
                    installed[profile.version_id].entry
                    if profile.version_id in installed
                    else "index.html"
                )
                host = "0.0.0.0" if allow_lan else "127.0.0.1"
                server, actual_port = create_server(
                    result.output_dir,
                    host=host,
                    port=port,
                    allow_fallback=False,
                    entry_name=entry,
                    allow_lan=allow_lan,
                )
            except OSError as exc:
                self.app.call_from_thread(self.set_status, f"port error: {exc}", "error")
                return
            except Exception as exc:  # noqa: BLE001 — surface unexpected errors to status
                self.app.call_from_thread(self.set_status, f"error: {exc}", "error")
                return

            url = f"http://127.0.0.1:{actual_port}/"
            self._server = server
            self._server_thread = threading.Thread(
                target=server.serve_forever, daemon=True
            )
            self._server_thread.start()
            self.app.call_from_thread(self._on_server_started, url, no_browser)

        self.set_status(f"starting server for {profile_name}…")
        self.run_worker(worker, exclusive=True, thread=True)

    def _on_server_started(self, url: str, no_browser: bool) -> None:
        self.query_one("#btn-run", Button).disabled = True
        self.query_one("#btn-build", Button).disabled = True
        self.query_one("#btn-stop", Button).disabled = False
        self.set_status(f"serving {url}", "success")
        self.query_one("#log", RichLog).write(f"Serving {url}")
        if not no_browser:
            webbrowser.open(url)

    def _stop_server(self) -> None:
        if self._server is None:
            return
        server = self._server
        thread = self._server_thread
        self._server = None
        self._server_thread = None

        def shutdown() -> None:
            try:
                server.shutdown()
                server.server_close()
            except Exception:
                pass
            if thread is not None:
                thread.join(timeout=2.0)
            self.app.call_from_thread(self._on_server_stopped)

        # shutdown() blocks until serve_forever exits — do it in a worker
        self.run_worker(shutdown, thread=True)

    def _on_server_stopped(self) -> None:
        # Re-enable buttons safely; if widgets are gone (unmount), ignore.
        try:
            self.query_one("#btn-run", Button).disabled = False
            self.query_one("#btn-build", Button).disabled = False
            self.query_one("#btn-stop", Button).disabled = True
        except Exception:
            return
        self.set_status("server stopped", "success")
        self.query_one("#log", RichLog).write("Server stopped")
