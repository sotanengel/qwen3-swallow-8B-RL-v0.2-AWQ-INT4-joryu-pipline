"""config.yaml から ModelOrchestrator を構築。"""

from __future__ import annotations

from pathlib import Path

from joryu.config import Config, ProfileSpecConfig, load_config
from joryu.orchestrator.backend import resolve_backend
from joryu.orchestrator.profile import ModelProfile, ProfileSpec
from joryu.orchestrator.service import ModelOrchestrator


def _default_profiles() -> list[ProfileSpecConfig]:
    return [
        ProfileSpecConfig(
            name="distill",
            service="joryu",
            port=8100,
            model="tokyotech-llm/Qwen3-Swallow-8B-RL-v0.2-AWQ-INT4",
            compose_profile="distill",
        ),
        ProfileSpecConfig(
            name="seed_gen",
            service="joryu-seed",
            port=8110,
            model="Qwen/Qwen2.5-7B-Instruct-AWQ",
            compose_profile="seed_gen",
        ),
        ProfileSpecConfig(
            name="screening",
            service="joryu-judge",
            port=8080,
            kind="llama_server",
            model="Llama-3.1-Swallow-8B-Instruct-v0.5-Q4_K_M.gguf",
            compose_profile="screening",
        ),
    ]


def profile_specs_from_config(cfg: Config) -> dict[ModelProfile, ProfileSpec]:
    raw_profiles = cfg.models.profiles or _default_profiles()
    out: dict[ModelProfile, ProfileSpec] = {}
    for p in raw_profiles:
        mp = ModelProfile(p.name)
        out[mp] = ProfileSpec(
            name=p.name,
            service=p.service,
            port=p.port,
            health=p.health,
            kind=p.kind,  # type: ignore[arg-type]
            model=p.model,
            compose_profile=p.compose_profile or p.name,
        )
    return out


def auto_restore_profile(cfg: Config) -> ModelProfile | None:
    value = (cfg.models.auto_restore or "distill").strip().lower()
    if value in ("none", ""):
        return None
    if value == "last":
        return None
    return ModelProfile(value)


def build_orchestrator(repo_root: Path, cfg: Config | None = None) -> ModelOrchestrator:
    if cfg is None:
        cfg_path = repo_root / "config.yaml"
        cfg = load_config(cfg_path) if cfg_path.exists() else Config()
    return ModelOrchestrator(
        repo_root=repo_root,
        profiles=profile_specs_from_config(cfg),
        backend=resolve_backend(str(repo_root)),
        auto_restore=auto_restore_profile(cfg),
    )
