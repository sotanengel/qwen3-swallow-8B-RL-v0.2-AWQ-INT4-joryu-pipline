"""docker-compose / Dockerfile が vllm serve を起動する契約テスト。"""

from __future__ import annotations

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]

VLLM_SERVE_ARGS = {
    "vllm",
    "serve",
    "tokyotech-llm/Qwen3-Swallow-8B-RL-v0.2-AWQ-INT4",
    "--host=0.0.0.0",
    "--port=8100",
    "--quantization=awq_marlin",
    "--dtype=bfloat16",
    "--max-model-len=4096",
    "--gpu-memory-utilization=0.85",
    "--kv-cache-dtype=fp8",
    "--enable-prefix-caching",
    "--max-num-seqs=1",
    "--enforce-eager",
    "--enable-auto-tool-choice",
    "--tool-call-parser=hermes",
    "--reasoning-parser=qwen3",
}


def test_compose_joryu_service_runs_vllm_serve() -> None:
    compose = yaml.safe_load((REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    command = compose["services"]["joryu"]["command"]
    assert isinstance(command, list)
    assert set(command) == VLLM_SERVE_ARGS
    assert command[0:3] == ["vllm", "serve", "tokyotech-llm/Qwen3-Swallow-8B-RL-v0.2-AWQ-INT4"]


def test_dockerfile_cmd_runs_vllm_serve() -> None:
    dockerfile = (REPO_ROOT / "Dockerfile.job").read_text(encoding="utf-8")
    assert 'CMD ["vllm", "serve"' in dockerfile
    assert "--enable-auto-tool-choice" in dockerfile
    assert "--tool-call-parser=hermes" in dockerfile
    assert "--reasoning-parser=qwen3" in dockerfile
    assert "joryu-llm-serve" not in dockerfile.split("CMD")[-1]


def test_config_yaml_defaults_to_vllm_serve_backend() -> None:
    raw = yaml.safe_load((REPO_ROOT / "config.yaml").read_text(encoding="utf-8"))
    assert raw["vllm"]["backend"] == "vllm-serve"
