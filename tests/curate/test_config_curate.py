"""config.yaml の curate: セクション読み込みテスト (R-15 / R-17)。"""

from __future__ import annotations

from pathlib import Path

import yaml

from joryu.config import Config, load_config


def _write(path: Path, payload: dict) -> None:
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def test_load_config_uses_curate_defaults_when_section_absent(tmp_path: Path) -> None:
    p = tmp_path / "c.yaml"
    _write(p, {"model": {"name": "x"}})
    cfg = load_config(p)
    assert cfg.curate.threshold == 0.7
    assert cfg.curate.weights_stat == 0.4
    assert cfg.curate.weights_llm == 0.6


def test_load_config_overrides_curate_top_level(tmp_path: Path) -> None:
    p = tmp_path / "c.yaml"
    _write(
        p,
        {
            "curate": {
                "weights_stat": 0.2,
                "weights_llm": 0.8,
                "threshold": 0.5,
                "judge_model": "alt",
            }
        },
    )
    cfg = load_config(p)
    assert cfg.curate.weights_stat == 0.2
    assert cfg.curate.weights_llm == 0.8
    assert cfg.curate.threshold == 0.5
    assert cfg.curate.judge_model == "alt"


def test_load_config_overrides_curate_thresholds(tmp_path: Path) -> None:
    p = tmp_path / "c.yaml"
    _write(
        p,
        {
            "curate": {
                "thresholds": {
                    "len_a_min": 100,
                    "len_a_max": 8000,
                    "samp_out_z_min": -3.0,
                }
            }
        },
    )
    cfg = load_config(p)
    assert cfg.curate.thresholds.len_a_min == 100
    assert cfg.curate.thresholds.len_a_max == 8000
    assert cfg.curate.thresholds.samp_out_z_min == -3.0
    # 未指定キーは既定維持
    assert cfg.curate.thresholds.lang_ja_min == 0.6


def test_curate_fingerprints_change_with_signal_threshold(tmp_path: Path) -> None:
    base = Config()
    base_fp = base.curate_fingerprints()
    altered = Config()
    altered.curate.thresholds.len_a_min = 5
    alt_fp = altered.curate_fingerprints()
    # signal_config_hash は変わる
    assert alt_fp["signal_config_hash"] != base_fp["signal_config_hash"]
    # judge / scoring は変わらない
    assert alt_fp["judge_config_hash"] == base_fp["judge_config_hash"]
    assert alt_fp["scoring_config_hash"] == base_fp["scoring_config_hash"]


def test_curate_fingerprints_change_with_scoring_weights(tmp_path: Path) -> None:
    base = Config()
    base_fp = base.curate_fingerprints()
    altered = Config()
    altered.curate.weights_stat = 0.2
    altered.curate.weights_llm = 0.8
    alt_fp = altered.curate_fingerprints()
    assert alt_fp["scoring_config_hash"] != base_fp["scoring_config_hash"]
    assert alt_fp["signal_config_hash"] == base_fp["signal_config_hash"]
    assert alt_fp["judge_config_hash"] == base_fp["judge_config_hash"]


def test_curate_fingerprints_change_with_judge_settings(tmp_path: Path) -> None:
    base = Config()
    base_fp = base.curate_fingerprints()
    altered = Config()
    altered.curate.judge_mode = "thinking"
    alt_fp = altered.curate_fingerprints()
    assert alt_fp["judge_config_hash"] != base_fp["judge_config_hash"]
    assert alt_fp["signal_config_hash"] == base_fp["signal_config_hash"]
    assert alt_fp["scoring_config_hash"] == base_fp["scoring_config_hash"]


def test_main_config_yaml_loads_with_curate_section() -> None:
    """リポジトリの config.yaml が curate: セクションを含む状態でロードできる。"""
    p = Path(__file__).resolve().parents[2] / "config.yaml"
    if not p.exists():
        return  # CI 等で config.yaml が無い場合は skip
    cfg = load_config(p)
    assert 0.0 < cfg.curate.weights_stat <= 1.0
    assert 0.0 <= cfg.curate.weights_llm <= 1.0
    assert cfg.curate.thresholds.len_a_min > 0
