"""ModelProfile 定義。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Literal


class ModelProfile(StrEnum):
    DISTILL = "distill"
    SEED_GEN = "seed_gen"
    SCREENING = "screening"


ProfileKind = Literal["openai_v1", "llama_server"]


@dataclass(frozen=True)
class ProfileSpec:
    name: str
    service: str
    port: int
    health: str = "/health"
    kind: ProfileKind = "openai_v1"
    model: str = ""
    compose_profile: str = ""

    @property
    def profile(self) -> ModelProfile:
        return ModelProfile(self.name)

    def health_url(self, *, host: str | None = None) -> str:
        base = host or self.service
        return f"http://{base}:{self.port}{self.health}"


GPU_PROFILES: frozenset[ModelProfile] = frozenset(
    {ModelProfile.DISTILL, ModelProfile.SEED_GEN, ModelProfile.SCREENING}
)

ALWAYS_COMPOSE_PROFILE = "always"

ALL_GPU_COMPOSE_PROFILES: tuple[str, ...] = (
    ModelProfile.DISTILL.value,
    ModelProfile.SEED_GEN.value,
    ModelProfile.SCREENING.value,
)

ALL_COMPOSE_PROFILES: tuple[str, ...] = (ALWAYS_COMPOSE_PROFILE, *ALL_GPU_COMPOSE_PROFILES)
