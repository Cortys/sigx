# sigx Architecture Map

This document summarizes how `sigx` runtime markers and `sigx-gen` generation flow work in v0.1.

## Runtime package (`sigx`)

- `src/sigx/runtime.py`
  - `stub_transform(ref, version=1)` and `stub_transform_factory(ref, version=1)` validate inputs.
  - They attach `TransformMetadata` to the original decorator object under `__sigx_transform__`.
  - They are no-op markers: the original decorator/factory object is returned unchanged.
- `src/sigx/model.py`
  - Defines `TransformKind`, `TransformMetadata`, and `TRANSFORM_ATTR`.

## Generator package (`sigx_gen`)

### Data model

- `src/sigx_gen/signature_ir.py`
  - Immutable `SignatureIR` and `SigParam` model.
- `src/sigx_gen/builder.py`
  - Mutable `SignatureBuilder` used by transform callbacks.
- `src/sigx_gen/transform_api.py`
  - Public callback context objects (`TransformContext`, `TransformFactoryContext`, etc.).
- `src/sigx_gen/diagnostics.py`
  - Structured diagnostics with codes and levels.

### End-to-end flow

1. `discovery.discover_functions(src_root)`
   - Walks `*.py`, parses AST, collects top-level functions and class methods.
   - Captures decorator syntax and import aliases for resolver.
   - Builds original signature input from AST nodes.

2. `engine.apply_transforms(discovered_functions)`
   - For each function, starts from AST-extracted `SignatureIR`.
   - Processes decorators in decorator-application order (bottom to top).
   - Resolves decorator references via `resolver.resolve_decorator(...)`.
   - Imports decorator module and loads runtime metadata via `loader`.
   - Loads generator callback from `module:function` ref.
   - For factory decorators, evaluates call arguments in module globals via `eval.evaluate_factory_arguments(...)` and binds them.
   - Calls transform callback with context and updates current signatures sequentially.
   - Transform callbacks can return one signature or multiple signatures; multiple returns branch into overload candidates via cross-product semantics.
   - Collects `Diagnostic` entries for unresolved/failed sites and continues.

3. `writer.render_module_outputs(...)`
   - Groups transformed functions by module.
   - Uses `render.render_signature(...)` to emit signature text.
   - Adds typing imports as needed (`Any`, `overload`).
   - Renders multiple signatures for one function as `@overload` blocks.
   - Emits top-level functions and minimal class blocks for transformed methods.

4. `writer.write_module_outputs(...)` or `writer.check_module_outputs(...)`
   - Writes `.pyi` files mirrored from source layout, or checks for drift.

### CLI orchestration

- `src/sigx_gen/cli.py`
  - `generate`: scan -> transform -> render -> write.
  - `check`: alias behavior to generate in check mode.
  - Exit codes: `0` success, `1` drift in check mode, `2` unrecoverable error.

## Important constraints

- Generation imports and evaluates project code. Use only on trusted codebases.
- Supported decorator syntax is intentionally minimal in v0.1.
- Nested functions and dynamic aliasing are out of scope for v0.1.
