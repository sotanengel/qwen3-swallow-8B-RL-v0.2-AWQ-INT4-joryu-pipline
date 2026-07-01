"""JobKind から ModelProfile を導出。"""

from __future__ import annotations

from joryu.jobs.models import (
    SEED_GEN_MODE_CHECK,
    CurateJobSpec,
    JobKind,
    JobRecord,
    SeedGenJobSpec,
)
from joryu.orchestrator.profile import ModelProfile


def required_profile(record: JobRecord) -> ModelProfile:
    """ジョブ種別から必要な GPU profile を返す。"""
    if record.kind == JobKind.DISTILL:
        return ModelProfile.DISTILL
    if record.kind == JobKind.SEED_GEN:
        if isinstance(record.spec, SeedGenJobSpec) and record.spec.mode == SEED_GEN_MODE_CHECK:
            return ModelProfile.SCREENING
        return ModelProfile.SEED_GEN
    if record.kind == JobKind.CURATE and isinstance(record.spec, CurateJobSpec):
        if record.spec.screening and record.spec.prompt_bank:
            return ModelProfile.SCREENING
        return ModelProfile.DISTILL
    return ModelProfile.DISTILL


def required_profile_from_spec(kind: JobKind, spec: object) -> ModelProfile:
    """spec から profile を導出 (API 事前チェック用)。"""
    if kind == JobKind.DISTILL:
        del spec
        return ModelProfile.DISTILL
    if kind == JobKind.SEED_GEN:
        if isinstance(spec, SeedGenJobSpec) and spec.mode == SEED_GEN_MODE_CHECK:
            return ModelProfile.SCREENING
        return ModelProfile.SEED_GEN
    if kind == JobKind.CURATE and isinstance(spec, CurateJobSpec):
        if spec.screening and spec.prompt_bank:
            return ModelProfile.SCREENING
        return ModelProfile.DISTILL
    return ModelProfile.DISTILL
