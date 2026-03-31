# sigx

`sigx` helps you generate and patch `.pyi` stubs for decorated functions.

It is split into two packages:

- `sigx`: tiny runtime marker decorators
- `sigx-gen`: generator that scans source code, evaluates decorator transforms, and patches baseline stubs

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
from sigx_gen.model.transform_api import TransformFactoryContext


def add_kwargs_transform(ctx: TransformFactoryContext):
    builder = SignatureBuilder.from_signature(ctx.original)
    for name in ctx.bound_factory_args.arguments["kwarg_list"]:
        builder.add_kwonly(name, annotation="Any", default="...")
    return builder.build()
```

Transform callbacks may also return multiple signatures (for overload generation):

```python
from sigx_gen.builder import SignatureBuilder
from sigx_gen.model.transform_api import TransformContext


def either_a_or_b(ctx: TransformContext):
    with_a = SignatureBuilder.from_signature(ctx.original)
    with_a.add_kwonly("a", annotation="Any", default="...")

    with_b = SignatureBuilder.from_signature(ctx.original)
    with_b.add_kwonly("b", annotation="Any", default="...")

    return [with_a.build(), with_b.build()]
```

`sigx-gen` applies this as multiple overload signatures during patching.

## CLI usage

Generate baseline stubs and patch transforms in one command:

```bash
sigx-gen generate --src-root src
```

Patch existing stubs without regenerating the baseline:

```bash
sigx-gen patch --src-root src --stub-root stubs
```

Check drift without writing:

```bash
sigx-gen patch --src-root src --stub-root stubs --check
```

Split planning/applying for CI or custom pipelines:

```bash
sigx-gen plan --src-root src --stub-root stubs --plan-out sigx-plan.json
sigx-gen apply --plan sigx-plan.json
```

Filter scope and fail hard on transform errors:

```bash
sigx-gen generate --src-root src --include "pkg/**" --exclude "**/legacy/**" --fail-on-errors
```

The plan+patch flow preserves key typing constructs:

- function type parameters are preserved in emitted signatures (for example `def run[T](...) -> T`)
- transformed signatures and overloads are rendered deterministically in decorator-application order

Install optional patch dependency:

```bash
pip install "sigx[patch]"
```

## v0.1 limitations

- only simple decorator forms are supported: `@name`, `@module.name`, and call forms of each
- nested functions are ignored
- local reassignments and dynamic aliases are not resolved
- patching currently targets top-level functions and class methods

## Safety note

Planning imports and evaluates project code, including decorator factory arguments. Run `sigx-gen` only on trusted codebases.

## Contributor notes

Test layout conventions are documented in `tests/README.md`.
