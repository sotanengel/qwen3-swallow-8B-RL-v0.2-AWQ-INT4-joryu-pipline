"""joryu config schema. YAML を dataclass に読み込み、欠損値は既定にフォールバック。"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

import yaml

Mode = Literal["thinking", "nothinking"]


@dataclass
class ModelConfig:
    name: str = "Qwen3-Swallow-8B-RL-v0.2-AWQ-INT4"
    num_ctx: int = 512
    num_predict: int = 384
    temperature: float = 0.6
    top_p: float = 0.95
    top_k: int = 20
    repetition_penalty: float = 1.05
    seed: int = 42
    mode: Mode = "thinking"

    def __post_init__(self) -> None:
        if self.mode not in ("thinking", "nothinking"):
            raise ValueError(f"model.mode must be 'thinking' or 'nothinking', got {self.mode!r}")


@dataclass
class VllmConfig:
    model_path: str = "tokyotech-llm/Qwen3-Swallow-8B-RL-v0.2-AWQ-INT4"
    dtype: str = "bfloat16"
    quantization: str = "awq_marlin"
    gpu_memory_utilization: float = 0.85
    enforce_eager: bool = True


_DEFAULT_SYSTEM_PROMPT = (
    "あなたは丁寧で正確な日本語アシスタントです。\n"
    "ユーザの質問に、根拠を示しながら自然な日本語で答えてください。\n"
)


@dataclass
class DistillConfig:
    prompt_bank: str = "data/prompts/training_prompts.jsonl"
    out_dir: str = "data/distilled"
    out_file: str = "responses.jsonl"
    min_interval_sec: float = 0.5
    system_prompt: str = _DEFAULT_SYSTEM_PROMPT
    styles_file: str = "styles.yaml"


@dataclass
class ExportConfig:
    out_dir: str = "exports"
    compression: str = "zstd"
    level: int = 19
    bundle_tar: bool = False


@dataclass
class Config:
    model: ModelConfig = field(default_factory=ModelConfig)
    vllm: VllmConfig = field(default_factory=VllmConfig)
    distill: DistillConfig = field(default_factory=DistillConfig)
    export: ExportConfig = field(default_factory=ExportConfig)

    def fingerprint(self) -> str:
        """設定の SHA256 ハッシュ。出力レコードの再現性記録に使う。"""
        payload = json.dumps(asdict(self), sort_keys=True, ensure_ascii=False)
        return "sha256-" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _merge_section(default: Any, override: dict[str, Any] | None) -> Any:
    if not override:
        return default
    cls = type(default)
    fields = {f for f in default.__dataclass_fields__}  # type: ignore[attr-defined]
    kwargs = {k: v for k, v in asdict(default).items()}
    for k, v in override.items():
        if k in fields:
            kwargs[k] = v
    return cls(**kwargs)


def load_config(path: str | Path) -> Config:
    """YAML から Config を構築する。欠損セクション/キーは既定値を使用。"""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"config not found: {p}")
    raw = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    cfg = Config()
    cfg.model = _merge_section(cfg.model, raw.get("model"))
    cfg.vllm = _merge_section(cfg.vllm, raw.get("vllm"))
    cfg.distill = _merge_section(cfg.distill, raw.get("distill"))
    cfg.export = _merge_section(cfg.export, raw.get("export"))
    return cfg
