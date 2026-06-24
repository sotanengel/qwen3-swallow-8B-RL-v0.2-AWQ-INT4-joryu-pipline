"""joryu config schema. YAML を dataclass に読み込み、欠損値は既定にフォールバック。"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

import yaml

Mode = Literal["thinking", "nothinking", "auto"]


@dataclass
class ModelConfig:
    name: str = "Qwen3-Swallow-8B-RL-v0.2-AWQ-INT4"
    # num_ctx/num_predict は KV cache FP8 + prefix caching 有効化前提で倍増。
    # VRAM が足りない環境では VllmClient.from_config が probe 結果でクランプする。
    num_ctx: int = 4096
    num_predict: int = 2048
    limits_probe_file: str = "data/vllm_limits.json"
    temperature: float = 0.6
    top_p: float = 0.95
    top_k: int = 20
    repetition_penalty: float = 1.05
    seed: int = 42
    mode: Mode = "thinking"

    def __post_init__(self) -> None:
        if self.mode not in ("thinking", "nothinking", "auto"):
            raise ValueError(
                f"model.mode must be 'thinking', 'nothinking', or 'auto', got {self.mode!r}"
            )


@dataclass
class VllmConfig:
    model_path: str = "tokyotech-llm/Qwen3-Swallow-8B-RL-v0.2-AWQ-INT4"
    dtype: str = "bfloat16"
    quantization: str = "awq_marlin"
    gpu_memory_utilization: float = 0.85
    enforce_eager: bool = True
    # KV キャッシュを FP8 化して実効容量を ~2 倍にする (品質影響は実質ゼロ報告)。
    # "auto" / "fp16" / "bfloat16" を指定すれば旧挙動に戻せる。
    kv_cache_dtype: str = "fp8"
    # 共通 system_prompt の KV を 1 回だけ確保するため、prefix caching を有効化。
    enable_prefix_caching: bool = True
    # 蒸留は逐次 1 件ずつなので KV ブロックプールを最小化。
    max_num_seqs: int = 1
    # KV を CPU 側に退避するための swap space (GiB)。0 で無効。
    swap_space_gib: int = 4


_DEFAULT_SYSTEM_PROMPT = (
    "あなたは丁寧で正確な日本語アシスタントです。\nユーザの質問に、自然な日本語で答えてください。\n"
)


@dataclass
class DistillConfig:
    prompt_bank: str = "data/prompts/training_prompts.jsonl"
    prompt_csv: str = ""
    prompt_bank_seed: str = ""
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
class CurateSignalThresholds:
    """ハード棄却の初期閾値 (要件 6.1)。"""

    len_a_min: int = 30
    len_a_max: int = 4000
    len_t_min: int = 20
    len_t_max: int = 8000
    ratio_ta_min: float = 0.05
    ratio_ta_max: float = 10.0
    lang_ja_min: float = 0.6
    repeat_ng_max: float = 0.25
    repeat_char_max: int = 30
    dup_glob_jaccard: float = 0.9
    samp_out_z_min: float = -2.0
    samp_out_min_bucket_size: int = 5  # この件数未満のサンプリング条件は z-score 評価を skip
    style_adh_default_min: float = 0.3


@dataclass
class SearchConfig:
    """ダッシュボード BM25 検索設定。"""

    index_dir: str = "data/distilled/.search_index"
    top_k_default: int = 50
    snippet_chars: int = 200


@dataclass
class CurateConfig:
    """高品質抽出 (`joryu-curate`) 設定。

    `Config.fingerprint()` には含めない (蒸留時の config_hash を破壊しないため)。
    代わりに 3 層ハッシュ (signal/judge/scoring) を `curate_fingerprints()` で個別に出す。
    """

    weights_stat: float = 0.4
    weights_llm: float = 0.6
    threshold: float = 0.7
    top_k: int | None = None
    keep_rate: float | None = None
    judge_model: str = "joryu"
    judge_mode: Mode = "nothinking"
    skip_llm: bool = False
    thresholds: CurateSignalThresholds = field(default_factory=CurateSignalThresholds)
    out_dir: str = "data/curated"

    def __post_init__(self) -> None:
        if self.judge_mode not in ("thinking", "nothinking"):
            raise ValueError(
                f"curate.judge_mode must be 'thinking' or 'nothinking', got {self.judge_mode!r}"
            )


@dataclass
class Config:
    model: ModelConfig = field(default_factory=ModelConfig)
    vllm: VllmConfig = field(default_factory=VllmConfig)
    distill: DistillConfig = field(default_factory=DistillConfig)
    export: ExportConfig = field(default_factory=ExportConfig)
    curate: CurateConfig = field(default_factory=CurateConfig)
    search: SearchConfig = field(default_factory=SearchConfig)

    def fingerprint(self) -> str:
        """設定の SHA256 ハッシュ。出力レコードの再現性記録に使う。

        curate セクションは含めない (蒸留時の config_hash を後段 curate 設定が
        変更しないように)。
        """
        payload_dict = {
            "model": asdict(self.model),
            "vllm": asdict(self.vllm),
            "distill": asdict(self.distill),
            "export": asdict(self.export),
        }
        payload = json.dumps(payload_dict, sort_keys=True, ensure_ascii=False)
        return "sha256-" + hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def curate_fingerprints(self) -> dict[str, str]:
        """curate 設定の 3 層ハッシュ (要件 R-23 への布石)。

        - signal_config_hash: ハード閾値 / シグナル設定
        - judge_config_hash:  judge_model / judge_mode
        - scoring_config_hash: weights / threshold / top_k / keep_rate
        """
        c = self.curate
        signal_payload = json.dumps(asdict(c.thresholds), sort_keys=True, ensure_ascii=False)
        judge_payload = json.dumps(
            {"judge_model": c.judge_model, "judge_mode": c.judge_mode},
            sort_keys=True,
            ensure_ascii=False,
        )
        scoring_payload = json.dumps(
            {
                "weights_stat": c.weights_stat,
                "weights_llm": c.weights_llm,
                "threshold": c.threshold,
                "top_k": c.top_k,
                "keep_rate": c.keep_rate,
            },
            sort_keys=True,
            ensure_ascii=False,
        )
        return {
            "signal_config_hash": "sha256-"
            + hashlib.sha256(signal_payload.encode("utf-8")).hexdigest(),
            "judge_config_hash": "sha256-"
            + hashlib.sha256(judge_payload.encode("utf-8")).hexdigest(),
            "scoring_config_hash": "sha256-"
            + hashlib.sha256(scoring_payload.encode("utf-8")).hexdigest(),
        }


def _merge_section(default: Any, override: dict[str, Any] | None) -> Any:
    if not override:
        return default
    cls = type(default)
    fields = {f for f in default.__dataclass_fields__}  # type: ignore[attr-defined]
    # shallow copy: ネスト dataclass を dict 化しないよう getattr ベースで構築
    kwargs = {k: getattr(default, k) for k in fields}
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
    curate_raw = raw.get("curate") or {}
    thresholds_raw = curate_raw.pop("thresholds", None) if isinstance(curate_raw, dict) else None
    cfg.curate = _merge_section(cfg.curate, curate_raw if isinstance(curate_raw, dict) else None)
    if isinstance(thresholds_raw, dict):
        cfg.curate.thresholds = _merge_section(cfg.curate.thresholds, thresholds_raw)
    cfg.search = _merge_section(cfg.search, raw.get("search"))
    return cfg
