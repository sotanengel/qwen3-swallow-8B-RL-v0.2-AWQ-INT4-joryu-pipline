"""seed_gen pipeline (create/check) tests."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from joryu.jobs.models import SEED_GEN_MODE_CHECK, SEED_GEN_MODE_CREATE
from joryu.seed_gen.config import DomainSpec, SeedGenConfig
from joryu.seed_gen.pipeline import (
    PipelineOptions,
    estimate_plan,
    run_check_pipeline,
    run_create_pipeline,
    run_pipeline,
)


class _StubBackend:
    def embed(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for text in texts:
            digest = hashlib.sha256(text.encode("utf-8")).digest()
            out.append([float(b) / 255.0 for b in digest[:16]])
        return out


class _StubGenerator:
    """LLM 生成をエミュレート: 呼ばれるたび決定的なプロンプトを返す。"""

    def __init__(self) -> None:
        self._counter = 0

    def generate_batch(self, *, domain: Any, n: int, sampling: Any) -> list[str]:
        del sampling
        out: list[str] = []
        for _ in range(n):
            self._counter += 1
            out.append(f"prompt-{domain.key}-{self._counter}")
        return out

    def next_sampling(self):
        from joryu.seed_gen.generator import SamplingParams

        return SamplingParams(temperature=0.9, top_p=0.95)


def _make_config(domain_key: str = "general_qa", target: int = 5) -> SeedGenConfig:
    return SeedGenConfig(
        version=1,
        target_total=target,
        domains=[
            DomainSpec(
                key=domain_key,
                target=target,
                seed_templates=["{theme}"],
                themes=["テーマ"],
            )
        ],
        legacy_category_aliases={},
    )


def test_estimate_plan_computes_gaps() -> None:
    cfg = _make_config(target=10)
    plan = estimate_plan(cfg, {"general_qa": 3})
    assert plan["remaining_by_domain"]["general_qa"] == 7
    assert plan["remaining_total"] == 7
    assert plan["existing_total"] == 3


def test_run_pipeline_dispatches_by_mode(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    called = {"create": 0, "check": 0}

    def _fake_create(_opts: PipelineOptions) -> int:
        called["create"] += 1
        return 0

    def _fake_check(_opts: PipelineOptions) -> int:
        called["check"] += 1
        return 0

    monkeypatch.setattr("joryu.seed_gen.pipeline.run_create_pipeline", _fake_create)
    monkeypatch.setattr("joryu.seed_gen.pipeline.run_check_pipeline", _fake_check)

    opts = PipelineOptions(
        bank_path=tmp_path / "bank.jsonl",
        state_path=tmp_path / "state.json",
        config=_make_config(),
        mode=SEED_GEN_MODE_CREATE,
    )
    assert run_pipeline(opts) == 0
    opts.mode = SEED_GEN_MODE_CHECK
    assert run_pipeline(opts) == 0
    assert called == {"create": 1, "check": 1}


def test_run_pipeline_rejects_unknown_mode(tmp_path: Path) -> None:
    opts = PipelineOptions(
        bank_path=tmp_path / "bank.jsonl",
        state_path=tmp_path / "state.json",
        config=_make_config(),
        mode="bogus",
    )
    with pytest.raises(ValueError, match="unknown seed_gen mode"):
        run_pipeline(opts)


def test_run_create_pipeline_appends_and_dedups(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """LLM 出力を Stage1 dedup して bank に追記する。"""
    bank = tmp_path / "bank.jsonl"
    state = tmp_path / "state.json"

    monkeypatch.setattr(
        "joryu.seed_gen.pipeline.OpenAICompatibleSeedGenerator",
        lambda **_kwargs: _StubGenerator(),
    )

    cfg = _make_config(target=3)
    opts = PipelineOptions(
        bank_path=bank,
        state_path=state,
        config=cfg,
        mode=SEED_GEN_MODE_CREATE,
        batch_size=2,
        llm_base_url="http://example/v1",
        llm_model="Qwen/Qwen2.5-7B-Instruct-AWQ",
    )
    rc = run_create_pipeline(opts)
    assert rc == 0
    lines = bank.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) >= 3
    parsed = [json.loads(line) for line in lines]
    assert all(row["domain"] == "general_qa" for row in parsed)
    assert state.is_file()


def test_run_create_pipeline_skips_completed_domains(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """既存件数が target の 80% を超える分野はスキップされる。"""
    bank = tmp_path / "bank.jsonl"
    # target=5, existing=4 (>= 5*0.8=4) → 生成不要
    bank.write_text(
        "\n".join(
            json.dumps({"prompt": f"seed-{i}", "domain": "general_qa"}, ensure_ascii=False)
            for i in range(4)
        )
        + "\n",
        encoding="utf-8",
    )
    state = tmp_path / "state.json"

    calls = {"gen": 0}

    class _CountingGen(_StubGenerator):
        def generate_batch(self, *, domain: Any, n: int, sampling: Any) -> list[str]:
            calls["gen"] += 1
            return super().generate_batch(domain=domain, n=n, sampling=sampling)

    monkeypatch.setattr(
        "joryu.seed_gen.pipeline.OpenAICompatibleSeedGenerator",
        lambda **_kwargs: _CountingGen(),
    )

    opts = PipelineOptions(
        bank_path=bank,
        state_path=state,
        config=_make_config(target=5),
        mode=SEED_GEN_MODE_CREATE,
    )
    rc = run_create_pipeline(opts)
    assert rc == 0
    assert calls["gen"] == 0


def test_run_check_pipeline_moves_similar_rows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """類似プロンプトが検出されると rejected ファイルへ隔離され、bank から除去される。"""
    bank = tmp_path / "bank.jsonl"
    duplicate = "同じテーマの質問A"
    rows = [
        {"id": "row-1", "prompt": duplicate, "domain": "general_qa"},
        {"id": "row-2", "prompt": duplicate, "domain": "general_qa"},
        {"id": "row-3", "prompt": "全く別の内容XYZ12345", "domain": "general_qa"},
    ]
    bank.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
        encoding="utf-8",
    )
    rejected = tmp_path / "rejected" / "similar.jsonl"
    state = tmp_path / "state.json"

    monkeypatch.setattr(
        "joryu.seed_gen.pipeline.load_sentence_transformer_backend",
        lambda _model: _StubBackend(),
    )

    opts = PipelineOptions(
        bank_path=bank,
        state_path=state,
        config=_make_config(),
        mode=SEED_GEN_MODE_CHECK,
        sim_threshold=0.99,
        rejected_path=rejected,
    )
    rc = run_check_pipeline(opts)
    assert rc == 0

    remaining = bank.read_text(encoding="utf-8").strip().splitlines()
    ids = [json.loads(line)["id"] for line in remaining]
    assert "row-2" not in ids
    assert "row-1" in ids and "row-3" in ids

    assert rejected.is_file()
    rejected_rows = [json.loads(line) for line in rejected.read_text(encoding="utf-8").splitlines()]
    assert rejected_rows[0]["reason"] == "stage2_similar"
    assert rejected_rows[0]["id"] == "row-2"


def test_run_check_pipeline_returns_zero_when_bank_missing(
    tmp_path: Path,
) -> None:
    opts = PipelineOptions(
        bank_path=tmp_path / "missing.jsonl",
        state_path=tmp_path / "state.json",
        config=_make_config(),
        mode=SEED_GEN_MODE_CHECK,
    )
    assert run_check_pipeline(opts) == 0


def test_run_check_pipeline_small_bank_no_op(tmp_path: Path) -> None:
    bank = tmp_path / "bank.jsonl"
    bank.write_text(
        json.dumps({"id": "only", "prompt": "single", "domain": "general_qa"}) + "\n",
        encoding="utf-8",
    )
    opts = PipelineOptions(
        bank_path=bank,
        state_path=tmp_path / "state.json",
        config=_make_config(),
        mode=SEED_GEN_MODE_CHECK,
    )
    assert run_check_pipeline(opts) == 0
