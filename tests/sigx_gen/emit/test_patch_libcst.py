from __future__ import annotations

from sigx_gen.emit.patch_libcst import build_libcst_backend


def test_build_libcst_backend_optional_dependency() -> None:
    try:
        backend = build_libcst_backend()
    except RuntimeError:
        assert True
        return

    assert backend is not None
