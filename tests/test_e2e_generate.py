from __future__ import annotations

import importlib
from pathlib import Path
import shutil
import sys

from sigx_gen.discovery import discover_functions
from sigx_gen.engine import apply_transforms
from sigx_gen.writer import render_module_outputs, write_module_outputs


def test_e2e_generate_fixture_project(tmp_path: Path) -> None:
    fixture_root = Path(__file__).parent.parent / "fixtures" / "project_basic" / "src"
    work_src = tmp_path / "src"
    shutil.copytree(fixture_root, work_src)

    sys.path.insert(0, str(work_src))
    importlib.invalidate_caches()
    try:
        discovered = discover_functions(work_src)
        result = apply_transforms(discovered)
        outputs = render_module_outputs(result.functions, src_root=work_src, out_root=work_src)
        write_module_outputs(outputs)
    finally:
        if str(work_src) in sys.path:
            sys.path.remove(str(work_src))

    jobs_stub_path = work_src / "myproj" / "jobs.pyi"
    assert jobs_stub_path.exists()
    assert jobs_stub_path.read_text(encoding="utf-8") == (
        "from typing import Any\n\n"
        "def run_job(name: str, *, debug: Any = ..., trace: Any = ...) -> None: ...\n\n"
        "class Worker:\n"
        "    def process(self, name: str, *, attempt: Any = ...) -> None: ...\n"
    )
