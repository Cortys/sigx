from __future__ import annotations

from sigx import stub_transform


@stub_transform("myproj.stub_transforms:add_audit_flag")
def audit(func):
    return func
