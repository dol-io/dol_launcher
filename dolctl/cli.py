from __future__ import annotations

from pathlib import Path
from typing import Optional
import functools
import inspect

import click

import typer

from . import __version__
from core.build import build_runtime
from core.mods import (
    add_mod_from_zip,
    get_mod_info,
    list_mods,
    remove_mod,
)
from core.profiles import (
    add_mod_to_profile,
    create_profile,
    get_profile,
    list_profiles,
    remove_mod_from_profile,
    set_active_profile,
    set_profile_version,
)
from core.root import init_root, load_config, load_state, resolve_root
from core.run import prepare_run
from core.serve import create_server
from core.versions import (
    install_from_dir,
    install_from_file,
    install_from_remote,
    list_installed,
    list_remote_versions,
)
from infra.log import log_error
from infra.open import open_browser
from core.models import DolCtlError

app = typer.Typer(add_completion=False)
version_app = typer.Typer()
version_remote_app = typer.Typer()
profile_app = typer.Typer()
profile_mod_app = typer.Typer()
mod_app = typer.Typer()


def _get_root(ctx: typer.Context) -> Path:
    cli_root = ctx.obj.get("root") if ctx.obj else None
    return resolve_root(cli_root)


def _resolve_profile_name(root: Path, profile_name: Optional[str]) -> str:
    if profile_name:
        return profile_name
    state = load_state(root)
    if state.active_profile:
        return state.active_profile
    config = load_config(root)
    return config.default_profile


def _handle_error(ctx: typer.Context, exc: DolCtlError) -> None:
    root = None
    try:
        root = _get_root(ctx)
    except DolCtlError:
        root = None
    if root is not None:
        log_error(root, str(exc), exc)
    typer.echo(f"Error: {exc}", err=True)
    raise typer.Exit(code=1)


def with_errors(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        ctx = click.get_current_context(silent=True)
        try:
            return func(*args, **kwargs)
        except DolCtlError as exc:
            if ctx is None:
                typer.echo(f"Error: {exc}", err=True)
                raise typer.Exit(code=1)
            _handle_error(ctx, exc)

    wrapper.__signature__ = inspect.signature(func)
    return wrapper


@app.callback(invoke_without_command=True)
@with_errors
def main(
    ctx: typer.Context,
    root: Optional[Path] = typer.Option(None, "--root", "-r", help="Root directory"),
    version: bool = typer.Option(False, "--version", help="Show version"),
) -> None:
    ctx.obj = {"root": root}
    if version:
        typer.echo(__version__)
        raise typer.Exit()


@app.command()
@with_errors
def init(directory: Path = typer.Argument(..., help="Directory to initialize")) -> None:
    init_root(directory)
    typer.echo(f"Initialized root at {directory}")


@app.command()
@with_errors
def where(ctx: typer.Context) -> None:
    root = _get_root(ctx)
    typer.echo(str(root))


@app.command()
@with_errors
def doctor(ctx: typer.Context) -> None:
    root = _get_root(ctx)
    missing: list[str] = []
    for rel in [".dolctl", "versions", "profiles", "runtime"]:
        if not (root / rel).exists():
            missing.append(rel)
    if missing:
        typer.echo("Missing directories:")
        for rel in missing:
            typer.echo(f"- {rel}")
        raise typer.Exit(code=1)
    config = load_config(root)
    if not config.channels:
        typer.echo("No channels configured. Edit .dolctl/config.toml to add channels.")
    typer.echo("OK")


@version_app.command("list")
@with_errors
def version_list(ctx: typer.Context) -> None:
    root = _get_root(ctx)
    versions = list_installed(root)
    if not versions:
        typer.echo("No versions installed")
        return
    for version in versions:
        typer.echo(f"{version.id}\t{version.channel}\t{version.installed_at}")


@version_remote_app.command("list")
@with_errors
def version_remote_list(
    ctx: typer.Context,
    channel: Optional[str] = typer.Option(None, "--channel"),
    refresh: bool = typer.Option(False, "--refresh"),
) -> None:
    root = _get_root(ctx)
    config = load_config(root)
    channels = [channel] if channel else list(config.channels.keys())
    if not channels:
        raise DolCtlError("No channels configured")
    for name in channels:
        typer.echo(f"Channel: {name}")
        versions = list_remote_versions(root, name, refresh=refresh)
        if not versions:
            typer.echo("  (none)")
            continue
        for version in versions:
            typer.echo(f"  {version.id}\t{version.published_at}\t{version.asset_name}")


@app.command()
@with_errors
def install(
    ctx: typer.Context,
    selector: Optional[str] = typer.Argument(
        None, help="Version selector (e.g., latest, 0.5.3)"
    ),
    channel: str = typer.Option("vanilla", "--channel"),
    file: Optional[Path] = typer.Option(None, "--file", help="Install from zip"),
    source_dir: Optional[Path] = typer.Option(
        None, "--dir", help="Install from directory"
    ),
    version_id: Optional[str] = typer.Option(None, "--as", help="Override version id"),
    force: bool = typer.Option(False, "--force"),
) -> None:
    root = _get_root(ctx)
    if file:
        installed = install_from_file(root, file, version_id, channel, force=force)
    elif source_dir:
        installed = install_from_dir(root, source_dir, version_id, channel, force=force)
    else:
        if not selector:
            raise DolCtlError("Selector required for remote install")
        installed = install_from_remote(root, channel, selector, force=force)
    typer.echo(f"Installed: {installed}")


@app.command("use")
@with_errors
def use_version(
    ctx: typer.Context,
    version_id: str = typer.Argument(..., help="Installed version id"),
    profile: Optional[str] = typer.Option(None, "--profile"),
) -> None:
    root = _get_root(ctx)
    profile_name = _resolve_profile_name(root, profile)
    set_profile_version(root, profile_name, version_id)
    typer.echo(f"Profile {profile_name} now uses {version_id}")


@profile_app.command("list")
@with_errors
def profile_list(ctx: typer.Context) -> None:
    root = _get_root(ctx)
    profiles = list_profiles(root)
    if not profiles:
        typer.echo("No profiles")
        return
    for name in profiles:
        typer.echo(name)


@profile_app.command("create")
@with_errors
def profile_create(ctx: typer.Context, name: str = typer.Argument(...)) -> None:
    root = _get_root(ctx)
    create_profile(root, name)
    typer.echo(f"Created profile: {name}")


@profile_app.command("use")
@with_errors
def profile_use(ctx: typer.Context, name: str = typer.Argument(...)) -> None:
    root = _get_root(ctx)
    set_active_profile(root, name)
    typer.echo(f"Active profile: {name}")


@profile_app.command("set-version")
@with_errors
def profile_set_version(
    ctx: typer.Context,
    version_id: str = typer.Argument(...),
    profile: Optional[str] = typer.Option(None, "--profile"),
) -> None:
    root = _get_root(ctx)
    profile_name = _resolve_profile_name(root, profile)
    set_profile_version(root, profile_name, version_id)
    typer.echo(f"Profile {profile_name} now uses {version_id}")


# ---------------------------------------------------------------------------
# mod commands:  dolctl mod list / add / remove / info
# ---------------------------------------------------------------------------


@mod_app.command("list")
@with_errors
def mod_list(ctx: typer.Context) -> None:
    root = _get_root(ctx)
    mods = list_mods(root)
    if not mods:
        typer.echo("No mods installed")
        return
    for m in mods:
        typer.echo(f"{m.id}\t{m.name}\t{m.version}")


@mod_app.command("add")
@with_errors
def mod_add(
    ctx: typer.Context,
    path_or_url: str = typer.Argument(..., help="Path to .mod.zip or a URL"),
    mod_id: Optional[str] = typer.Option(None, "--id", help="Override mod id"),
) -> None:
    root = _get_root(ctx)
    installed_id = add_mod_from_zip(root, path_or_url, mod_id)
    typer.echo(f"Installed mod: {installed_id}")


@mod_app.command("remove")
@with_errors
def mod_remove(
    ctx: typer.Context,
    mod_id: str = typer.Argument(...),
) -> None:
    root = _get_root(ctx)
    remove_mod(root, mod_id)
    typer.echo(f"Removed mod: {mod_id}")


@mod_app.command("info")
@with_errors
def mod_info(
    ctx: typer.Context,
    mod_id: str = typer.Argument(...),
) -> None:
    root = _get_root(ctx)
    m = get_mod_info(root, mod_id)
    typer.echo(f"id:          {m.id}")
    typer.echo(f"name:        {m.name}")
    typer.echo(f"version:     {m.version}")
    typer.echo(f"author:      {m.author}")
    typer.echo(f"description: {m.description}")
    typer.echo(f"source:      {m.source}")
    typer.echo(f"source_ref:  {m.source_ref}")
    typer.echo(f"installed:   {m.installed_at}")


# ---------------------------------------------------------------------------
# profile mod commands:  dolctl profile mod add / remove / list
# ---------------------------------------------------------------------------


@profile_mod_app.command("add")
@with_errors
def profile_mod_add(
    ctx: typer.Context,
    mod_id: str = typer.Argument(...),
    profile: Optional[str] = typer.Option(None, "--profile"),
) -> None:
    root = _get_root(ctx)
    profile_name = _resolve_profile_name(root, profile)
    add_mod_to_profile(root, profile_name, mod_id)
    typer.echo(f"Added {mod_id} to profile {profile_name}")


@profile_mod_app.command("remove")
@with_errors
def profile_mod_remove(
    ctx: typer.Context,
    mod_id: str = typer.Argument(...),
    profile: Optional[str] = typer.Option(None, "--profile"),
) -> None:
    root = _get_root(ctx)
    profile_name = _resolve_profile_name(root, profile)
    remove_mod_from_profile(root, profile_name, mod_id)
    typer.echo(f"Removed {mod_id} from profile {profile_name}")


@profile_mod_app.command("list")
@with_errors
def profile_mod_list(
    ctx: typer.Context,
    profile: Optional[str] = typer.Option(None, "--profile"),
) -> None:
    root = _get_root(ctx)
    profile_name = _resolve_profile_name(root, profile)
    p = get_profile(root, profile_name)
    if not p.mod_order:
        typer.echo("No mods in profile")
        return
    for i, mod_id in enumerate(p.mod_order, 1):
        typer.echo(f"{i}. {mod_id}")


# ---------------------------------------------------------------------------
# build / run / serve
# ---------------------------------------------------------------------------


@app.command()
@with_errors
def build(
    ctx: typer.Context,
    profile: Optional[str] = typer.Option(None, "--profile"),
) -> None:
    root = _get_root(ctx)
    profile_name = _resolve_profile_name(root, profile)
    result = build_runtime(root, profile_name, clean=True)
    typer.echo(f"Built runtime for {profile_name} at {result.output_dir}")


@app.command()
@with_errors
def run(
    ctx: typer.Context,
    profile: Optional[str] = typer.Option(None, "--profile"),
    port: Optional[int] = typer.Option(None, "--port"),
    no_browser: bool = typer.Option(False, "--no-browser"),
    allow_lan: bool = typer.Option(
        False, "--allow-lan", help="Allow LAN access (bind 0.0.0.0)"
    ),
) -> None:
    root = _get_root(ctx)
    profile_name = _resolve_profile_name(root, profile)
    open_browser_override = False if no_browser else None
    result = prepare_run(
        root, profile_name, port, open_browser_override, allow_lan=allow_lan
    )
    typer.echo(f"Serving {result.url}")
    if result.open_browser:
        open_browser(result.url, enabled=True)
    try:
        result.server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        result.server.server_close()


@app.command()
@with_errors
def serve(
    ctx: typer.Context,
    profile: Optional[str] = typer.Option(None, "--profile"),
    port: Optional[int] = typer.Option(None, "--port"),
    allow_lan: bool = typer.Option(
        False, "--allow-lan", help="Allow LAN access (bind 0.0.0.0)"
    ),
) -> None:
    root = _get_root(ctx)
    profile_name = _resolve_profile_name(root, profile)
    profile_data = get_profile(root, profile_name)
    config = load_config(root)
    if port is not None:
        port_choice = port
        allow_fallback = False
    elif profile_data.port is not None:
        port_choice = profile_data.port
        allow_fallback = True
    else:
        port_choice = config.default_port
        allow_fallback = True
    merged_dir = root / "runtime" / profile_name / "merged"
    if not merged_dir.exists():
        raise DolCtlError(f"Runtime not built for profile: {profile_name}")
    # Resolve entry HTML name from version manifest
    from infra.toml import read_toml
    from core.models import version_manifest_from_dict

    entry_name = "index.html"
    if profile_data.version_id:
        manifest_path = root / "versions" / profile_data.version_id / ".manifest.toml"
        if manifest_path.exists():
            vm = version_manifest_from_dict(read_toml(manifest_path))
            entry_name = vm.entry
    host = "0.0.0.0" if allow_lan else "127.0.0.1"
    server, actual_port = create_server(
        merged_dir,
        host=host,
        port=port_choice,
        allow_fallback=allow_fallback,
        entry_name=entry_name,
        allow_lan=allow_lan,
    )
    url = f"http://127.0.0.1:{actual_port}/"
    typer.echo(f"Serving {url}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


app.add_typer(version_app, name="version")
version_app.add_typer(version_remote_app, name="remote")
app.add_typer(profile_app, name="profile")
profile_app.add_typer(profile_mod_app, name="mod")
app.add_typer(mod_app, name="mod")
