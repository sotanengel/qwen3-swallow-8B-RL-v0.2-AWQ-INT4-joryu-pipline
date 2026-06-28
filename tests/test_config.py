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


def test_model_config_has_no_mode_field() -> None:
    """#94 で蒸留側 mode を削除した。ModelConfig.mode は存在しない。"""
    cfg = ModelConfig()
    assert not hasattr(cfg, "mode")


def test_load_config_yaml(tmp_path: Path) -> None:
    yaml_text = """
model:
  name: "custom-model"
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
    assert cfg.model.temperature == pytest.approx(0.3)
    assert cfg.vllm.dtype == "float16"
    assert cfg.distill.prompt_bank == "x.jsonl"
    assert cfg.export.bundle_tar is True
    assert cfg.export.level == 9


def test_load_config_ignores_legacy_model_mode(tmp_path: Path) -> None:
    """過去 YAML に `model.mode` が残っていても読み込み時にエラーにせず無視する。"""
    yaml_text = "model:\n  mode: nothinking\n  temperature: 0.4\n"
    path = tmp_path / "legacy.yaml"
    path.write_text(yaml_text, encoding="utf-8")
    cfg = load_config(path)
    assert not hasattr(cfg.model, "mode")
    assert cfg.model.temperature == pytest.approx(0.4)


def test_load_config_rejects_removed_joryu_llm_serve_backend(tmp_path: Path) -> None:
    """ADR 0003: 旧 joryu-llm-serve backend は読み込み時に拒否する。"""
    path = tmp_path / "removed-backend.yaml"
    path.write_text('vllm:\n  backend: "joryu-llm-serve"\n', encoding="utf-8")
    with pytest.raises(ValueError, match="vllm.backend"):
        load_config(path)


def test_load_config_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_config(tmp_path / "nope.yaml")


def test_partial_yaml_falls_back_to_defaults(tmp_path: Path) -> None:
    path = tmp_path / "partial.yaml"
    path.write_text("model:\n  temperature: 0.4\n", encoding="utf-8")
    cfg = load_config(path)
    assert cfg.model.temperature == pytest.approx(0.4)
    assert cfg.model.name == "Qwen3-Swallow-8B-RL-v0.2-AWQ-INT4"
    assert cfg.vllm.dtype == "bfloat16"


def test_default_system_prompt_avoids_reasoning_bias() -> None:
    prompt = Config().distill.system_prompt
    assert "根拠を示しながら" not in prompt
    assert "自然な日本語で答えてください" in prompt


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


def test_distill_no_think_fallback_defaults_false() -> None:
    cfg = Config()
    assert cfg.distill.no_think_fallback is False


def test_distill_tools_repetition_penalty_defaults() -> None:
    cfg = Config()
    assert cfg.distill.tools_repetition_penalty == pytest.approx(1.0)


def test_fingerprint_unchanged_when_vllm_serve_url_changes() -> None:
    """接続先 URL は config_hash に含めない (下流 SFT 互換)。"""
    base = Config()
    alt = Config()
    alt.vllm.serve_url = "http://localhost:9999"
    assert base.fingerprint() == alt.fingerprint()


def test_fingerprint_unchanged_when_vllm_serve_port_changes() -> None:
    base = Config()
    alt = Config()
    alt.vllm.serve_port = 9999
    assert base.fingerprint() == alt.fingerprint()


def test_load_config_mcp_timeout(tmp_path: Path) -> None:
    path = tmp_path / "mcp.yaml"
    path.write_text(
        """
mcp:
  enabled: true
  url: "http://localhost:8200"
  timeout:
    connect: 1.5
    read: 6.0
""".strip(),
        encoding="utf-8",
    )
    cfg = load_config(path)
    assert cfg.mcp.enabled is True
    assert cfg.mcp.url == "http://localhost:8200"
    assert cfg.mcp.timeout.connect == pytest.approx(1.5)
    assert cfg.mcp.timeout.read == pytest.approx(6.0)


def test_load_config_models_profiles(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text(
        """
models:
  auto_restore: distill
  profiles:
    - name: distill
      service: joryu
      port: 8100
    - name: seed_gen
      service: joryu-seed
      port: 8110
""".strip(),
        encoding="utf-8",
    )
    cfg = load_config(path)
    assert cfg.models.auto_restore == "distill"
    assert len(cfg.models.profiles) == 2
    assert cfg.models.profiles[0].name == "distill"
    assert cfg.models.profiles[1].port == 8110


def test_load_config_tools_weather(tmp_path: Path) -> None:
    path = tmp_path / "tools.yaml"
    path.write_text(
        """
tools:
  weather:
    timeout: 2.5
    provider: open_meteo
""".strip(),
        encoding="utf-8",
    )
    cfg = load_config(path)
    assert cfg.tools.weather.timeout == pytest.approx(2.5)
    assert cfg.tools.weather.provider == "open_meteo"
