from __future__ import annotations

import math
from pathlib import Path
import uuid

import pytest

from sigx import stub_transform
from sigx_gen.pipeline.loader import ModuleLoadError, load_module, load_transform_callable, load_transform_metadata


def test_load_module_imports_module() -> None:
    module = load_module("math")
    assert module is math


def test_load_transform_metadata_reads_marker() -> None:
    @stub_transform("math:sqrt")
    def dec(func: object) -> object:
        return func

    metadata = load_transform_metadata(dec)
    assert metadata is not None
    assert metadata.ref == "math:sqrt"


def test_load_transform_callable_validates_ref() -> None:
    with pytest.raises(ValueError, match="module:function"):
        load_transform_callable("invalid")


def test_load_module_preserves_import_and_file_fallback_errors(tmp_path: Path) -> None:
    module_name = f"missing_fixture_{uuid.uuid4().hex[:8]}"
    module_file = tmp_path / "bad_module.py"
    module_file.write_text('raise RuntimeError("file boom")\n', encoding="utf-8")

    with pytest.raises(ModuleLoadError) as exc_info:
        load_module(module_name, module_files={module_name: module_file})

    message = str(exc_info.value)
    assert "importlib import failed: ModuleNotFoundError" in message
    assert f"No module named '{module_name}'" in message
    assert "file fallback failed: RuntimeError: file boom" in message
