# sigx

`sigx` helps you generate `.pyi` overrides for decorated functions.

It is split into two packages:

- `sigx`: tiny runtime marker decorators
- `sigx-gen`: generator that scans source code, imports modules, evaluates decorator factory arguments, applies registered transforms, and writes `.pyi` files

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

## CLI usage

Generate inline `.pyi` files:

```bash
sigx-gen generate --src-root src
```

Check for drift without writing files:

```bash
sigx-gen check --src-root src
```

## v0.1 limitations

- only simple decorator forms are supported: `@name`, `@module.name`, and call forms of each
- nested functions are ignored
- local reassignments and dynamic aliases are not resolved
- only inline `.pyi` output (next to `.py`) is supported
- transform callbacks must return a single `SignatureIR`

## Safety note

Generation imports and evaluates project code, including decorator factory arguments. Run `sigx-gen` only on trusted codebases.
