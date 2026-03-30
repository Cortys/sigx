"""Backward-compatible re-exports for transform engine."""

from sigx_gen.pipeline.transformer import TransformedFunction, TransformerResult as EngineResult, apply_transforms

__all__ = ["EngineResult", "TransformedFunction", "apply_transforms"]
