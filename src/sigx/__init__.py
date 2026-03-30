"""sigx: Runtime package for sigx-gen.

This package provides the runtime decorators used by sigx-gen to analyze and generate .pyi stub files.
The provided decorators in this sigx do not perform any runtime modifications to the functions they decorate;
instead, they serve as markers for sigx-gen to identify and process the decorated functions when generating type stubs.
"""

__version__ = "0.1.0"
