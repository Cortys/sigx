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

        if package == "pkg":
            (out_root / "pkg").mkdir(parents=True, exist_ok=True)
            (out_root / "pkg" / "a.pyi").write_text("def a() -> None: ...\n", encoding="utf-8")
            (out_root / "pkg" / "b.pyi").write_text("def b() -> None: ...\n", encoding="utf-8")
        if package == "other":
            (out_root / "other").mkdir(parents=True, exist_ok=True)
            (out_root / "other" / "mod.pyi").write_text("def mod() -> None: ...\n", encoding="utf-8")

        config = json.loads(project_path.read_text(encoding="utf-8"))
        assert config["stubPath"] == str(out_root)
        assert config["include"] == [str(src_root)]
        assert config["executionEnvironments"] == [{"root": str(src_root), "extraPaths": [str(src_root)]}]

        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr("sigx_gen.bootstrap.basedpyright.subprocess.run", fake_run)

    generate_baseline_stubs(
        src_root=src_root,
        out_root=out_root,
        module_targets=(
            ("pkg.a", out_root / "pkg" / "a.pyi"),
            ("pkg.b", out_root / "pkg" / "b.pyi"),
            ("other.mod", out_root / "other" / "mod.pyi"),
        ),
    )

    assert package_calls == ["other", "pkg"]
    assert len(project_files) == 2
    assert project_files[0] == project_files[1]


def test_generate_baseline_stubs_falls_back_to_missing_modules(monkeypatch, tmp_path: Path) -> None:
    src_root = tmp_path / "src"
    out_root = tmp_path / "stubs"
    src_root.mkdir(parents=True)

    monkeypatch.setattr("sigx_gen.bootstrap.basedpyright.shutil.which", lambda _: "/usr/bin/basedpyright")

    package_calls: list[str] = []

    def fake_run(command, *, check: bool, capture_output: bool, text: bool, env: dict[str, str]):
        del check, capture_output, text, env
        package = command[command.index("--createstub") + 1]
        package_calls.append(package)

        if package == "pkg":
            (out_root / "pkg").mkdir(parents=True, exist_ok=True)
            (out_root / "pkg" / "a.pyi").write_text("def a() -> None: ...\n", encoding="utf-8")
        if package == "pkg.b":
            (out_root / "pkg").mkdir(parents=True, exist_ok=True)
            (out_root / "pkg" / "b.pyi").write_text("def b() -> None: ...\n", encoding="utf-8")

        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr("sigx_gen.bootstrap.basedpyright.subprocess.run", fake_run)

    generate_baseline_stubs(
        src_root=src_root,
        out_root=out_root,
        module_targets=(
            ("pkg.a", out_root / "pkg" / "a.pyi"),
            ("pkg.b", out_root / "pkg" / "b.pyi"),
        ),
    )

    assert package_calls == ["pkg", "pkg.b"]
    assert (out_root / "pkg" / "a.pyi").exists()
    assert (out_root / "pkg" / "b.pyi").exists()


def test_generate_baseline_stubs_generates_required_package_init_stubs(monkeypatch, tmp_path: Path) -> None:
    src_root = tmp_path / "src"
    out_root = tmp_path / "stubs"
    (src_root / "pkg" / "sub").mkdir(parents=True)
    (src_root / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    (src_root / "pkg" / "sub" / "__init__.py").write_text("", encoding="utf-8")

    monkeypatch.setattr("sigx_gen.bootstrap.basedpyright.shutil.which", lambda _: "/usr/bin/basedpyright")

    package_calls: list[str] = []

    def fake_run(command, *, check: bool, capture_output: bool, text: bool, env: dict[str, str]):
        del check, capture_output, text, env
        package = command[command.index("--createstub") + 1]
        package_calls.append(package)

        if package == "pkg":
            (out_root / "pkg" / "sub").mkdir(parents=True, exist_ok=True)
            (out_root / "pkg" / "sub" / "mod.pyi").write_text("def mod() -> None: ...\n", encoding="utf-8")
            (out_root / "pkg" / "__init__.pyi").write_text("", encoding="utf-8")
        if package == "pkg.sub":
            (out_root / "pkg" / "sub").mkdir(parents=True, exist_ok=True)
            (out_root / "pkg" / "sub" / "__init__.pyi").write_text("", encoding="utf-8")

        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr("sigx_gen.bootstrap.basedpyright.subprocess.run", fake_run)

    generate_baseline_stubs(
        src_root=src_root,
        out_root=out_root,
        module_targets=(("pkg.sub.mod", out_root / "pkg" / "sub" / "mod.pyi"),),
    )

    assert package_calls == ["pkg", "pkg.sub"]
    assert (out_root / "pkg" / "__init__.pyi").exists()
    assert (out_root / "pkg" / "sub" / "__init__.pyi").exists()


def test_generate_baseline_stubs_does_not_require_namespace_package_init_stubs(monkeypatch, tmp_path: Path) -> None:
    src_root = tmp_path / "src"
    out_root = tmp_path / "stubs"
    (src_root / "pkg" / "sub").mkdir(parents=True)

    monkeypatch.setattr("sigx_gen.bootstrap.basedpyright.shutil.which", lambda _: "/usr/bin/basedpyright")

    package_calls: list[str] = []

    def fake_run(command, *, check: bool, capture_output: bool, text: bool, env: dict[str, str]):
        del check, capture_output, text, env
        package = command[command.index("--createstub") + 1]
        package_calls.append(package)

        if package == "pkg":
            (out_root / "pkg" / "sub").mkdir(parents=True, exist_ok=True)
            (out_root / "pkg" / "sub" / "mod.pyi").write_text("def mod() -> None: ...\n", encoding="utf-8")

        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr("sigx_gen.bootstrap.basedpyright.subprocess.run", fake_run)

    generate_baseline_stubs(
        src_root=src_root,
        out_root=out_root,
        module_targets=(("pkg.sub.mod", out_root / "pkg" / "sub" / "mod.pyi"),),
    )

    assert package_calls == ["pkg"]
    assert not (out_root / "pkg" / "__init__.pyi").exists()
    assert not (out_root / "pkg" / "sub" / "__init__.pyi").exists()
