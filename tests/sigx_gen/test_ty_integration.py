from __future__ import annotations

import importlib
import os
from pathlib import Path
import shutil
import subprocess
import sys

from sigx_gen.emit.standalone import render_standalone_outputs, write_outputs
from sigx_gen.pipeline.discovery import discover_modules
from sigx_gen.pipeline.transformer import apply_transforms


def test_generated_stubs_are_usable_by_ty(tmp_path: Path) -> None:
    fixture_root = Path(__file__).resolve().parents[1] / "fixtures" / "project_basic" / "src"
    work_src = tmp_path / "src"
    shutil.copytree(fixture_root, work_src)

    sys.path.insert(0, str(work_src))
    importlib.invalidate_caches()
    try:
        modules = discover_modules(work_src)
        discovered = tuple(function for module in modules for function in module.functions)
        transformed = apply_transforms(discovered)
        outputs = render_standalone_outputs(modules, transformed.functions, src_root=work_src, out_root=work_src)
        write_outputs(outputs)
    finally:
        if str(work_src) in sys.path:
            sys.path.remove(str(work_src))

    result = subprocess.run(
        ["ty", "check", str(work_src)],
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": str(work_src)},
    )

    assert result.returncode == 0, result.stdout + result.stderr
