from __future__ import annotations

from pathlib import Path

from sigx_gen.bootstrap.source_stubs import generate_stubs_from_source
from sigx_gen.model.plan import ModulePlan


def _module_plan_for(*, source_file: Path, stub_file: Path, module_name: str = "pkg.mod") -> ModulePlan:
    return ModulePlan(
        module_name=module_name,
        source_file=source_file,
        stub_file=stub_file,
        typing_imports=(),
        module_imports=(),
        symbols=(),
    )


def test_generate_stubs_from_source_strips_bodies_and_keeps_docstrings(tmp_path: Path) -> None:
    source_file = tmp_path / "src" / "pkg" / "mod.py"
    stub_file = tmp_path / "stubs" / "pkg" / "mod.pyi"
    source_file.parent.mkdir(parents=True)
    source_file.write_text(
        (
            "def run(name: str) -> str:\n"
            '    """Run one job."""\n'
            "    value = name.upper()\n"
            "    return value\n\n"
            "class Worker:\n"
            "    def process(self, name: str) -> str:\n"
            '        """Process one job."""\n'
            "        return name.upper()\n"
        ),
        encoding="utf-8",
    )

    diagnostics = generate_stubs_from_source(
        module_plans=(_module_plan_for(source_file=source_file, stub_file=stub_file),),
    )

    assert diagnostics == ()
    stub_text = stub_file.read_text(encoding="utf-8")
    assert '"""Run one job."""' in stub_text
    assert '"""Process one job."""' in stub_text
    assert "value = name.upper()" not in stub_text
    assert "return value" not in stub_text
    assert "return name.upper()" not in stub_text
    assert "def run(name: str) -> str:" in stub_text
    assert "def process(self, name: str) -> str:" in stub_text
    assert "..." in stub_text


def test_generate_stubs_from_source_strips_only_known_signature_neutral_decorators(tmp_path: Path) -> None:
    source_file = tmp_path / "src" / "pkg" / "mod.py"
    stub_file = tmp_path / "stubs" / "pkg" / "mod.pyi"
    source_file.parent.mkdir(parents=True)
    source_file.write_text(
        (
            "from typing import override\n"
            "from typing import final\n"
            "from typing_extensions import override as ext_override\n"
            "from typing_extensions import final as ext_final\n"
            "import typing as t\n"
            "import typing_extensions as te\n\n"
            "def keep(func):\n"
            "    return func\n\n"
            "@override\n"
            "@ext_override\n"
            "@t.override\n"
            "@te.override\n"
            "@final\n"
            "@ext_final\n"
            "@t.final\n"
            "@te.final\n"
            "@keep\n"
            "def run() -> None:\n"
            '    """Run one job."""\n'
            "    return None\n"
        ),
        encoding="utf-8",
    )

    diagnostics = generate_stubs_from_source(
        module_plans=(_module_plan_for(source_file=source_file, stub_file=stub_file),),
    )

    assert diagnostics == ()
    stub_text = stub_file.read_text(encoding="utf-8")
    assert "@override" not in stub_text
    assert "@ext_override" not in stub_text
    assert "@t.override" not in stub_text
    assert "@te.override" not in stub_text
    assert "@final" in stub_text
    assert "@ext_final" in stub_text
    assert "@t.final" in stub_text
    assert "@te.final" in stub_text
    assert "@keep" in stub_text
