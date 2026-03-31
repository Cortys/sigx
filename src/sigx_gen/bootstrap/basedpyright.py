"""basedpyright-backed baseline stub generation helpers."""

from __future__ import annotations

from collections.abc import Iterable
import os
from pathlib import Path
import shutil
import subprocess
import sys


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

    for package in top_level_packages:
        command = _basedpyright_command(package=package, out_root=out_root)
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
                f"basedpyright stub generation failed for '{package}': {(result.stderr or result.stdout).strip()}"
            )


def _basedpyright_command(*, package: str, out_root: Path) -> list[str]:
    if shutil.which("basedpyright") is not None:
        executable = "basedpyright"
        return [executable, "--createstub", package, "--output", str(out_root)]
    return [sys.executable, "-m", "basedpyright", "--createstub", package, "--output", str(out_root)]
