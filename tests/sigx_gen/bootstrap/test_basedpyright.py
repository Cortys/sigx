from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

from sigx_gen.bootstrap.basedpyright import _basedpyright_command, generate_baseline_stubs


def test_basedpyright_command_uses_project_and_not_output(monkeypatch) -> None:
    monkeypatch.setattr("sigx_gen.bootstrap.basedpyright.shutil.which", lambda _: "/usr/bin/basedpyright")

    command = _basedpyright_command(package="pkg", project_file=Path("/tmp/pyrightconfig.json"))

    assert command == [
        "basedpyright",
        "--project",
        "/tmp/pyrightconfig.json",
        "--createstub",
        "pkg",
    ]
    assert "--output" not in command


def test_basedpyright_command_falls_back_to_python_module(monkeypatch) -> None:
    monkeypatch.setattr("sigx_gen.bootstrap.basedpyright.shutil.which", lambda _: None)

    command = _basedpyright_command(package="pkg", project_file=Path("/tmp/pyrightconfig.json"))

    assert command == [
        sys.executable,
        "-m",
        "basedpyright",
        "--project",
        "/tmp/pyrightconfig.json",
        "--createstub",
        "pkg",
    ]
    assert "--output" not in command


def test_generate_baseline_stubs_uses_project_config(monkeypatch, tmp_path: Path) -> None:
    src_root = tmp_path / "src"
    out_root = tmp_path / "stubs"
    src_root.mkdir(parents=True)

    monkeypatch.setattr("sigx_gen.bootstrap.basedpyright.shutil.which", lambda _: "/usr/bin/basedpyright")

    project_files: list[Path] = []
    package_calls: list[str] = []

    def fake_run(command, *, check: bool, capture_output: bool, text: bool, env: dict[str, str]):
        assert check is False
        assert capture_output is True
        assert text is True
        assert env["PYTHONPATH"] == str(src_root)
        assert "--output" not in command
        assert "--project" in command
        assert "--createstub" in command

        project_path = Path(command[command.index("--project") + 1])
        package = command[command.index("--createstub") + 1]
        project_files.append(project_path)
        package_calls.append(package)

        config = json.loads(project_path.read_text(encoding="utf-8"))
        assert config["stubPath"] == str(out_root)
        assert config["include"] == [str(src_root)]
        assert config["executionEnvironments"] == [{"root": str(src_root), "extraPaths": [str(src_root)]}]

        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr("sigx_gen.bootstrap.basedpyright.subprocess.run", fake_run)

    generate_baseline_stubs(
        src_root=src_root,
        out_root=out_root,
        module_names=("pkg.a", "pkg.b", "other.mod"),
    )

    assert package_calls == ["other", "pkg"]
    assert len(project_files) == 2
    assert project_files[0] == project_files[1]
