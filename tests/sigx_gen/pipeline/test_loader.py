from __future__ import annotations

import math

import pytest

from sigx import stub_transform
from sigx_gen.pipeline.loader import load_module, load_transform_callable, load_transform_metadata


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
