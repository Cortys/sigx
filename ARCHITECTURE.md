# sigx Architecture Map

This document describes the current `sigx` runtime package and the restructured `sigx-gen` pipeline.

## Runtime package (`sigx`)

- `src/sigx/runtime.py`
  - `stub_transform(ref, version=1)` and `stub_transform_factory(ref, version=1)` validate inputs.
  - They attach `TransformMetadata` to the original decorator object under `__sigx_transform__`.
  - They are no-op markers: original objects are returned unchanged.
- `src/sigx/model.py`
  - Defines `TransformKind`, `TransformMetadata`, and `TRANSFORM_ATTR`.

## Generator package (`sigx_gen`)

### Package layout

- `src/sigx_gen/model/`
  - Immutable shared data models: signatures, diagnostics, discovery symbols, callback contexts, transform plans.
- `src/sigx_gen/pipeline/`
  - Source analysis and transform execution: discovery, resolver, loader, evaluator, transformer, planner.
- `src/sigx_gen/emit/`
  - Output backends: standalone file emission, patch backend interfaces, LibCST patch backend, render/import helpers.
- `src/sigx_gen/io/`
  - Serialized artifact I/O (`TransformPlan` JSON).
- `src/sigx_gen/*.py`
  - Thin compatibility wrappers and CLI entrypoint.

### End-to-end flow

1. `pipeline.discovery.discover_modules(src_root)`
   - Walks `*.py` files and parses AST.
   - Collects module imports, top-level variables, class names, and functions/methods.

2. `pipeline.transformer.apply_transforms(discovered_functions)`
   - Applies decorator transforms in decorator-application order (bottom-to-top).
   - Supports single or multi-signature transform results.
   - Multi-signature outputs branch via cross-product semantics.

3. Backend-specific emission
   - **Standalone backend** (`emit.standalone`):
     - emits `.pyi` only for modules containing at least one transformed symbol,
     - emits module-complete stubs for those modules (decorated + undecorated discovered functions/methods, discovered classes, discovered variables).
   - **Patch backend** (`emit.patch_libcst`):
     - builds a transform plan (`pipeline.planner`),
     - patches existing stubs structurally via LibCST.

4. `cli.py` orchestration
   - `generate` / `check` with `--backend standalone|patch`
   - `plan` / `apply` for explicit plan-driven integration workflows
   - Exit codes: `0` success, `1` check mismatch, `2` unrecoverable error.

## Design constraints

- Generation imports and evaluates project code; use only on trusted codebases.
- Decorator syntax support is intentionally minimal.
- Patch backend depends on optional extra `sigx[patch]` (LibCST).
