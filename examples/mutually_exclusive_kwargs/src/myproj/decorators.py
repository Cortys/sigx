from __future__ import annotations

from sigx import stub_transform


@stub_transform("myproj.stub_transforms:either_a_or_b")
def either_a_or_b(func):
    return func
