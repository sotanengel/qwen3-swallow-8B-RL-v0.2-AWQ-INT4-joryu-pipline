"""joryu-judge が参照する GGUF リポジトリの契約テスト。"""

from __future__ import annotations

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
COMPOSE_FILE = REPO_ROOT / "docker-compose.yml"
ENTRYPOINT = REPO_ROOT / "scripts" / "judge_entrypoint.sh"

# tokyotech-llm/*-GGUF は存在しない。公開 GGUF はコミュニティ量子化を使う。
JUDGE_GGUF_HF_REPO = "mradermacher/Llama-3.1-Swallow-8B-Instruct-v0.5-GGUF"
JUDGE_GGUF_MODEL_FILE = "Llama-3.1-Swallow-8B-Instruct-v0.5.Q4_K_M.gguf"
OBSOLETE_HF_REPO = "tokyotech-llm/Llama-3.1-Swallow-8B-Instruct-v0.5-GGUF"


def _judge_env() -> dict[str, str]:
    compose = yaml.safe_load(COMPOSE_FILE.read_text(encoding="utf-8"))
    env_list = compose["services"]["joryu-judge"]["environment"]
    return {k: v for item in env_list for k, v in [item.split("=", 1)]}


def test_judge_compose_points_at_existing_gguf_repo() -> None:
    env = _judge_env()
    assert env["JORYU_JUDGE_HF_REPO"] == JUDGE_GGUF_HF_REPO
    assert env["JORYU_JUDGE_MODEL"] == JUDGE_GGUF_MODEL_FILE
    assert OBSOLETE_HF_REPO not in env.values()


def test_judge_entrypoint_defaults_match_compose() -> None:
    text = ENTRYPOINT.read_text(encoding="utf-8")
    assert JUDGE_GGUF_HF_REPO in text
    assert JUDGE_GGUF_MODEL_FILE in text
    assert OBSOLETE_HF_REPO not in text
