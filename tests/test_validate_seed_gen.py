"""validate_seed_gen_job_spec tests."""

from pathlib import Path

import pytest

from joryu.jobs.models import SeedGenJobSpec
from joryu.jobs.validate import validate_seed_gen_job_spec


def test_validate_seed_gen_rejects_bad_threshold() -> None:
    with pytest.raises(ValueError, match="sim_threshold"):
        validate_seed_gen_job_spec(SeedGenJobSpec(sim_threshold=1.5))


def test_validate_seed_gen_missing_domains(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="domains config"):
        validate_seed_gen_job_spec(
            SeedGenJobSpec(domains_config="missing.yaml"),
            repo_root=tmp_path,
        )
