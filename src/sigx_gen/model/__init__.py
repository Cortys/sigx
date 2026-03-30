"""Core data models used across sigx generator pipeline."""

from sigx_gen.model.diagnostics import Diagnostic, DiagnosticLevel
from sigx_gen.model.plan import ModulePlan, SymbolPlan, TransformPlan
from sigx_gen.model.signature import ParamKind, SignatureIR, SigParam
from sigx_gen.model.symbols import DiscoveredFunction, DiscoveredModule, DiscoveredVariable, ImportAlias
from sigx_gen.model.transform_api import (
    BoundArgumentsView,
    DecoratorApplication,
    DecoratorFactoryApplication,
    FactoryTransform,
    PlainTransform,
    TargetInfo,
    TransformContext,
    TransformFactoryContext,
    TransformResult,
)

__all__ = [
    "BoundArgumentsView",
    "DecoratorApplication",
    "DecoratorFactoryApplication",
    "Diagnostic",
    "DiagnosticLevel",
    "DiscoveredFunction",
    "DiscoveredModule",
    "DiscoveredVariable",
    "FactoryTransform",
    "ImportAlias",
    "ModulePlan",
    "ParamKind",
    "PlainTransform",
    "SigParam",
    "SignatureIR",
    "SymbolPlan",
    "TargetInfo",
    "TransformContext",
    "TransformFactoryContext",
    "TransformPlan",
    "TransformResult",
]
