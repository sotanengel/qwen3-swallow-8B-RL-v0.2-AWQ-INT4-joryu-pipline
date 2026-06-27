"""prompt-bank LLM screening CLI tests."""

from pathlib import Path

import pytest

from joryu.cli.curate import main as curate_main
from joryu.curate.judge_client import PROMPT_HEALTH_RUBRIC_KEYS, FakeJudgeClient


@pytest.fixture
def prompt_bank(tmp_path: Path) -> Path:
    p = tmp_path / "prompts.jsonl"
    p.write_text(
        "\n".join(
            [
                '{"prompt":"桜について説明してください","domain":"general_qa"}',
                '{"prompt":"2+2を計算してください","domain":"math"}',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return p


def test_screening_prompt_bank_llm_only(
    tmp_path: Path, prompt_bank: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dst = tmp_path / "out"
    judge = FakeJudgeClient(prompt_health_scores={k: 5 for k in PROMPT_HEALTH_RUBRIC_KEYS})
    monkeypatch.setenv("JORYU_CURATE_FAKE_JUDGE", "0")
    rc = curate_main(
        [
            "--screening",
            "--prompt-bank",
            "--no-resume",
            "--src",
            str(prompt_bank),
            "--dst",
            str(dst),
        ],
        _judge=judge,
    )
    assert rc == 0
    assert (dst / "screening.ok.jsonl").exists()
    scores = (dst / "scores.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(scores) == 2
