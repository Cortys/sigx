"""Rendering utilities for turning signature IR into stub syntax."""

from __future__ import annotations

from sigx_gen.model.signature import ParamKind, SignatureIR, SigParam


def render_signature(sig: SignatureIR) -> str:
    """Render a signature IR object to Python stub syntax.

    Args:
        sig: Signature IR to render.

    Returns:
        Rendered signature including return annotation.
    """
    params = list(sig.params)
    tokens: list[str] = []

    first_kwonly_index = next((i for i, param in enumerate(params) if param.kind == ParamKind.KW_ONLY), None)
    has_var_pos = any(param.kind == ParamKind.VAR_POS for param in params)
    last_pos_only_index = max(
        (i for i, param in enumerate(params) if param.kind == ParamKind.POS_ONLY),
        default=None,
    )

    for index, param in enumerate(params):
        if first_kwonly_index == index and not has_var_pos:
            tokens.append("*")

        tokens.append(_render_param(param))

        if last_pos_only_index == index:
            tokens.append("/")

    type_params_prefix = ""
    if sig.type_params:
        type_params_prefix = f"[{', '.join(sig.type_params)}]"
    return_annotation = sig.return_annotation or "Any"
    return f"{type_params_prefix}({', '.join(tokens)}) -> {return_annotation}"


def _render_param(param: SigParam) -> str:
    prefix = ""
    if param.kind == ParamKind.VAR_POS:
        prefix = "*"
    elif param.kind == ParamKind.VAR_KW:
        prefix = "**"

    rendered = f"{prefix}{param.name}"
    if param.annotation is not None:
        rendered = f"{rendered}: {param.annotation}"
    if param.default is not None:
        rendered = f"{rendered} = {param.default}"
    return rendered
