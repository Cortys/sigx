"""basedpyright-backed baseline stub generation helpers."""

from __future__ import annotations

from collections.abc import Iterable
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


def generate_baseline_stubs(
    *,
    src_root: Path,
    out_root: Path,
    module_targets: Iterable[tuple[str, Path]],
) -> None:
    """Generate baseline stubs using basedpyright.

    Args:
        src_root: Source root to place on ``PYTHONPATH``.
        out_root: Stub output root.
        module_targets: Module names paired with expected stub file paths.

    Raises:
        RuntimeError: If basedpyright is unavailable or generation fails.
    """
    target_stub_paths = {module_name: stub_path for module_name, stub_path in module_targets if module_name}
    if not target_stub_paths:
        return
    required_package_stub_paths = _required_package_stub_paths(
        src_root=src_root,
        out_root=out_root,
        module_names=target_stub_paths,
    )
    expected_stub_paths = {**required_package_stub_paths, **target_stub_paths}
    top_level_packages = sorted({module_name.split(".")[0] for module_name in expected_stub_paths})

    out_root.mkdir(parents=True, exist_ok=True)
    attempted_targets: set[str] = set()

    with tempfile.TemporaryDirectory(prefix="sigx-gen-basedpyright-") as temp_dir:
        project_file = Path(temp_dir) / "pyrightconfig.json"
        _write_project_config(project_file=project_file, src_root=src_root, out_root=out_root)

        for package in top_level_packages:
            _run_basedpyright_command(
                command=_basedpyright_command(package=package, project_file=project_file),
                source_label=package,
                src_root=src_root,
            )
            attempted_targets.add(package)

        missing_modules = sorted(
            module_name
            for module_name, stub_path in expected_stub_paths.items()
            if not stub_path.exists() and module_name not in attempted_targets
        )
        for module_name in missing_modules:
            _run_basedpyright_command(
                command=_basedpyright_command(package=module_name, project_file=project_file),
                source_label=module_name,
                src_root=src_root,
            )

        still_missing = sorted(
            f"{module_name} -> {stub_path}"
            for module_name, stub_path in expected_stub_paths.items()
            if not stub_path.exists()
        )
        if still_missing:
            missing_report = ", ".join(still_missing)
            raise RuntimeError(f"basedpyright did not generate required module stubs: {missing_report}")


def _required_package_stub_paths(
    *,
    src_root: Path,
    out_root: Path,
    module_names: Iterable[str],
) -> dict[str, Path]:
    required: dict[str, Path] = {}
    for module_name in module_names:
        parts = module_name.split(".")
        for index in range(1, len(parts)):
            package_parts = parts[:index]
            package_init = src_root.joinpath(*package_parts, "__init__.py")
            if not package_init.exists():
                continue
            package_name = ".".join(package_parts)
            required[package_name] = out_root.joinpath(*package_parts, "__init__.pyi")
    return required


def _basedpyright_command(*, package: str, project_file: Path) -> list[str]:
    if shutil.which("basedpyright") is not None:
        return ["basedpyright", "--project", str(project_file), "--createstub", package]
    return [sys.executable, "-m", "basedpyright", "--project", str(project_file), "--createstub", package]


def _write_project_config(*, project_file: Path, src_root: Path, out_root: Path) -> None:
    config = {
        "include": [str(src_root)],
        "stubPath": str(out_root),
        "executionEnvironments": [
            {
                "root": str(src_root),
                "extraPaths": [str(src_root)],
            }
        ],
    }
    project_file.write_text(json.dumps(config), encoding="utf-8")


def _run_basedpyright_command(*, command: list[str], source_label: str, src_root: Path) -> None:
    try:
        result = subprocess.run(  # noqa: S603
            command,
            check=False,
            capture_output=True,
            text=True,
            env={**os.environ, "PYTHONPATH": str(src_root)},
        )
    except FileNotFoundError as exc:
        raise RuntimeError("basedpyright is not installed. Install it with 'pip install basedpyright'.") from exc
    if result.returncode != 0:
        raise RuntimeError(
            f"basedpyright stub generation failed for '{source_label}': {(result.stderr or result.stdout).strip()}"
        )
