# Test Suite Layout

Tests are organized to mirror the package structure.

## Mapping rule

- For each testable module `sigx_gen.x.y`, place tests in `tests/sigx_gen/x/test_y.py`.
- For each testable module `sigx.x`, place tests in `tests/sigx/test_x.py`.

Examples:

- `src/sigx_gen/pipeline/discovery.py` -> `tests/sigx_gen/pipeline/test_discovery.py`
- `src/sigx_gen/emit/standalone.py` -> `tests/sigx_gen/emit/test_standalone.py`
- `src/sigx/runtime.py` -> `tests/sigx/test_runtime.py`

## Broader integration tests

- Keep cross-module integration scenarios in `tests/sigx_gen/test_*.py`.
- Keep end-to-end and CLI tests in `tests/sigx_gen/test_e2e_generate.py`, `tests/sigx_gen/test_cli.py`, and related top-level files.

## Style expectations

- Prefer focused unit tests in the nearest module-mirrored location.
- Add/adjust tests whenever behavior changes in the corresponding module.
- Run `ruff check src tests`, `ty check`, and `pytest` before finishing.
