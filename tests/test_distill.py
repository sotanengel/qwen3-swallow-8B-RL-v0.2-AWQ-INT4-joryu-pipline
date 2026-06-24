"""distill.py: コアの蒸留ループ (FakeVllmClient ベース)。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from joryu.config import Config
from joryu.distill import run_distill
from tests.helpers.jsonl import read_jsonl, write_jsonl

from .conftest import FakeVllmClient


def _write_bank(path: Path, rows: list[dict]) -> None:
    write_jsonl(path, rows)


def _load_jsonl(path: Path) -> list[dict]:
    return read_jsonl(path)


def test_run_distill_writes_records(tmp_path: Path) -> None:
    bank = tmp_path / "bank.jsonl"
    _write_bank(bank, [{"prompt": "P1", "category": "国語"}, {"prompt": "P2"}])
    out = tmp_path / "out.jsonl"
    cfg = Config()
    client = FakeVllmClient(answer="A", thinking="T")

    n = run_distill(cfg, bank_path=bank, out_path=out, client=client)

    assert n == 2
    records = _load_jsonl(out)
    assert [r["prompt"] for r in records] == ["P1", "P2"]
    assert records[0]["category"] == "国語"
    assert records[0]["answer"] == "A"
    assert records[0]["thinking_trace"] == "T"
    assert records[0]["mode"] == "thinking"
    assert records[0]["effective_mode"] == "thinking"
    assert records[0]["model"] == cfg.model.name
    assert records[0]["sampling"]["temperature"] == cfg.model.temperature
    assert records[0]["sampling"]["top_p"] == cfg.model.top_p
    assert records[0]["sampling"]["max_tokens"] == cfg.model.num_predict
    assert records[0]["config_hash"].startswith("sha256-")
    assert records[0]["tools"] == []
    assert records[0]["tool_calls"] == []
    assert records[0]["tool_ids_requested"] == []
    assert records[0]["turns"] == []
    assert records[0]["finish_reason"] == "stop"
    assert records[0]["prompt_tokens"] == 10
    assert records[0]["completion_tokens"] == 5
    assert "created_at" in records[0]


def _done_record(prompt: str, cfg: Config, **extra: object) -> dict:
    rec = {
        "prompt": prompt,
        "answer": "x",
        "mode": cfg.model.mode,
        "style_id": None,
        "sampling": {
            "temperature": cfg.model.temperature,
            "top_p": cfg.model.top_p,
        },
    }
    rec.update(extra)
    return rec


def test_run_distill_skips_already_done(tmp_path: Path) -> None:
    bank = tmp_path / "bank.jsonl"
    _write_bank(bank, [{"prompt": "P1"}, {"prompt": "P2"}, {"prompt": "P3"}])
    out = tmp_path / "out.jsonl"
    cfg = Config()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(_done_record("P1", cfg), ensure_ascii=False)
        + "\n"
        + json.dumps(_done_record("P2", cfg), ensure_ascii=False)
        + "\n",
        encoding="utf-8",
    )

    client = FakeVllmClient(answer="A", thinking="T")
    n = run_distill(cfg, bank_path=bank, out_path=out, client=client)

    assert n == 1
    assert len(client.calls) == 1
    assert client.calls[0]["messages"][-1]["content"] == "P3"


def test_count_cap_limits_new_records(tmp_path: Path) -> None:
    bank = tmp_path / "bank.jsonl"
    _write_bank(bank, [{"prompt": f"P{i}"} for i in range(5)])
    out = tmp_path / "out.jsonl"
    cfg = Config()
    client = FakeVllmClient(answer="A")
    n = run_distill(cfg, bank_path=bank, out_path=out, client=client, count=2)
    assert n == 2
    assert len(_load_jsonl(out)) == 2


def test_row_mode_nothinking_disables_thinking_for_that_row(tmp_path: Path) -> None:
    bank = tmp_path / "bank.jsonl"
    _write_bank(
        bank,
        [
            {"prompt": "P1"},
            {"prompt": "P2", "mode": "nothinking"},
        ],
    )
    out = tmp_path / "out.jsonl"
    cfg = Config()  # defaults thinking
    client = FakeVllmClient(answer="A", thinking="T")
    run_distill(cfg, bank_path=bank, out_path=out, client=client)

    assert client.calls[0]["enable_thinking"] is True
    assert client.calls[1]["enable_thinking"] is False

    records = _load_jsonl(out)
    assert records[0]["mode"] == "thinking"
    assert records[0]["thinking_trace"] == "T"
    assert records[1]["mode"] == "nothinking"
    assert records[1]["thinking_trace"] is None
    assert records[1]["effective_mode"] == "nothinking"


def test_mode_auto_passes_none_enable_thinking(tmp_path: Path) -> None:
    bank = tmp_path / "bank.jsonl"
    _write_bank(bank, [{"prompt": "P1", "mode": "auto"}])
    out = tmp_path / "out.jsonl"
    cfg = Config()
    client = FakeVllmClient(answer="A", thinking="T")
    run_distill(cfg, bank_path=bank, out_path=out, client=client)

    assert client.calls[0]["enable_thinking"] is None
    rec = _load_jsonl(out)[0]
    assert rec["mode"] == "auto"
    assert rec["effective_mode"] == "thinking"
    assert rec["thinking_trace"] == "T"


def test_mode_auto_without_thinking_records_nothinking_effective(tmp_path: Path) -> None:
    bank = tmp_path / "bank.jsonl"
    _write_bank(bank, [{"prompt": "P1", "mode": "auto"}])
    out = tmp_path / "out.jsonl"
    cfg = Config()
    client = FakeVllmClient(answer="A", thinking=None)
    run_distill(cfg, bank_path=bank, out_path=out, client=client)

    rec = _load_jsonl(out)[0]
    assert rec["mode"] == "auto"
    assert rec["effective_mode"] == "nothinking"
    assert rec["thinking_trace"] is None


def test_mode_sweep_expands_variants(tmp_path: Path) -> None:
    bank = tmp_path / "bank.jsonl"
    _write_bank(bank, [{"prompt": "P1"}])
    out = tmp_path / "out.jsonl"
    cfg = Config()
    client = FakeVllmClient(answer="A", thinking="T")
    n = run_distill(
        cfg,
        bank_path=bank,
        out_path=out,
        client=client,
        modes=["thinking", "nothinking", "auto"],
    )
    assert n == 3
    records = _load_jsonl(out)
    assert {r["mode"] for r in records} == {"thinking", "nothinking", "auto"}
    enable_flags = [c["enable_thinking"] for c in client.calls]
    assert enable_flags == [True, False, None]


def test_global_mode_override_applies_when_row_missing(tmp_path: Path) -> None:
    bank = tmp_path / "bank.jsonl"
    _write_bank(bank, [{"prompt": "P1"}])
    out = tmp_path / "out.jsonl"
    cfg = Config()
    cfg.model.mode = "nothinking"
    client = FakeVllmClient(answer="A", thinking="T")
    run_distill(cfg, bank_path=bank, out_path=out, client=client)

    assert client.calls[0]["enable_thinking"] is False
    rec = _load_jsonl(out)[0]
    assert rec["mode"] == "nothinking"
    assert rec["thinking_trace"] is None


def test_per_row_sampling_overrides_passed_and_recorded(tmp_path: Path) -> None:
    bank = tmp_path / "bank.jsonl"
    _write_bank(
        bank,
        [
            {
                "prompt": "P1",
                "sampling": {"temperature": 0.1, "max_tokens": 256},
            }
        ],
    )
    out = tmp_path / "out.jsonl"
    cfg = Config()
    client = FakeVllmClient(answer="A")
    run_distill(cfg, bank_path=bank, out_path=out, client=client)

    s = client.calls[0]["sampling"]
    assert s["temperature"] == 0.1
    assert s["max_tokens"] == 256
    # row 未指定のキーは config 既定値
    assert s["top_p"] == cfg.model.top_p
    assert s["top_k"] == cfg.model.top_k

    rec = _load_jsonl(out)[0]
    assert rec["sampling"]["temperature"] == 0.1
    assert rec["sampling"]["max_tokens"] == 256


def test_system_prompt_override_per_row(tmp_path: Path) -> None:
    bank = tmp_path / "bank.jsonl"
    _write_bank(bank, [{"prompt": "P1", "system_prompt": "丁寧に文語体で"}])
    out = tmp_path / "out.jsonl"
    cfg = Config()
    client = FakeVllmClient(answer="A")
    run_distill(cfg, bank_path=bank, out_path=out, client=client)

    msgs = client.calls[0]["messages"]
    assert msgs[0]["role"] == "system"
    assert msgs[0]["content"] == "丁寧に文語体で"
    assert msgs[1]["role"] == "user"
    assert msgs[1]["content"] == "P1"


def test_client_exception_skips_row_continues(tmp_path: Path) -> None:
    bank = tmp_path / "bank.jsonl"
    _write_bank(bank, [{"prompt": "P1"}, {"prompt": "P2"}, {"prompt": "P3"}])
    out = tmp_path / "out.jsonl"

    class _RaisesOnSecond(FakeVllmClient):
        def chat_via_template(self, messages, **kw):  # type: ignore[override]
            from joryu.vllm_client import ChatResult

            self.calls.append({"messages": messages})
            if len(self.calls) == 2:
                raise RuntimeError("boom")
            return ChatResult(
                thinking="T",
                answer="A",
                finish_reason="stop",
                prompt_tokens=1,
                completion_tokens=1,
            )

    client = _RaisesOnSecond()
    n = run_distill(Config(), bank_path=bank, out_path=out, client=client)
    assert n == 2
    records = _load_jsonl(out)
    assert [r["prompt"] for r in records] == ["P1", "P3"]


def test_vllm_load_failure_aborts_job(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from joryu.vllm_client import VllmError

    bank = tmp_path / "bank.jsonl"
    _write_bank(bank, [{"prompt": "P1"}, {"prompt": "P2"}])
    out = tmp_path / "out.jsonl"

    class _LoadFailure(FakeVllmClient):
        def chat_via_template(self, messages, **kw):  # type: ignore[override]
            raise VllmError("failed to load vLLM model: Engine core initialization failed")

    client = _LoadFailure()
    n = run_distill(Config(), bank_path=bank, out_path=out, client=client)
    assert n == 0
    assert len(client.calls) == 0
    err = capsys.readouterr().err
    assert "vLLM ロード失敗" in err
    assert "joryu-probe-vllm" in err
    assert "joryu-up" in err


def test_run_distill_redo_truncated_reprocesses_matching_keys(tmp_path: Path) -> None:
    bank = tmp_path / "bank.jsonl"
    _write_bank(bank, [{"prompt": "P1"}, {"prompt": "P2"}])
    out = tmp_path / "out.jsonl"
    cfg = Config()
    out.parent.mkdir(parents=True, exist_ok=True)
    truncated = {
        "prompt": "P1",
        "answer": "途中で切れた見出し\n\n## 1. 章",
        "mode": cfg.model.mode,
        "style_id": None,
        "sampling": {"temperature": cfg.model.temperature, "top_p": cfg.model.top_p},
    }
    complete = _done_record("P2", cfg)
    out.write_text(
        json.dumps(truncated, ensure_ascii=False)
        + "\n"
        + json.dumps(complete, ensure_ascii=False)
        + "\n",
        encoding="utf-8",
    )
    client = FakeVllmClient(answer="完結した回答。")
    n = run_distill(cfg, bank_path=bank, out_path=out, client=client, redo_truncated=True)
    assert n == 1
    assert len(client.calls) == 1
    assert client.calls[0]["messages"][-1]["content"] == "P1"
    records = _load_jsonl(out)
    assert len(records) == 3


def test_deadline_stops_loop(tmp_path: Path) -> None:
    bank = tmp_path / "bank.jsonl"
    _write_bank(bank, [{"prompt": f"P{i}"} for i in range(5)])
    out = tmp_path / "out.jsonl"
    cfg = Config()
    client = FakeVllmClient(answer="A")
    # deadline = 過去時刻 -> 1 件も処理しない
    import time

    n = run_distill(cfg, bank_path=bank, out_path=out, client=client, deadline=time.time() - 1)
    assert n == 0
    assert not out.exists() or out.read_text(encoding="utf-8") == ""


def test_run_distill_style_temperature_cartesian(tmp_path: Path) -> None:
    from joryu.styles import load_styles

    bank = tmp_path / "bank.jsonl"
    _write_bank(bank, [{"prompt": "P1"}])
    out = tmp_path / "out.jsonl"
    cfg = Config()
    styles = load_styles("styles.yaml")
    client = FakeVllmClient(answer="A")
    n = run_distill(
        cfg,
        bank_path=bank,
        out_path=out,
        client=client,
        style_presets=[styles["polite"], styles["casual"]],
        temperatures=[0.5, 0.8],
    )
    assert n == 4
    records = _load_jsonl(out)
    assert len(records) == 4
    style_ids = {r["style_id"] for r in records}
    temps = {r["sampling"]["temperature"] for r in records}
    assert style_ids == {"polite", "casual"}
    assert temps == {0.5, 0.8}


def test_run_distill_same_prompt_different_style_not_skipped(tmp_path: Path) -> None:
    from joryu.styles import load_styles

    bank = tmp_path / "bank.jsonl"
    _write_bank(bank, [{"prompt": "P1"}])
    out = tmp_path / "out.jsonl"
    cfg = Config()
    styles = load_styles("styles.yaml")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(
            _done_record("P1", cfg, style_id="polite"),
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    client = FakeVllmClient(answer="A")
    n = run_distill(
        cfg,
        bank_path=bank,
        out_path=out,
        client=client,
        style_presets=[styles["casual"]],
    )
    assert n == 1
    rec = _load_jsonl(out)[-1]
    assert rec["style_id"] == "casual"


def test_logs_progress_messages(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    bank = tmp_path / "bank.jsonl"
    _write_bank(bank, [{"prompt": "P1"}, {"prompt": "P2"}])
    out = tmp_path / "out.jsonl"
    cfg = Config()
    client = FakeVllmClient(answer="ans")

    run_distill(cfg, bank_path=bank, out_path=out, client=client)

    err = capsys.readouterr().err
    assert "[joryu-distill] 全体 2件" in err
    assert "進捗 1/2" in err
    assert "進捗 2/2" in err
    assert "直近の完了" in err
    assert "P1" in err
    assert "ans" in err
    assert f"完了: 2 件 → {out}" in err


def test_run_distill_calls_stats_refresher_after_writes(tmp_path: Path) -> None:
    bank = tmp_path / "bank.jsonl"
    _write_bank(bank, [{"prompt": "P1"}, {"prompt": "P2"}])
    out = tmp_path / "out.jsonl"
    cfg = Config()
    client = FakeVllmClient(answer="A")
    calls: list[Path] = []

    run_distill(
        cfg,
        bank_path=bank,
        out_path=out,
        client=client,
        stats_refresher=calls.append,
    )

    assert calls == [out, out]


def test_default_stats_refresher_writes_under_repo_root(tmp_path: Path) -> None:
    from joryu.distill import default_stats_refresher

    out = tmp_path / "data" / "distilled" / "responses.jsonl"
    out.parent.mkdir(parents=True)
    out.write_text('{"prompt":"P","answer":"A","model":"M"}\n', encoding="utf-8")
    stats_path = tmp_path / "dashboard" / "public" / "stats.json"

    default_stats_refresher(out)

    assert stats_path.exists()
    data = json.loads(stats_path.read_text(encoding="utf-8"))
    assert data["total"] == 1


def test_run_distill_stats_refresher_is_throttled(tmp_path: Path) -> None:
    out = tmp_path / "out.jsonl"
    calls: list[float] = []
    tick = {"now": 0.0}

    def time_fn() -> float:
        return tick["now"]

    def refresher(_out: Path) -> None:
        calls.append(tick["now"])

    from joryu.distill import _StatsRefreshThrottler

    throttler = _StatsRefreshThrottler(
        out,
        refresher,
        interval_sec=10.0,
        time_fn=time_fn,
    )
    for _ in range(5):
        throttler.maybe_refresh()
        tick["now"] += 1.0
    throttler.maybe_refresh(force=True)

    assert calls == [0.0, 5.0]


def test_run_distill_retries_truncated_until_complete(tmp_path: Path) -> None:
    bank = tmp_path / "bank.jsonl"
    _write_bank(bank, [{"prompt": "P1"}])
    out = tmp_path / "out.jsonl"
    cfg = Config()
    client = FakeVllmClient(
        finish_reasons=["length", "stop"],
        answers=["途中\n\n## 1. 章", "完結した回答。"],
    )
    n = run_distill(cfg, bank_path=bank, out_path=out, client=client)
    assert n == 1
    assert len(client.calls) == 2
    records = _load_jsonl(out)
    assert len(records) == 1
    assert records[0]["answer"] == "完結した回答。"
    assert records[0]["generation_attempts"] == 2


def test_run_distill_skips_write_when_truncated_and_deadline_hit(tmp_path: Path) -> None:
    import time

    bank = tmp_path / "bank.jsonl"
    _write_bank(bank, [{"prompt": "P1"}])
    out = tmp_path / "out.jsonl"
    cfg = Config()
    client = FakeVllmClient(
        finish_reason="length",
        answer="途中\n\n## 1. 章",
    )
    n = run_distill(
        cfg,
        bank_path=bank,
        out_path=out,
        client=client,
        deadline=time.time() + 0.05,
    )
    assert n == 0
    assert not out.exists() or out.read_text(encoding="utf-8") == ""


def test_run_distill_records_generation_attempts_after_many_retries(tmp_path: Path) -> None:
    bank = tmp_path / "bank.jsonl"
    _write_bank(bank, [{"prompt": "P1"}])
    out = tmp_path / "out.jsonl"
    cfg = Config()
    client = FakeVllmClient(
        finish_reasons=["length", "length", "length", "stop"],
        answers=[
            "a\n\n## h",
            "b\n\n## h",
            "c\n\n## h",
            "完結した回答。",
        ],
    )
    n = run_distill(cfg, bank_path=bank, out_path=out, client=client)
    assert n == 1
    assert len(client.calls) == 4
    rec = _load_jsonl(out)[0]
    assert rec["generation_attempts"] == 4


def test_run_distill_records_tool_calls(tmp_path: Path) -> None:
    bank = tmp_path / "bank.jsonl"
    _write_bank(
        bank,
        [{"prompt": "天気を調べて", "tool_ids": ["search"]}],
    )
    out = tmp_path / "out.jsonl"
    cfg = Config()
    tool_call = '<tool_call>{"name":"search","arguments":{"query":"東京 天気"}}</tool_call>'
    client = FakeVllmClient(answer=tool_call + "\n要約です。", thinking=None)
    run_distill(cfg, bank_path=bank, out_path=out, client=client)

    assert client.calls[0]["tools"] is not None
    assert len(client.calls[0]["tools"]) == 1
    assert client.calls[0]["tools"][0]["function"]["name"] == "search"

    rec = _load_jsonl(out)[0]
    assert rec["tool_ids_requested"] == ["search"]
    assert len(rec["tools"]) == 1
    assert rec["tools"][0]["function"]["name"] == "search"
    assert len(rec["tool_calls"]) == 1
    assert rec["tool_calls"][0]["name"] == "search"
    assert rec["turns"] == []


def test_variant_run_key_differs_by_tools(tmp_path: Path) -> None:
    from joryu.distill import variant_run_key
    from joryu.prompt_bank import EffectiveSampling, PromptRow
    from joryu.variants import DistillVariant

    row = PromptRow(prompt="P1")
    search_tool = {
        "type": "function",
        "function": {"name": "search", "description": "d", "parameters": {}},
    }
    calc_tool = {
        "type": "function",
        "function": {"name": "calc", "description": "d", "parameters": {}},
    }
    eff_a = EffectiveSampling(
        mode="thinking",
        system_prompt="sys",
        sampling={"temperature": 0.6, "top_p": 0.95},
        tools=[search_tool],
    )
    eff_b = EffectiveSampling(
        mode="thinking",
        system_prompt="sys",
        sampling={"temperature": 0.6, "top_p": 0.95},
        tools=[calc_tool],
    )
    key_a = variant_run_key(DistillVariant(row=row, eff=eff_a))
    key_b = variant_run_key(DistillVariant(row=row, eff=eff_b))
    assert key_a != key_b
