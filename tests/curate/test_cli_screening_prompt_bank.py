"""prompt-bank LLM screening CLI tests."""

import json
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
    # cfg.distill.out_dir defaults to "data/distilled", which makes resolve_repo_root()
    # match its "distilled"-parent heuristic against cwd. Pin JORYU_REPO_ROOT to tmp_path
    # so the screening.json/curation.json dashboard writes stay isolated from the real repo tree.
    monkeypatch.setenv("JORYU_REPO_ROOT", str(tmp_path))
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
    # repo-root-relative dashboard writes must land under the isolated JORYU_REPO_ROOT,
    # never in the real repo's dashboard/public/ (regression guard for issue #424).
    assert (tmp_path / "dashboard" / "public" / "screening.json").exists()
    assert (tmp_path / "dashboard" / "public" / "curation.json").exists()


def test_screening_prompt_bank_skips_checked_prompts(
    tmp_path: Path, prompt_bank: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from joryu.core.prompt_bank import PromptRow
    from joryu.seed_gen.check_state import mark_checked, prompt_check_key
    from joryu.seed_gen.writer import load_state, save_state

    state_dir = tmp_path / "data" / "seed_gen"
    state_dir.mkdir(parents=True)
    state_path = state_dir / "state.json"
    rows = prompt_bank.read_text(encoding="utf-8").strip().splitlines()
    first = PromptRow.model_validate(json.loads(rows[0]))
    state = load_state(state_path)
    mark_checked(state, [prompt_check_key(first)])
    save_state(state_path, state)

    dst = tmp_path / "out"
    judge = FakeJudgeClient(prompt_health_scores={k: 5 for k in PROMPT_HEALTH_RUBRIC_KEYS})
    monkeypatch.setenv("JORYU_REPO_ROOT", str(tmp_path))
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
    scores = (dst / "scores.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(scores) == 1

    reloaded = load_state(state_path)
    assert len(reloaded.prompt_check.checked_keys) == 2
