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
    module_names: Iterable[str],
) -> None:
    """Generate baseline stubs using basedpyright.

    Args:
        src_root: Source root to place on ``PYTHONPATH``.
        out_root: Stub output root.
        module_names: Module names targeted for baseline generation.

    Raises:
        RuntimeError: If basedpyright is unavailable or generation fails.
    """
    top_level_packages = sorted({module_name.split(".")[0] for module_name in module_names if module_name})
    if not top_level_packages:
        return

    out_root.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="sigx-gen-basedpyright-") as temp_dir:
        project_file = Path(temp_dir) / "pyrightconfig.json"
        _write_project_config(project_file=project_file, src_root=src_root, out_root=out_root)

        for package in top_level_packages:
            command = _basedpyright_command(package=package, project_file=project_file)
            try:
                result = subprocess.run(  # noqa: S603
                    command,
                    check=False,
                    capture_output=True,
                    text=True,
                    env={**os.environ, "PYTHONPATH": str(src_root)},
                )
            except FileNotFoundError as exc:
                raise RuntimeError(
                    "basedpyright is not installed. Install it with 'pip install basedpyright'."
                ) from exc
            if result.returncode != 0:
                raise RuntimeError(
                    f"basedpyright stub generation failed for '{package}': {(result.stderr or result.stdout).strip()}"
                )


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
