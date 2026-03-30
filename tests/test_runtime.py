from __future__ import annotations

from typing import cast

import pytest

from sigx import TransformKind, stub_transform, stub_transform_factory
from sigx.model import TRANSFORM_ATTR


def test_stub_transform_attaches_metadata() -> None:
    def dec(func: object) -> object:
        return func

    decorated = stub_transform("pkg.mod:transform")(dec)
    metadata = getattr(decorated, TRANSFORM_ATTR)

    assert metadata.kind == TransformKind.DECORATOR
    assert metadata.ref == "pkg.mod:transform"
    assert metadata.version == 1


def test_stub_transform_factory_attaches_metadata() -> None:
    def factory() -> object:
        return object()

    decorated = stub_transform_factory("pkg.mod:factory_transform", version=2)(factory)
    metadata = getattr(decorated, TRANSFORM_ATTR)

    assert metadata.kind == TransformKind.DECORATOR_FACTORY
    assert metadata.ref == "pkg.mod:factory_transform"
    assert metadata.version == 2


def test_runtime_markers_preserve_identity() -> None:
    def target() -> None:
        return None

    assert stub_transform("pkg.mod:t")(target) is target
    assert stub_transform_factory("pkg.mod:t")(target) is target


@pytest.mark.parametrize("ref", ["", "   ", None])
def test_runtime_markers_reject_invalid_ref(ref: object) -> None:
    with pytest.raises(ValueError, match="non-empty"):
        stub_transform(cast("str", ref))


@pytest.mark.parametrize("version", [0, -1])
def test_runtime_markers_reject_invalid_version(version: int) -> None:
    with pytest.raises(ValueError, match=">= 1"):
        stub_transform("pkg.mod:ok", version=version)
