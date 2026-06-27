"""Curate PipelineBuilder (#258)。"""

from __future__ import annotations

from joryu.curate.stage import CurateContext, CurateStage


class PipelineBuilder:
    """CurateStage を順次接続するビルダ。"""

    def __init__(self) -> None:
        self._stages: list[CurateStage] = []

    def register_stage(self, stage: CurateStage) -> PipelineBuilder:
        self._stages.append(stage)
        return self

    def build(self) -> CuratePipeline:
        return CuratePipeline(tuple(self._stages))


class CuratePipeline:
    """登録済み Stage を stage_index 付きで実行。"""

    def __init__(self, stages: tuple[CurateStage, ...]) -> None:
        self._stages = stages

    @property
    def stage_count(self) -> int:
        return len(self._stages)

    def run(self, context: CurateContext) -> CurateContext:
        ctx = context
        for index, stage in enumerate(self._stages):
            ctx.stage_index = index
            ctx = stage.apply(ctx)
        return ctx


__all__ = ["CuratePipeline", "PipelineBuilder"]
