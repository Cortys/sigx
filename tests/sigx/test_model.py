from __future__ import annotations

from sigx.model import TRANSFORM_ATTR, TransformKind, TransformMetadata


def test_transform_kind_values() -> None:
    assert TransformKind.DECORATOR == "decorator"
    assert TransformKind.DECORATOR_FACTORY == "decorator_factory"


def test_transform_metadata_fields() -> None:
    metadata = TransformMetadata(kind=TransformKind.DECORATOR, ref="pkg.mod:cb", version=2)

    assert metadata.kind is TransformKind.DECORATOR
    assert metadata.ref == "pkg.mod:cb"
    assert metadata.version == 2


def test_transform_attr_name_constant() -> None:
    assert TRANSFORM_ATTR == "__sigx_transform__"
