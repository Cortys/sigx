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
  - Patch backend interfaces and implementation plus signature/import rendering helpers.
- `src/sigx_gen/bootstrap/`
  - Baseline stub bootstrap (`basedpyright`) used by `generate`.
- `src/sigx_gen/io/`
  - Serialized artifact I/O (`TransformPlan` JSON).
- `src/sigx_gen/*.py`
  - CLI/config orchestration (`cli.py`, `config.py`) and transform builder helpers (`builder.py`).

### End-to-end flow

1. `pipeline.discovery.discover_modules(src_root)`
   - Walks `*.py` files and parses AST.
   - Collects module imports, top-level variables, class names, and functions/methods.

2. `pipeline.transformer.apply_transforms(discovered_functions, module_files=...)`
   - Applies decorator transforms in decorator-application order (bottom-to-top).
   - Supports single or multi-signature transform results.
   - Multi-signature outputs branch via cross-product semantics.
   - Uses static marker fallback when runtime decorator import/metadata lookup fails.

3. Plan construction
   - `pipeline.planner.build_transform_plan(...)`
   - Converts transformed signatures into serialized symbol/module patch intents.
   - Synthesizes deterministic typing imports from signature name usage (`Any`, `Literal`, `overload`).

4. Stub update
    - **generate**: bootstrap baseline stubs with `bootstrap.basedpyright`, guarantee each planned module stub exists via targeted fallback generation, then patch using LibCST backend.
    - `generate` always prunes unmanaged `.pyi` files from the generated output set.
    - When `out-root != src-root`, pruning keeps required ancestor `__init__.pyi` package stubs for planned modules; when `out-root == src-root`, pruning keeps only planned module stubs.
    - **patch/apply**: patch existing stubs via `emit.patch_libcst` directly from discovered or serialized plans.

5. `cli.py` orchestration
    - `generate`, `patch`, `plan`, `apply`
    - `--check`, `--fail-on-errors`, `--include`, `--exclude` supported where applicable
    - Exit codes: `0` success, `1` check mismatch, `2` unrecoverable error.

## Design constraints

- Generation imports and evaluates project code; use only on trusted codebases.
- Decorator syntax support is intentionally minimal.
- Patch backend depends on `libcst` as a default runtime dependency.
- Baseline generation depends on `basedpyright`.
