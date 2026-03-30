# sigx

`sigx` helps you generate and patch `.pyi` stubs for decorated functions.

It is split into two packages:

- `sigx`: tiny runtime marker decorators
- `sigx-gen`: generator that scans source code, imports modules, evaluates decorator factory arguments, applies registered transforms, and emits stubs

## Basic example

```python
from sigx import stub_transform_factory


@stub_transform_factory("myproj.stub_transforms:add_kwargs_transform")
def add_kwargs(kwarg_list: list[str]):
    def decorator(func):
        return func

    return decorator
```

```python
from myproj.decorators import add_kwargs


@add_kwargs(["debug", "trace"])
def run_job(name: str) -> None:
    pass
```

Generated stub:

```python
from typing import Any


def run_job(name: str, *, debug: Any = ..., trace: Any = ...) -> None: ...
```

## Writing a generator transform callback

```python
from sigx_gen.builder import SignatureBuilder
from sigx_gen.transform_api import TransformFactoryContext


def add_kwargs_transform(ctx: TransformFactoryContext):
    builder = SignatureBuilder.from_signature(ctx.original)
    for name in ctx.bound_factory_args.arguments["kwarg_list"]:
        builder.add_kwonly(name, annotation="Any", default="...")
    return builder.build()
```

Transform callbacks may also return multiple signatures (for overload generation):

```python
from sigx_gen.builder import SignatureBuilder
from sigx_gen.transform_api import TransformContext


def either_a_or_b(ctx: TransformContext):
    with_a = SignatureBuilder.from_signature(ctx.original)
    with_a.add_kwonly("a", annotation="Any", default="...")

    with_b = SignatureBuilder.from_signature(ctx.original)
    with_b.add_kwonly("b", annotation="Any", default="...")

    return [with_a.build(), with_b.build()]
```

`sigx-gen` renders this as `@overload` entries in the generated `.pyi` output.

## CLI usage

### Standalone backend (module-complete stubs)

Generate inline `.pyi` files:

```bash
sigx-gen generate --src-root src
```

Check for drift without writing files:

```bash
sigx-gen check --src-root src
```

When a module contains at least one transformed function, `sigx-gen` emits a module-complete stub for that module (including undecorated top-level functions and discovered methods). Modules without transformed functions are skipped.

### Patch backend (integrate with existing stub pipelines)

Install optional patch dependency:

```bash
pip install "sigx[patch]"
```

Generate and patch existing stubs in one step (no temporary plan file):

```bash
sigx-gen generate --src-root src --out-root stubs --backend patch
```

Or split into explicit plan/apply stages:

```bash
sigx-gen plan --src-root src --stub-root stubs --plan-out sigx-plan.json
sigx-gen apply --plan sigx-plan.json
```

## v0.1 limitations

- only simple decorator forms are supported: `@name`, `@module.name`, and call forms of each
- nested functions are ignored
- local reassignments and dynamic aliases are not resolved
- patch backend currently targets top-level functions and class methods
- supported decorator forms are intentionally limited (`@name`, `@module.name`, and call variants)

## Safety note

Generation imports and evaluates project code, including decorator factory arguments. Run `sigx-gen` only on trusted codebases.

## Contributor notes

Test layout conventions are documented in `tests/README.md`.
