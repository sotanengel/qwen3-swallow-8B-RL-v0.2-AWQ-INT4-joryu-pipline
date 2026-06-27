"""Curate PipelineBuilder テスト (#258)。"""

from __future__ import annotations

from joryu.config import Config
from joryu.curate.cache import CacheIndex
from joryu.curate.pipeline import PipelineBuilder
from joryu.curate.signals import SignalResult
from joryu.curate.stage import CurateContext
from joryu.curate.stages.stat_signals import StatSignalsStage


class _FixedSignal:
    code = "TEST"
    version = "1"

    def __init__(self, score: float) -> None:
        self._score = score

    def evaluate(self, record: dict) -> SignalResult:
        del record
        return SignalResult(code=self.code, version=self.version, score=self._score, raw={})


def test_pipeline_builder_runs_stages_in_order() -> None:
    stage = StatSignalsStage(signals=(_FixedSignal(0.8),))
    pipeline = PipelineBuilder().register_stage(stage).build()
    ctx = CurateContext(
        config=Config(),
        record={"prompt": "p", "answer": "a"},
        record_hash="abc",
        cache_index=CacheIndex(),
        expected_versions={"TEST": "1"},
    )
    result = pipeline.run(ctx)
    assert result.stage_index == 0
    assert len(result.signal_results) == 1
    assert result.signal_results[0].score == 0.8


def test_register_stage_returns_builder_for_chaining() -> None:
    builder = PipelineBuilder()
    s1 = StatSignalsStage(signals=(_FixedSignal(0.5),))
    s2 = StatSignalsStage(signals=(_FixedSignal(0.9),))
    pipeline = builder.register_stage(s1).register_stage(s2).build()
    assert pipeline.stage_count == 2
