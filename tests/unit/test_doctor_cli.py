from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

from typer.testing import CliRunner

from core.launcher import Launcher
from dolctl.cli import app
from infra.toml import write_toml


runner = CliRunner()


def test_doctor_passes_for_fresh_root(launcher: Launcher) -> None:
    report = launcher.doctor()
    assert report.ok
    assert any(check.key == "profile.default" for check in report.checks)


def test_doctor_reports_missing_directory_without_crashing(launcher: Launcher) -> None:
    (launcher.root / "mods").rmdir()
    report = launcher.doctor()
    assert not report.ok
    assert any(
        check.key == "directory.mods" and not check.ok for check in report.checks
    )


def test_doctor_handles_non_object_runtime_metadata(
    launcher: Launcher, make_version_dir
) -> None:
    launcher.install_version_directory(make_version_dir(), version_id="game")
    launcher.configure_instance("default", version_id="game")
    runtime = launcher.root / "runtime" / "default"
    runtime.mkdir(parents=True)
    (runtime / "build_meta.json").write_text("[]", encoding="utf-8")
    report = launcher.doctor()
    runtime_check = next(
        check for check in report.checks if check.key == "runtime.default"
    )
    assert not runtime_check.ok


def test_doctor_reports_dangling_instance_references(launcher: Launcher) -> None:
    write_toml(
        launcher.root / "profiles" / "default" / "profile.toml",
        {
            "schema_version": 1,
            "name": "default",
            "version_id": "missing-game",
            "mod_order": ["missing-mod"],
        },
    )
    report = launcher.doctor()
    failed = {check.key for check in report.checks if not check.ok}
    assert "profile.default.version" in failed
    assert "profile.default.mods" in failed


def test_cli_init_and_instance_flow(tmp_path: Path) -> None:
    root = tmp_path / "game-root"
    initialised = runner.invoke(app, ["init", str(root)])
    assert initialised.exit_code == 0
    assert "Initialised launcher root" in initialised.stdout

    created = runner.invoke(
        app,
        ["--root", str(root), "instance", "create", "casual", "--select"],
    )
    assert created.exit_code == 0
    listed = runner.invoke(app, ["--root", str(root), "instance", "list"])
    assert listed.exit_code == 0
    assert "* casual" in listed.stdout
    shown = runner.invoke(app, ["--root", str(root), "instance", "show", "casual"])
    assert shown.exit_code == 0
    assert "name:         casual" in shown.stdout


def test_cli_local_version_defaults_to_local_channel(
    tmp_path: Path, make_version_zip
) -> None:
    root = tmp_path / "game-root"
    assert runner.invoke(app, ["init", str(root)]).exit_code == 0
    archive = make_version_zip()
    result = runner.invoke(
        app,
        [
            "--root",
            str(root),
            "version",
            "install",
            "--file",
            str(archive),
            "--as",
            "game",
        ],
    )
    assert result.exit_code == 0
    assert Launcher.open(root).version("game").channel == "local"


def test_cli_rejects_ambiguous_install_options(
    launcher: Launcher, make_version_zip
) -> None:
    archive = make_version_zip()
    result = runner.invoke(
        app,
        [
            "--root",
            str(launcher.root),
            "version",
            "install",
            "latest",
            "--file",
            str(archive),
        ],
    )
    assert result.exit_code == 2
    assert "cannot be combined" in result.stderr


def test_cli_formats_expected_errors(tmp_path: Path) -> None:
    result = runner.invoke(app, ["--root", str(tmp_path), "where"])
    assert result.exit_code == 1
    assert "Error: Not a dolctl root" in result.stderr
    assert "Traceback" not in result.stderr


def test_cli_module_does_not_import_textual() -> None:
    environment = dict(os.environ)
    environment.pop("PYTHONSTARTUP", None)
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; import dolctl.cli; raise SystemExit('textual' in sys.modules)",
        ],
        cwd=Path(__file__).parents[2],
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
