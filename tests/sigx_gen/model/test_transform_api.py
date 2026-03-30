from __future__ import annotations

from sigx_gen.model.signature import SignatureIR
from sigx_gen.model.transform_api import BoundArgumentsView, DecoratorApplication, TargetInfo, TransformContext


def test_transform_context_models_construct() -> None:
    context = TransformContext(
        original=SignatureIR(params=(), return_annotation="None"),
        target=TargetInfo(
            module_name="pkg.mod",
            qualname="run",
            function_name="run",
            class_name=None,
            is_async=False,
            is_method=False,
            is_classmethod=False,
            is_staticmethod=False,
        ),
        decorator=DecoratorApplication(
            syntax="@decorator",
            resolved_name="pkg.decorator",
            transform_ref="pkg.transforms:run",
        ),
    )
    bound = BoundArgumentsView(arguments={"name": "x"})

    assert context.target.function_name == "run"
    assert bound.arguments["name"] == "x"
