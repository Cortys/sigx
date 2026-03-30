# Implementation Plan: `sigx` and `sigx-gen`

## 1. Objective

Build a two-part library for Python 3.13+ that lets users annotate decorators and decorator factories with **generator-time signature transforms**, then generate `.pyi` stubs by scanning a codebase, importing relevant modules, evaluating decorator factory arguments, and applying the registered transforms.

The design must be:

* minimal
* deterministic
* unit-tested
* documented with Google-style docstrings on every public class, function, and method

The system must support this core use case:

```python
from sigx import stub_transform_factory


@stub_transform_factory("myproj.stub_transforms:add_kwargs_transform")
def add_kwargs(kwarg_list: list[str]):
    def decorator(func):
        return func

    return decorator
```

And:

```python
@add_kwargs(["debug", "trace"])
def run_job(name: str) -> None: ...
```

Generates:

```python
from typing import Any


def run_job(name: str, *, debug: Any = ..., trace: Any = ...) -> None: ...
```

---

## 2. Scope for v0.1

Implement only the smallest coherent feature set.

### In scope

* Runtime package `sigx`
* Generator package `sigx-gen`
* Annotating plain decorators
* Annotating decorator factories
* Source scanning of `.py` files
* Resolving simple decorator names and imported aliases
* Loading modules during generation
* Evaluating decorator factory arguments in module context
* Binding evaluated args to the factory signature
* Executing programmatic transform callbacks
* Internal signature model
* Signature builder with keyword-only insertion support
* `.pyi` rendering for top-level functions and methods
* Unit tests
* CLI with `generate` and `check`
* Inline `.pyi` output next to `.py`

### Out of scope for v0.1

* Stub-only package emission
* Overload synthesis
* Class-wide transforms
* Property transforms
* Nested function support
* Subprocess import sandboxing
* Full static symbol solver for arbitrary Python
* Arbitrary decorator expressions beyond supported forms
* Transform registry IDs
* Configurable evaluation modes
* Automatic import sorting/formatting beyond stable deterministic output

---

## 3. Non-goals

Do not attempt to:

* teach `ty` or any checker new inference rules directly
* infer transform semantics from arbitrary runtime code
* execute untrusted code safely
* fully model all Python decorator edge cases
* preserve exact formatting/comments in generated stubs

---

## 4. High-level architecture

## 4.1 Runtime package: `sigx`

A tiny package shipped to end users.

Responsibilities:

* provide marker decorators
* attach transform metadata to decorator functions/factories
* expose no heavy dependencies
* perform no scanning, parsing, or generation

### Public runtime API

```python
def stub_transform(ref: str, *, version: int = 1): ...
def stub_transform_factory(ref: str, *, version: int = 1): ...
```

These must be runtime no-ops except for attaching metadata.

---

## 4.2 Generator package: `sigx-gen`

A development-time package.

Responsibilities:

* scan source files
* discover decorated functions
* resolve decorator references
* import modules
* evaluate decorator arguments
* load transform callbacks
* build transformed signatures
* render `.pyi` stubs
* expose CLI

---

## 5. Repository layout

Use a monorepo with two installable packages.

```text
repo/
  pyproject.toml
  README.md
  src/
    sigx/
      __init__.py
      runtime.py
      model.py
    sigx_gen/
      __init__.py
      cli.py
      config.py
      discovery.py
      resolver.py
      loader.py
      eval.py
      signature_ir.py
      builder.py
      transform_api.py
      engine.py
      render.py
      writer.py
      diagnostics.py
  tests/
    test_runtime.py
    test_discovery.py
    test_resolver.py
    test_eval.py
    test_signature_ir.py
    test_builder.py
    test_engine.py
    test_render.py
    test_e2e_generate.py
  fixtures/
    project_basic/
      ...
```

Keep the first version flat. Do not over-modularize.

---

## 6. Runtime package design (`sigx`)

## 6.1 `sigx.model`

Define the runtime metadata model.

### `TransformKind`

Use `enum.StrEnum`.

Values:

* `"decorator"`
* `"decorator_factory"`

### `TransformMetadata`

Use `@dataclass(frozen=True, slots=True)`.

Fields:

* `kind: TransformKind`
* `ref: str`
* `version: int = 1`

### Constant

* `TRANSFORM_ATTR = "__sigx_transform__"`

---

## 6.2 `sigx.runtime`

Implement the marker decorators.

### `stub_transform(ref: str, *, version: int = 1) -> Callable[[F], F]`

Attach:

```python
TransformMetadata(kind=TransformKind.DECORATOR, ref=ref, version=version)
```

to the decorated function using `TRANSFORM_ATTR`.

### `stub_transform_factory(ref: str, *, version: int = 1) -> Callable[[F], F]`

Attach:

```python
TransformMetadata(kind=TransformKind.DECORATOR_FACTORY, ref=ref, version=version)
```

to the decorated function using `TRANSFORM_ATTR`.

### Requirements

* return the original object unchanged
* do not wrap
* do not import generator code
* validate `ref` is a non-empty string
* validate `version >= 1`

---

## 6.3 `sigx.__init__`

Export only:

* `stub_transform`
* `stub_transform_factory`
* `TransformMetadata`
* `TransformKind`

Keep it minimal.

---

## 7. Generator package data model

## 7.1 `sigx_gen.signature_ir`

Define the internal signature representation.

### `ParamKind`

Use `enum.StrEnum` with values:

* `POS_ONLY`
* `POS_OR_KW`
* `VAR_POS`
* `KW_ONLY`
* `VAR_KW`

### `SigParam`

`@dataclass(frozen=True, slots=True)`

Fields:

* `name: str`
* `kind: ParamKind`
* `annotation: str | None`
* `default: str | None`

### `SignatureIR`

`@dataclass(frozen=True, slots=True)`

Fields:

* `params: tuple[SigParam, ...]`
* `return_annotation: str | None`
* `is_async: bool = False`

### Required methods

* `get_param(name: str) -> SigParam | None`
* `has_param(name: str) -> bool`
* `index_of(name: str) -> int | None`

Do not add mutation methods here.

---

## 7.2 `sigx_gen.builder`

Define a mutable builder.

### `SignatureBuilder`

Internal mutable class for transforms.

Fields:

* `_params: list[SigParam]`
* `_return_annotation: str | None`
* `_is_async: bool`

### Constructors

* `from_signature(sig: SignatureIR) -> SignatureBuilder`

### Methods

* `add_kwonly(name: str, *, annotation: str = "Any", default: str | None = "...", if_missing: bool = False) -> None`
* `remove(name: str) -> None`
* `rename(old: str, new: str) -> None`
* `set_return(annotation: str) -> None`
* `build() -> SignatureIR`

### Validation rules

* no duplicate parameter names
* `add_kwonly` inserts:

  * after existing kw-only params
  * before `**kwargs`
  * inserts a synthetic kw-only boundary during rendering, not as a fake param
* if param exists:

  * raise `ValueError`, unless `if_missing=True`
* do not allow removing `*args` or `**kwargs` in v0.1
* do not allow renaming to existing name

Keep the builder focused. Do not add positional insertion in v0.1.

---

## 7.3 `sigx_gen.transform_api`

Define the official generator-side API for transform authors.

### `TargetInfo`

`@dataclass(frozen=True, slots=True)`

Fields:

* `module_name: str`
* `qualname: str`
* `function_name: str`
* `class_name: str | None`
* `is_async: bool`
* `is_method: bool`
* `is_classmethod: bool`
* `is_staticmethod: bool`

### `DecoratorApplication`

`@dataclass(frozen=True, slots=True)`

Fields:

* `syntax: str`
* `resolved_name: str`
* `transform_ref: str`

### `DecoratorFactoryApplication`

`@dataclass(frozen=True, slots=True)`

Fields:

* `syntax: str`
* `resolved_name: str`
* `transform_ref: str`
* `arg_exprs: tuple[str, ...]`
* `kwarg_exprs: dict[str, str]`

### `BoundArgumentsView`

`@dataclass(frozen=True, slots=True)`

Fields:

* `arguments: Mapping[str, object]`

### `TransformContext`

`@dataclass(frozen=True, slots=True)`

Fields:

* `original: SignatureIR`
* `target: TargetInfo`
* `decorator: DecoratorApplication`

### `TransformFactoryContext`

`@dataclass(frozen=True, slots=True)`

Fields:

* `original: SignatureIR`
* `target: TargetInfo`
* `decorator: DecoratorFactoryApplication`
* `bound_factory_args: BoundArgumentsView`

### Type aliases

* `type PlainTransform = Callable[[TransformContext], SignatureIR]`
* `type FactoryTransform = Callable[[TransformFactoryContext], SignatureIR]`

Do not support multi-signature results yet.

---

## 8. Discovery model

## 8.1 `sigx_gen.discovery`

Parse source files with `ast`.

Do not use LibCST in v0.1.

### Responsibilities

* walk source roots
* parse Python modules
* collect top-level functions and class methods
* record decorator syntax
* collect import aliases needed for resolution
* record original function signatures as source data

### Define data classes

#### `ImportAlias`

Fields:

* `local_name: str`
* `resolved_module: str | None`
* `resolved_attr: str | None`

Examples:

* `from pkg.mod import dec as alias`
* `import pkg.mod as pm`

#### `DiscoveredFunction`

Fields:

* `module_name: str`
* `file_path: Path`
* `qualname: str`
* `function_name: str`
* `class_name: str | None`
* `is_async: bool`
* `is_method: bool`
* `decorators: tuple[ast.expr, ...]`
* `node: ast.FunctionDef | ast.AsyncFunctionDef`
* `imports: tuple[ImportAlias, ...]`

### Supported decorator syntax in v0.1

* `@name`
* `@module.name`
* `@name(...)`
* `@module.name(...)`

Skip anything else with a diagnostic.

### Signature extraction

Extract signature source directly from AST:

* parameter names
* param kinds
* annotations as source strings via `ast.unparse`
* defaults as source strings via `ast.unparse`
* return annotation as source string via `ast.unparse`

Do not import the target function to derive the original signature.

---

## 8.2 Module name derivation

Given a `src_root` and file path, derive module names from relative path:

* `src/pkg/mod.py` -> `pkg.mod`
* `src/pkg/__init__.py` -> `pkg`

Assume a normal source layout.

---

## 9. Decorator resolution

## 9.1 `sigx_gen.resolver`

Resolve a decorator expression to a module object path.

### Inputs

* decorator AST expression
* module name
* import aliases
* local scope context

### Output

A `ResolvedDecoratorRef` data class:

Fields:

* `module_name: str | None`
* `object_name: str | None`
* `is_call: bool`
* `display_name: str`

### Resolution rules

#### Case 1: `@name`

If `name` was imported via `from x import name`, resolve to:

* module: `x`
* object: `name`

If unresolved, assume it refers to a local module-level symbol in the same module:

* module: current module
* object: `name`

#### Case 2: `@alias`

If alias imported from `from x import y as alias`, resolve to `x.y`.

#### Case 3: `@mod.name`

If `mod` is from `import pkg.mod as mod`, resolve to `pkg.mod.name`.

#### Case 4: decorator factory calls

Same as above, but `is_call=True` and preserve the call AST.

### Out of scope

Do not support:

* re-export chains across multiple modules
* assignment aliases like `other = dec`
* dynamically constructed decorators

Emit warnings for unresolved cases.

---

## 10. Module loading and transform callback loading

## 10.1 `sigx_gen.loader`

Responsibilities:

* import decorator-defining modules
* retrieve runtime transform metadata
* import generator transform callbacks from dotted refs

### Functions

* `load_module(module_name: str) -> ModuleType`
* `load_transform_metadata(obj: object) -> TransformMetadata | None`
* `load_transform_callable(ref: str) -> Callable[..., SignatureIR]`

### `load_transform_callable`

Accept dotted refs in the form:

```text
package.module:function_name
```

Reject anything else.

### Import policy

Use `importlib.import_module` in-process.

Document clearly that generation imports project code and is intended only for trusted codebases.

---

## 11. Decorator argument evaluation

## 11.1 `sigx_gen.eval`

Implement evaluation of decorator factory arguments at call sites.

### Inputs

* module object containing the decorated function
* decorator call AST
* resolved factory object
* factory callable

### Responsibilities

* evaluate positional args using `eval`
* evaluate keyword args using `eval`
* use the decorated module globals as the evaluation namespace
* bind the result to `inspect.signature(factory).bind(*args, **kwargs)`

### Output

* `BoundArgumentsView`

### Constraints

* v0.1 supports only module-global evaluation
* use:

  * `globals = vars(module_obj)`
  * `locals = None`
* do not attempt a safe evaluator in v0.1
* surface exceptions as diagnostics, not crashes

### Required behavior

If evaluation fails:

* record a diagnostic
* skip stub transformation for that decoration site
* continue processing other functions

---

## 12. Transform engine

## 12.1 `sigx_gen.engine`

This is the core orchestration layer.

### Responsibilities

For each discovered function:

1. build `SignatureIR` from AST
2. inspect decorators in source order
3. resolve each decorator
4. import the defining module
5. retrieve the decorator/factory object
6. read runtime transform metadata
7. if no transform metadata, ignore the decorator
8. if plain decorator:

   * load generator transform callable
   * build `TransformContext`
   * call transform
9. if decorator factory:

   * evaluate call args
   * bind them
   * load generator transform callable
   * build `TransformFactoryContext`
   * call transform
10. apply transforms sequentially to the current `SignatureIR`
11. store final signature result for stub rendering

### Important choice

Apply transforms in the same order the decorators appear in the source list, top to bottom.

Document this explicitly and test it.

### Diagnostics

Collect structured diagnostics rather than throwing when possible.

---

## 13. Stub rendering

## 13.1 `sigx_gen.render`

Convert `SignatureIR` to `.pyi` function signatures.

### Responsibilities

* render params in valid Python syntax
* insert `*` when kw-only params exist and no `*args` is present
* place kw-only params before `**kwargs`
* render defaults exactly as stored strings
* render annotations exactly as stored strings
* render return annotation or `Any` if none

### Required helper

`render_signature(sig: SignatureIR) -> str`

Example:

```python
(x: int, y: str = "a", *, debug: Any = ..., trace: Any = ...) -> None
```

### `Any` handling

If any inserted transform uses `"Any"`, make sure the module-level stub includes:

```python
from typing import Any
```

In v0.1, simplest approach:

* scan rendered functions for the substring `Any`
* if found, emit `from typing import Any`

Do not attempt precise import tracking yet.

---

## 13.2 `sigx_gen.writer`

Group results by module and write `.pyi` files.

### Behavior

* output path mirrors the source tree
* for `pkg/mod.py`, write `pkg/mod.pyi`
* for `pkg/__init__.py`, write `pkg/__init__.pyi`

### Minimal rendering strategy

For each module:

* optional header comment
* required imports
* one function stub per transformed function
* preserve simple class grouping for methods

### For class methods

If a method belongs to a class, render:

```python
class MyClass:
    def method(...): ...
```

In v0.1:

* render only methods that were discovered
* do not try to reproduce full class bodies
* emit `class Name:` followed by relevant methods
* if a class has no rendered methods, omit it

This is sufficient for the first version.

---

## 14. Diagnostics

## 14.1 `sigx_gen.diagnostics`

Define a minimal structured diagnostic model.

### `DiagnosticLevel`

* `INFO`
* `WARNING`
* `ERROR`

### `Diagnostic`

Fields:

* `level: DiagnosticLevel`
* `code: str`
* `message: str`
* `module_name: str | None`
* `qualname: str | None`
* `file_path: str | None`

### Suggested codes

* `SX001` unresolved decorator
* `SX002` unsupported decorator syntax
* `SX003` module import failed
* `SX004` transform metadata missing
* `SX005` transform callback import failed
* `SX006` decorator factory arg evaluation failed
* `SX007` transform execution failed
* `SX008` invalid transformed signature

The engine should return diagnostics alongside results.

---

## 15. CLI

## 15.1 `sigx_gen.cli`

Provide two commands.

### `sigx-gen generate`

Arguments:

* `--src-root PATH` required
* `--out-root PATH` optional, default same as src-root
* `--check` optional

Behavior:

* scan source tree
* generate stubs
* write files
* if `--check`, compare generated output to on-disk output and exit non-zero on drift without writing

### `sigx-gen check`

Alias for:

* `generate --check`

### Exit codes

* `0` success
* `1` check mismatch
* `2` unrecoverable error

Use `argparse` in v0.1.

---

## 16. Minimal documentation requirements

Every public class, function, and method must have a Google-style docstring.

### Docstring template

```python
def example(arg: str) -> str:
    """Do the thing.

    Args:
        arg: Description of the argument.

    Returns:
        Description of the return value.

    Raises:
        ValueError: If the argument is invalid.
    """
```

### Requirement

Docstrings required for:

* all public runtime APIs
* all public generator APIs
* all builder methods
* all rendering/writing functions
* CLI entrypoints
* data classes only need class-level docstrings, not property docstrings

Tests do not need docstrings.

---

## 17. Unit test plan

Use `pytest`.

## 17.1 `test_runtime.py`

Cover:

* metadata attached correctly by `stub_transform`
* metadata attached correctly by `stub_transform_factory`
* original object identity preserved
* invalid refs rejected
* invalid versions rejected

---

## 17.2 `test_signature_ir.py`

Cover:

* `has_param`
* `get_param`
* `index_of`

---

## 17.3 `test_builder.py`

Cover:

* add kw-only to function without kw-only params
* add kw-only to function with existing kw-only params
* add kw-only before `**kwargs`
* duplicate param errors
* `if_missing=True`
* rename success/failure
* remove success/failure
* build returns immutable `SignatureIR`

---

## 17.4 `test_discovery.py`

Use temporary files.

Cover:

* module name derivation
* discovery of top-level function
* discovery of class method
* extraction of decorators
* extraction of annotations/defaults from AST
* detection of async functions

---

## 17.5 `test_resolver.py`

Cover:

* `from x import dec`
* `from x import dec as alias`
* `import pkg.mod as pm`
* unresolved local symbol fallback
* unsupported expressions emit diagnostics

---

## 17.6 `test_eval.py`

Cover:

* literal positional args
* literal keyword args
* module constant lookup
* bound args mapping
* evaluation failure surfaces diagnostic-compatible exception

---

## 17.7 `test_engine.py`

Create fixture modules.

Cover:

* plain decorator transform applied
* decorator factory transform applied
* multiple transforms applied in source order
* decorator without metadata ignored
* transform callback failure recorded

Use a very small generator transform callback fixture:

```python
def add_kwargs_transform(ctx):
    builder = SignatureBuilder.from_signature(ctx.original)
    for name in ctx.bound_factory_args.arguments["kwarg_list"]:
        builder.add_kwonly(name, annotation="Any", default="...")
    return builder.build()
```

---

## 17.8 `test_render.py`

Cover:

* no kw-only
* kw-only with synthetic `*`
* kw-only with `*args`
* placement before `**kwargs`
* return annotation rendering
* `Any` import detection

---

## 17.9 `test_e2e_generate.py`

Fixture project layout:

```text
fixtures/project_basic/src/myproj/
  decorators.py
  stub_transforms.py
  jobs.py
```

Run generation against the fixture and assert exact `.pyi` contents.

At least two end-to-end cases:

* top-level function
* class method

---

## 18. Example fixture design

## 18.1 `decorators.py`

```python
from sigx import stub_transform_factory


@stub_transform_factory("myproj.stub_transforms:add_kwargs_transform")
def add_kwargs(kwarg_list: list[str]):
    def decorator(func):
        return func

    return decorator
```

## 18.2 `stub_transforms.py`

```python
from sigx_gen.builder import SignatureBuilder
from sigx_gen.transform_api import TransformFactoryContext


def add_kwargs_transform(ctx: TransformFactoryContext):
    builder = SignatureBuilder.from_signature(ctx.original)
    for name in ctx.bound_factory_args.arguments["kwarg_list"]:
        builder.add_kwonly(name, annotation="Any", default="...")
    return builder.build()
```

## 18.3 `jobs.py`

```python
from myproj.decorators import add_kwargs


@add_kwargs(["debug", "trace"])
def run_job(name: str) -> None:
    pass
```

Expected `.pyi`:

```python
from typing import Any


def run_job(name: str, *, debug: Any = ..., trace: Any = ...) -> None: ...
```

---

## 19. Implementation order

## Phase 1: runtime package

Implement:

* `sigx.model`
* `sigx.runtime`
* `sigx.__init__`
* runtime tests

Exit criteria:

* runtime tests pass

---

## Phase 2: signature core

Implement:

* `signature_ir.py`
* `builder.py`
* builder/signature tests

Exit criteria:

* builder operations stable and validated

---

## Phase 3: source discovery

Implement:

* AST scanning
* module name derivation
* import alias capture
* AST-to-IR signature extraction
* discovery tests

Exit criteria:

* can discover decorated functions and extract original signatures

---

## Phase 4: resolver and loader

Implement:

* decorator resolution
* module import
* transform metadata load
* transform callable load
* resolver tests

Exit criteria:

* resolved decorators can be mapped to runtime objects and transform callbacks

---

## Phase 5: evaluation and transform engine

Implement:

* decorator factory arg evaluation
* binding to factory signature
* context object construction
* sequential transform application
* engine tests

Exit criteria:

* transformed `SignatureIR` produced correctly for plain and factory decorators

---

## Phase 6: rendering and writing

Implement:

* signature rendering
* module stub emission
* filesystem writing
* render tests
* e2e tests

Exit criteria:

* `.pyi` files generated correctly for fixture projects

---

## Phase 7: CLI and docs polish

Implement:

* CLI
* check mode
* README
* docstring pass

Exit criteria:

* package usable from command line
* public APIs documented

---

## 20. Coding standards

* Python 3.13+
* use `from __future__ import annotations`
* use `dataclass(slots=True, frozen=True)` where appropriate
* use `pathlib.Path`
* use `enum.StrEnum`
* use explicit return types everywhere
* keep functions small
* prefer pure functions in generator internals
* avoid hidden global state
* no external dependencies in v0.1 besides `pytest`

---

## 21. Error handling rules

* user-facing generation should continue past per-function failures
* collect diagnostics instead of crashing
* only fatal errors should abort the whole run:

  * invalid CLI args
  * unreadable source root
  * malformed output path handling

Transform callback exceptions must be wrapped into diagnostics.

---

## 22. Minimal README outline

Include:

1. what the library does
2. runtime vs generator split
3. basic example
4. how to write a generator transform callback
5. how to run `sigx-gen generate`
6. limitations of v0.1
7. safety note that generation imports and evaluates project code

---

## 23. Acceptance criteria

The implementation is complete when all of the following are true:

* `stub_transform` and `stub_transform_factory` attach metadata without wrapping
* generator can scan a source tree and discover supported decorator sites
* generator can resolve imported decorator symbols for supported cases
* generator can import the decorator-defining module and load metadata
* generator can import a transform callback from a `module:function` ref
* generator can evaluate decorator factory args in module context
* generator can bind args using the factory callable signature
* generator can call a transform callback with `TransformFactoryContext`
* `SignatureBuilder.add_kwonly()` behaves correctly in all tested cases
* generator writes deterministic `.pyi` files for fixture projects
* all public methods have Google-style docstrings
* all unit and end-to-end tests pass

---

## 24. Known limitations to document clearly

Document these in code and README:

* generation imports and evaluates project code
* only trusted codebases should be processed
* only simple decorator forms are supported in v0.1
* nested functions are ignored
* local reassignments and dynamic aliases are not resolved
* only inline `.pyi` output is supported
* transform callbacks must return a single `SignatureIR`

---

## 25. Stretch items only if time remains

Only after v0.1 is complete:

* `pyproject.toml` config support
* separate `stub-package` output mode
* richer import tracking
* registry IDs in addition to dotted refs
* overload-capable transform results
* subprocess import mode

Do not start these until the core acceptance criteria are met.

---

## 26. Final instruction to coding agent

Build the smallest end-to-end system first. Favor clarity over abstraction. Keep runtime metadata tiny, keep transform execution entirely generator-side, and use tests to lock down behavior before expanding scope.

The first milestone should be: generate one correct `.pyi` file for the `add_kwargs(["debug", "trace"])` fixture and pass all related unit tests.
