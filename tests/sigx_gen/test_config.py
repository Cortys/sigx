from __future__ import annotations

from pathlib import Path

from sigx_gen.config import ApplyConfig, GenerationConfig, PlanConfig


def test_generation_config_defaults() -> None:
    config = GenerationConfig(src_root=Path("src"), out_root=Path("out"))

    assert not config.check
    assert config.backend == "standalone"


def test_plan_and_apply_config_values() -> None:
    plan = PlanConfig(src_root=Path("src"), stub_root=Path("stubs"), plan_file=Path("plan.json"))
    apply = ApplyConfig(plan_file=Path("plan.json"), check=True)

    assert plan.stub_root == Path("stubs")
    assert apply.check
