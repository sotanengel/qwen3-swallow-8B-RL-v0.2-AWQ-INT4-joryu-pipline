"""Chat persist 後の stats.json 更新 (#300 / Epic #294 Sub#300)。"""

from __future__ import annotations

from pathlib import Path

from joryu.chat.session import ChatColumn, ChatSession, ChatSessionConfig, ChatSessionState
from joryu.chat.turn_persistence import TurnPersistence
from joryu.styles import StylePreset
from joryu.vllm_client import ChatResult


def test_persist_turn_refreshes_stats_json(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "config.yaml").write_text(
        "distill:\n  out_dir: data/distilled\n  out_file: responses.jsonl\n",
        encoding="utf-8",
    )
    stats_calls: list[Path] = []

    def fake_ensure_stats(repo_root: Path, *, force: bool = False, log=None) -> int:
        stats_calls.append(repo_root)
        assert force is True
        return 0

    monkeypatch.setattr("joryu.preflight.ensure_stats_json", fake_ensure_stats)
    monkeypatch.setattr(
        "joryu.preflight.sync_dashboard_responses_copy",
        lambda _root: None,
    )

    preset = StylePreset(style_id="prose", label="散文", instruction="散文。")
    col = ChatColumn(style_id="prose", label="散文")
    out_path = tmp_path / "data" / "distilled" / "responses.jsonl"
    out_path.parent.mkdir(parents=True)
    config = ChatSessionConfig(
        base_system_prompt="base",
        model_name="test-model",
        config_hash="hash",
        tools=(),
        tool_ids=(),
        out_path=out_path,
        repo_root=tmp_path,
        style_presets={"prose": preset},
    )
    state = ChatSessionState(
        session_id="sess-1",
        columns={"prose": col},
        created_at=0.0,
        last_updated_at=0.0,
    )
    session = ChatSession(config=config, state=state)
    chat = ChatResult(
        thinking=None,
        answer="ok",
        finish_reason="stop",
        prompt_tokens=1,
        completion_tokens=1,
        tool_calls=(),
    )
    TurnPersistence().persist_turn(
        session=session,
        style_id="prose",
        system_prompt="sys",
        user_text="q",
        turn_index=0,
        final_chat=chat,
        turns=[],
        sampling={},
    )
    assert stats_calls == [tmp_path]
