"""config.py: YAML を joryu の Config dataclass に読み込む。"""

from pathlib import Path

import pytest

from joryu.config import (
    Config,
    DistillConfig,
    ExportConfig,
    ModelConfig,
    VllmConfig,
    load_config,
)


def test_default_config_round_trips_known_values() -> None:
    cfg = Config()
    assert cfg.model.name == "Qwen3-Swallow-8B-RL-v0.2-AWQ-INT4"
    assert cfg.model.mode == "thinking"
    assert cfg.model.temperature == pytest.approx(0.6)
    assert cfg.model.top_p == pytest.approx(0.95)
    assert cfg.model.top_k == 20
    assert cfg.model.repetition_penalty == pytest.approx(1.05)
    assert cfg.vllm.dtype == "bfloat16"
    assert cfg.vllm.quantization == "awq_marlin"
    assert cfg.distill.prompt_bank.endswith("training_prompts.jsonl")
    assert cfg.distill.prompt_csv == ""
    assert cfg.export.compression == "zstd"
    assert cfg.export.level == 19


def test_load_config_yaml(tmp_path: Path) -> None:
    yaml_text = """
model:
  name: "custom-model"
  mode: "nothinking"
  temperature: 0.3
  top_p: 0.8
  top_k: 50
  num_ctx: 1024
  num_predict: 256
vllm:
  model_path: "some/path"
  dtype: "float16"
  quantization: "awq"
  gpu_memory_utilization: 0.7
  enforce_eager: false
distill:
  prompt_bank: "x.jsonl"
  out_dir: "out"
  out_file: "r.jsonl"
  min_interval_sec: 0
  system_prompt: "hi"
export:
  out_dir: "exp"
  compression: "zstd"
  level: 9
  bundle_tar: true
""".strip()
    path = tmp_path / "c.yaml"
    path.write_text(yaml_text, encoding="utf-8")

    cfg = load_config(path)
    assert cfg.model.name == "custom-model"
    assert cfg.model.mode == "nothinking"
    assert cfg.model.temperature == pytest.approx(0.3)
    assert cfg.vllm.dtype == "float16"
    assert cfg.distill.prompt_bank == "x.jsonl"
    assert cfg.export.bundle_tar is True
    assert cfg.export.level == 9


def test_load_config_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_config(tmp_path / "nope.yaml")


def test_invalid_mode_rejected() -> None:
    with pytest.raises(ValueError):
        ModelConfig(mode="rambling")  # type: ignore[arg-type]


def test_partial_yaml_falls_back_to_defaults(tmp_path: Path) -> None:
    # model.mode のみ上書き。他は既定値。
    path = tmp_path / "partial.yaml"
    path.write_text("model:\n  mode: nothinking\n", encoding="utf-8")
    cfg = load_config(path)
    assert cfg.model.mode == "nothinking"
    assert cfg.model.name == "Qwen3-Swallow-8B-RL-v0.2-AWQ-INT4"
    assert cfg.vllm.dtype == "bfloat16"


def test_config_hash_is_stable_and_changes_with_content() -> None:
    a = Config()
    b = Config()
    assert a.fingerprint() == b.fingerprint()
    a.model.temperature = 0.1
    assert a.fingerprint() != b.fingerprint()


def test_dataclass_types() -> None:
    cfg = Config()
    assert isinstance(cfg.model, ModelConfig)
    assert isinstance(cfg.vllm, VllmConfig)
    assert isinstance(cfg.distill, DistillConfig)
    assert isinstance(cfg.export, ExportConfig)
