from __future__ import annotations

from dataclasses import dataclass
import functools
import inspect
import logging
from pathlib import Path
import time
from typing import Callable, cast, Optional

import typer

from core.launcher import Launcher
from core.models import DolCtlError

from . import __version__


app = typer.Typer(add_completion=False, no_args_is_help=True)
instance_app = typer.Typer(no_args_is_help=True)
instance_mod_app = typer.Typer(no_args_is_help=True)
version_app = typer.Typer(no_args_is_help=True)
mod_app = typer.Typer(no_args_is_help=True)
channel_app = typer.Typer(no_args_is_help=True)


@dataclass(slots=True)
class CliState:
    root: Path | None
    verbose: bool
    launcher: Launcher | None = None


def _state(ctx: typer.Context) -> CliState:
    if not isinstance(ctx.obj, CliState):
        raise RuntimeError("CLI context was not initialised")
    return ctx.obj


def _launcher(ctx: typer.Context) -> Launcher:
    state = _state(ctx)
    if state.launcher is None:
        state.launcher = Launcher.open(state.root)
        state.launcher.configure_logging(verbose=state.verbose)
    return state.launcher


def _extract_context(
    signature: inspect.Signature, args: tuple[object, ...], kwargs: dict[str, object]
) -> typer.Context | None:
    names = list(signature.parameters)
    if "ctx" not in names:
        return None
    value = kwargs.get("ctx")
    if isinstance(value, typer.Context):
        return value
    index = names.index("ctx")
    if index < len(args) and isinstance(args[index], typer.Context):
        return cast(typer.Context, args[index])
    return None


def with_errors(function: Callable):
    signature = inspect.signature(function)

    @functools.wraps(function)
    def wrapped(*args: object, **kwargs: object):
        try:
            return function(*args, **kwargs)
        except (typer.Exit, typer.Abort, typer.BadParameter):
            raise
        except DolCtlError as exc:
            logger = logging.getLogger("dolctl")
            if logger.handlers:
                logger.error("%s", exc, exc_info=exc)
            typer.echo(f"Error: {exc}", err=True)
            raise typer.Exit(1) from exc
        except Exception as exc:
            logger = logging.getLogger("dolctl")
            if logger.handlers:
                logger.exception("Unexpected launcher failure")
            typer.echo(f"Unexpected error: {exc}", err=True)
            context = _extract_context(signature, args, kwargs)
            if context is not None and _state(context).verbose:
                typer.echo("See the traceback in the launcher log.", err=True)
            raise typer.Exit(1) from exc

    setattr(wrapped, "__signature__", signature)
    return wrapped


def _progress(label: str) -> Callable[[int, int | None], None]:
    state = {"last_time": 0.0, "last_percent": -1}

    def report(downloaded: int, total: int | None) -> None:
        now = time.monotonic()
        percent = int(downloaded * 100 / total) if total else -1
        complete = total is not None and downloaded >= total
        if not complete and now - state["last_time"] < 0.25:
            return
        if total and not complete and percent == state["last_percent"]:
            return
        state["last_time"] = now
        state["last_percent"] = percent
        downloaded_mb = downloaded / 1_048_576
        if total:
            typer.echo(
                f"{label}: {downloaded_mb:.1f}/{total / 1_048_576:.1f} MB ({percent}%)",
                err=True,
            )
        else:
            typer.echo(f"{label}: {downloaded_mb:.1f} MB", err=True)

    return report


@app.callback()
def main(
    ctx: typer.Context,
    root: Optional[Path] = typer.Option(None, "--root", "-r", help="Launcher ROOT"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
    version: bool = typer.Option(False, "--version", help="Show version and exit"),
) -> None:
    logger = logging.getLogger("dolctl")
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()
    ctx.obj = CliState(root=root, verbose=verbose)
    if version:
        typer.echo(__version__)
        raise typer.Exit()


@app.command()
@with_errors
def init(directory: Path) -> None:
    launcher = Launcher.initialise(directory)
    launcher.configure_logging()
    typer.echo(f"Initialised launcher root: {launcher.root}")


@app.command()
@with_errors
def where(ctx: typer.Context) -> None:
    typer.echo(_launcher(ctx).root)


@app.command()
@with_errors
def tui(ctx: typer.Context) -> None:
    launcher = _launcher(ctx)
    from dolctl.tui.app import DolctlApp

    DolctlApp(launcher).run()


@app.command()
@with_errors
def doctor(ctx: typer.Context) -> None:
    report = _launcher(ctx).doctor()
    for check in report.checks:
        typer.echo(f"{'OK' if check.ok else 'FAIL'}\t{check.message}")
    if not report.ok:
        raise typer.Exit(1)


@instance_app.command("list")
@with_errors
def instance_list(ctx: typer.Context) -> None:
    launcher = _launcher(ctx)
    active = launcher.active_instance()
    for profile in launcher.instances():
        marker = "*" if profile.name == active else " "
        typer.echo(
            f"{marker} {profile.name}\t{profile.version_id or '-'}\t"
            f"{len(profile.mod_order)} mods"
        )


@instance_app.command("create")
@with_errors
def instance_create(
    ctx: typer.Context,
    name: str,
    version: Optional[str] = typer.Option(None, "--version"),
    select: bool = typer.Option(False, "--select"),
) -> None:
    launcher = _launcher(ctx)
    profile = launcher.create_instance(name, version_id=version)
    if select:
        launcher.select_instance(name)
    typer.echo(f"Created instance: {profile.name}")


@instance_app.command("select")
@with_errors
def instance_select(ctx: typer.Context, name: str) -> None:
    _launcher(ctx).select_instance(name)
    typer.echo(f"Selected instance: {name}")


@instance_app.command("show")
@with_errors
def instance_show(
    ctx: typer.Context,
    name: Optional[str] = typer.Argument(None),
) -> None:
    profile = _launcher(ctx).instance(name)
    typer.echo(f"name:         {profile.name}")
    typer.echo(f"version:      {profile.version_id or '-'}")
    typer.echo(
        f"port:         {profile.port if profile.port is not None else 'default'}"
    )
    browser = profile.open_browser
    typer.echo(f"open_browser: {browser if browser is not None else 'default'}")
    typer.echo("mods:")
    for index, mod_id in enumerate(profile.mod_order, 1):
        typer.echo(f"  {index}. {mod_id}")


@instance_app.command("configure")
@with_errors
def instance_configure(
    ctx: typer.Context,
    name: Optional[str] = typer.Argument(None),
    version: Optional[str] = typer.Option(None, "--version"),
    clear_version: bool = typer.Option(False, "--clear-version"),
    port: Optional[int] = typer.Option(None, "--port"),
    clear_port: bool = typer.Option(False, "--clear-port"),
    browser: Optional[bool] = typer.Option(None, "--browser/--no-browser"),
    default_browser: bool = typer.Option(False, "--default-browser"),
) -> None:
    if version is not None and clear_version:
        raise typer.BadParameter("Use either --version or --clear-version")
    if port is not None and clear_port:
        raise typer.BadParameter("Use either --port or --clear-port")
    if browser is not None and default_browser:
        raise typer.BadParameter(
            "Use either --browser/--no-browser or --default-browser"
        )
    launcher = _launcher(ctx)
    instance = launcher.active_instance(name)
    fields: dict[str, object] = {}
    if version is not None or clear_version:
        fields["version_id"] = None if clear_version else version
    if port is not None or clear_port:
        fields["port"] = None if clear_port else port
    if browser is not None or default_browser:
        fields["open_browser"] = None if default_browser else browser
    if not fields:
        raise typer.BadParameter("No configuration change was supplied")
    profile = launcher.configure_instance(instance, **fields)
    typer.echo(f"Updated instance: {profile.name}")


@instance_app.command("delete")
@with_errors
def instance_delete(ctx: typer.Context, name: str) -> None:
    _launcher(ctx).delete_instance(name)
    typer.echo(f"Deleted instance: {name}")


@instance_mod_app.command("list")
@with_errors
def instance_mod_list(ctx: typer.Context, instance: Optional[str] = None) -> None:
    profile = _launcher(ctx).instance(instance)
    for index, mod_id in enumerate(profile.mod_order, 1):
        typer.echo(f"{index}. {mod_id}")


@instance_mod_app.command("add")
@with_errors
def instance_mod_add(
    ctx: typer.Context, mod_id: str, instance: Optional[str] = None
) -> None:
    launcher = _launcher(ctx)
    name = launcher.active_instance(instance)
    launcher.enable_mod(name, mod_id)
    typer.echo(f"Enabled {mod_id} in {name}")


@instance_mod_app.command("remove")
@with_errors
def instance_mod_remove(
    ctx: typer.Context, mod_id: str, instance: Optional[str] = None
) -> None:
    launcher = _launcher(ctx)
    name = launcher.active_instance(instance)
    launcher.disable_mod(name, mod_id)
    typer.echo(f"Disabled {mod_id} in {name}")


@instance_mod_app.command("reorder")
@with_errors
def instance_mod_reorder(
    ctx: typer.Context,
    mod_ids: list[str],
    instance: Optional[str] = None,
) -> None:
    launcher = _launcher(ctx)
    name = launcher.active_instance(instance)
    launcher.reorder_instance_mods(name, mod_ids)
    typer.echo(f"Updated mod order in {name}")


@version_app.command("list")
@with_errors
def version_list(ctx: typer.Context) -> None:
    for version in _launcher(ctx).versions():
        typer.echo(
            f"{version.id}\t{version.channel}\t{version.display_name}\t"
            f"{version.installed_at}"
        )


@version_app.command("remote")
@with_errors
def version_remote(
    ctx: typer.Context,
    channel: Optional[str] = typer.Option(None, "--channel"),
    refresh: bool = typer.Option(False, "--refresh"),
) -> None:
    launcher = _launcher(ctx)
    names = (
        [channel]
        if channel
        else [name for name, config in launcher.channels() if config.kind == "game"]
    )
    for name in names:
        typer.echo(f"[{name}]")
        for version in launcher.remote_versions(name, refresh=refresh):
            typer.echo(f"{version.id}\t{version.published_at}\t{version.asset_name}")


def _install_version(
    launcher: Launcher,
    selector: str | None,
    channel: str | None,
    file: Path | None,
    source_dir: Path | None,
    version_id: str | None,
    force: bool,
) -> str:
    selected = sum(value is not None for value in (file, source_dir))
    if selected > 1:
        raise typer.BadParameter("Use only one of --file or --dir")
    if selected and selector is not None:
        raise typer.BadParameter(
            "A remote selector cannot be combined with --file/--dir"
        )
    if not selected and version_id is not None:
        raise typer.BadParameter("--as is only available for local imports")
    if file is not None:
        return launcher.install_version_file(
            file,
            version_id=version_id,
            channel=channel or "local",
            force=force,
        )
    if source_dir is not None:
        return launcher.install_version_directory(
            source_dir,
            version_id=version_id,
            channel=channel or "local",
            force=force,
        )
    return launcher.install_remote_version(
        channel or "modloader",
        selector or "latest",
        force=force,
        progress=_progress("download"),
    )


@version_app.command("install")
@with_errors
def version_install(
    ctx: typer.Context,
    selector: Optional[str] = typer.Argument(None),
    channel: Optional[str] = typer.Option(None, "--channel"),
    file: Optional[Path] = typer.Option(None, "--file"),
    source_dir: Optional[Path] = typer.Option(None, "--dir"),
    version_id: Optional[str] = typer.Option(None, "--as"),
    force: bool = typer.Option(False, "--force"),
) -> None:
    installed = _install_version(
        _launcher(ctx), selector, channel, file, source_dir, version_id, force
    )
    typer.echo(f"Installed version: {installed}")


@version_app.command("remove")
@with_errors
def version_remove(
    ctx: typer.Context,
    version_id: str,
    force: bool = typer.Option(False, "--force"),
) -> None:
    result = _launcher(ctx).remove_version(version_id, force=force)
    typer.echo(f"Removed version: {version_id}")
    if result.affected_profiles:
        typer.echo("Detached instances: " + ", ".join(result.affected_profiles))


@mod_app.command("list")
@with_errors
def mod_list(ctx: typer.Context) -> None:
    for mod in _launcher(ctx).mods():
        typer.echo(f"{mod.id}\t{mod.name}\t{mod.version}\t{mod.author}")


@mod_app.command("add")
@with_errors
def mod_add(
    ctx: typer.Context,
    source: str,
    mod_id: Optional[str] = typer.Option(None, "--id"),
    force: bool = typer.Option(False, "--force"),
) -> None:
    installed = _launcher(ctx).install_mod(
        source,
        mod_id=mod_id,
        force=force,
        progress=_progress("download"),
    )
    typer.echo(f"Installed mod: {installed}")


@mod_app.command("remote")
@with_errors
def mod_remote(
    ctx: typer.Context,
    channel: Optional[str] = typer.Option(None, "--channel"),
    refresh: bool = typer.Option(False, "--refresh"),
) -> None:
    launcher = _launcher(ctx)
    names = (
        [channel]
        if channel
        else [name for name, config in launcher.channels() if config.kind == "mod"]
    )
    for name in names:
        typer.echo(f"[{name}]")
        for release in launcher.remote_mods(name, refresh=refresh):
            typer.echo(f"{release.id}\t{release.published_at}\t{release.asset_name}")


@mod_app.command("install")
@with_errors
def mod_install(
    ctx: typer.Context,
    selector: str = typer.Argument("latest"),
    channel: str = typer.Option(..., "--channel"),
    mod_id: Optional[str] = typer.Option(None, "--id"),
    force: bool = typer.Option(False, "--force"),
) -> None:
    installed = _launcher(ctx).install_remote_mod(
        channel,
        selector,
        mod_id=mod_id,
        force=force,
        progress=_progress("download"),
    )
    typer.echo(f"Installed mod: {installed}")


@mod_app.command("info")
@with_errors
def mod_info(ctx: typer.Context, mod_id: str) -> None:
    mod = _launcher(ctx).mod(mod_id)
    typer.echo(f"id:          {mod.id}")
    typer.echo(f"name:        {mod.name}")
    typer.echo(f"version:     {mod.version}")
    typer.echo(f"author:      {mod.author}")
    typer.echo(f"description: {mod.description}")
    typer.echo(f"source:      {mod.source_ref}")


@mod_app.command("remove")
@with_errors
def mod_remove(ctx: typer.Context, mod_id: str) -> None:
    result = _launcher(ctx).remove_mod(mod_id)
    typer.echo(f"Removed mod: {mod_id}")
    if result.affected_profiles:
        typer.echo("Updated instances: " + ", ".join(result.affected_profiles))


@channel_app.command("list")
@with_errors
def channel_list(ctx: typer.Context) -> None:
    for name, channel in _launcher(ctx).channels():
        typer.echo(
            f"{name}\t{channel.kind}\t{channel.provider}\t{channel.repo}\t"
            f"{channel.asset_regex}"
        )


@channel_app.command("preset")
@with_errors
def channel_preset() -> None:
    for name, preset in Launcher.channel_presets():
        typer.echo(f"{name}\t{preset.kind}\t{preset.repo}\t{preset.description}")


@channel_app.command("add")
@with_errors
def channel_add(
    ctx: typer.Context,
    name: str,
    preset: Optional[str] = typer.Option(None, "--preset"),
    kind: Optional[str] = typer.Option(None, "--kind"),
    repo: Optional[str] = typer.Option(None, "--repo"),
    asset_regex: Optional[str] = typer.Option(None, "--asset-regex"),
    force: bool = typer.Option(False, "--force"),
) -> None:
    channel = _launcher(ctx).add_channel(
        name,
        preset=preset,
        kind=kind,
        repo=repo,
        asset_regex=asset_regex,
        force=force,
    )
    typer.echo(f"Added source: {name} ({channel.repo})")


@channel_app.command("remove")
@with_errors
def channel_remove(ctx: typer.Context, name: str) -> None:
    _launcher(ctx).remove_channel(name)
    typer.echo(f"Removed source: {name}")


@app.command()
@with_errors
def build(
    ctx: typer.Context,
    instance: Optional[str] = typer.Argument(None),
    clean: bool = typer.Option(False, "--clean"),
) -> None:
    result = _launcher(ctx).build(instance, clean=clean)
    typer.echo(f"{result.status}: {result.profile} -> {result.output_dir}")


@app.command()
@with_errors
def run(
    ctx: typer.Context,
    instance: Optional[str] = typer.Argument(None),
    port: Optional[int] = typer.Option(None, "--port"),
    no_browser: bool = typer.Option(False, "--no-browser"),
    allow_lan: bool = typer.Option(False, "--allow-lan"),
    clean: bool = typer.Option(False, "--clean"),
) -> None:
    session = _launcher(ctx).prepare_run(
        instance,
        port=port,
        open_browser=False if no_browser else None,
        allow_lan=allow_lan,
        clean=clean,
    )
    typer.echo(f"Serving {session.url}")
    session.open_browser()
    try:
        session.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        session.close()


@app.command()
@with_errors
def serve(
    ctx: typer.Context,
    instance: Optional[str] = typer.Argument(None),
    port: Optional[int] = typer.Option(None, "--port"),
    allow_lan: bool = typer.Option(False, "--allow-lan"),
) -> None:
    session = _launcher(ctx).prepare_serve(
        instance,
        port=port,
        allow_lan=allow_lan,
    )
    typer.echo(f"Serving {session.url}")
    try:
        session.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        session.close()


app.add_typer(instance_app, name="instance")
instance_app.add_typer(instance_mod_app, name="mod")
app.add_typer(version_app, name="version")
app.add_typer(mod_app, name="mod")
app.add_typer(channel_app, name="channel")
