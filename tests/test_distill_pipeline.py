"""Distill Stage 単体テスト (#251)。"""

from __future__ import annotations

from joryu.config import Config
from joryu.distill.pipeline import DistillPipeline
from joryu.distill.protocol import DistillContext
from joryu.distill.stages import LoopStage
from joryu.prompt_bank import EffectiveSampling, PromptRow
from tests.conftest import FakeVllmClient


def test_loop_stage_adds_turns_from_context() -> None:
    stage = LoopStage()
    cfg = Config()
    row = PromptRow(prompt="p", category="c")
    eff = EffectiveSampling(
        style_id=None,
        system_prompt="sys",
        sampling={"temperature": 0.7, "top_p": 0.9, "max_tokens": 100},
        tools=[],
    )
    context = DistillContext(
        config=cfg,
        client=FakeVllmClient(answer="a"),
        row=row,
        eff=eff,
        model_name="m",
        config_hash="sha256-x",
        messages=[{"role": "user", "content": "p"}],
        turns_holder={
            "turns": [{"role": "assistant", "content": "a", "tool_calls": []}],
            "tool_loop_dedupe": {"skipped_calls": 0, "unique_calls": 1},
        },
        use_tool_loop=True,
    )
    record = {"answer": "a", "turns": []}
    updated = stage.process(record, context)
    assert len(updated["turns"]) == 1
    assert updated["tool_loop_dedupe"]["unique_calls"] == 1


def test_distill_pipeline_apply_stages_chain() -> None:
    pipe = DistillPipeline(stages=(LoopStage(),))
    cfg = Config()
    row = PromptRow(prompt="p", category="c")
    eff = EffectiveSampling(
        style_id=None,
        system_prompt="sys",
        sampling={"temperature": 0.7, "top_p": 0.9, "max_tokens": 100},
        tools=[],
    )
    context = DistillContext(
        config=cfg,
        client=FakeVllmClient(answer="a"),
        row=row,
        eff=eff,
        model_name="m",
        config_hash="sha256-x",
        messages=[{"role": "user", "content": "p"}],
        turns_holder={"turns": [{"role": "assistant", "content": "x", "tool_calls": []}]},
        use_tool_loop=True,
    )
    result = pipe.apply_stages({"answer": "x"}, context)
    assert result["turns"][0]["content"] == "x"
