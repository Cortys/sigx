"""Backward-compatible re-exports for source discovery."""

from sigx_gen.model.symbols import DiscoveredFunction, DiscoveredModule, DiscoveredVariable, ImportAlias
from sigx_gen.pipeline.discovery import (
    derive_module_name,
    discover_functions,
    discover_modules,
    extract_signature_from_node,
)

__all__ = [
    "DiscoveredFunction",
    "DiscoveredModule",
    "DiscoveredVariable",
    "ImportAlias",
    "derive_module_name",
    "discover_functions",
    "discover_modules",
    "extract_signature_from_node",
]
