"""distill.py: コアの蒸留ループ (FakeVllmClient ベース)。"""

from __future__ import annotations

import json
from pathlib import Path

from joryu.config import Config
from joryu.distill import run_distill

from .conftest import FakeVllmClient


def _write_bank(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
        encoding="utf-8",
    )


def _load_jsonl(path: Path) -> list[dict]:
    return [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]


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
    assert records[0]["model"] == cfg.model.name
    assert records[0]["sampling"]["temperature"] == cfg.model.temperature
    assert records[0]["sampling"]["top_p"] == cfg.model.top_p
    assert records[0]["sampling"]["max_tokens"] == cfg.model.num_predict
    assert records[0]["config_hash"].startswith("sha256-")
    assert "created_at" in records[0]


def test_run_distill_skips_already_done(tmp_path: Path) -> None:
    bank = tmp_path / "bank.jsonl"
    _write_bank(bank, [{"prompt": "P1"}, {"prompt": "P2"}, {"prompt": "P3"}])
    out = tmp_path / "out.jsonl"
    # 既に P1 と P2 が処理済みであるとする。
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps({"prompt": "P1", "answer": "x"}, ensure_ascii=False)
        + "\n"
        + json.dumps({"prompt": "P2", "answer": "y"}, ensure_ascii=False)
        + "\n",
        encoding="utf-8",
    )

    cfg = Config()
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
            self.calls.append({"messages": messages})
            if len(self.calls) == 2:
                raise RuntimeError("boom")
            return ("T", "A")

    client = _RaisesOnSecond()
    n = run_distill(Config(), bank_path=bank, out_path=out, client=client)
    assert n == 2
    records = _load_jsonl(out)
    assert [r["prompt"] for r in records] == ["P1", "P3"]


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
