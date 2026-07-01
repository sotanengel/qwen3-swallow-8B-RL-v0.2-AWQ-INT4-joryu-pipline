"""required_profile mapping tests."""

from __future__ import annotations

from joryu.jobs.models import (
    SEED_GEN_MODE_CHECK,
    SEED_GEN_MODE_CREATE,
    CurateJobSpec,
    JobKind,
    JobRecord,
    JobStatus,
    SeedGenJobSpec,
)
from joryu.orchestrator.profile import ModelProfile
from joryu.orchestrator.required import required_profile, required_profile_from_spec


def _seed_record(mode: str) -> JobRecord:
    return JobRecord(
        id="job-x",
        kind=JobKind.SEED_GEN,
        spec=SeedGenJobSpec(mode=mode),
        status=JobStatus.QUEUED,
        created_at="2026-01-01T00:00:00Z",
    )


def test_seed_gen_create_requires_seed_gen_profile() -> None:
    assert required_profile(_seed_record(SEED_GEN_MODE_CREATE)) == ModelProfile.SEED_GEN
    assert (
        required_profile_from_spec(JobKind.SEED_GEN, SeedGenJobSpec(mode=SEED_GEN_MODE_CREATE))
        == ModelProfile.SEED_GEN
    )


def test_seed_gen_check_requires_screening_profile() -> None:
    assert required_profile(_seed_record(SEED_GEN_MODE_CHECK)) == ModelProfile.SCREENING
    assert (
        required_profile_from_spec(JobKind.SEED_GEN, SeedGenJobSpec(mode=SEED_GEN_MODE_CHECK))
        == ModelProfile.SCREENING
    )


def test_curate_screening_prompt_bank_requires_screening() -> None:
    spec = CurateJobSpec(screening=True, prompt_bank=True)
    assert required_profile_from_spec(JobKind.CURATE, spec) == ModelProfile.SCREENING


def test_distill_requires_distill_profile() -> None:
    assert required_profile_from_spec(JobKind.DISTILL, None) == ModelProfile.DISTILL
