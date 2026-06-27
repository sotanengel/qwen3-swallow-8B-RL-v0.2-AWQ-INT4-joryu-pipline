"""chat 経路の system_prompt 重複防止 (#297 / Epic #294 Sub#3)。"""

from __future__ import annotations

from pathlib import Path

from joryu.chat.streamer import build_column_system_prompt
from joryu.config import load_config
from joryu.datetime_context import format_date_context_ja, now_jst
from joryu.styles import load_styles
from joryu.system_prompt import _FACTUAL_GUARD, build_system_prompt
from joryu.tools import ToolDefinition, load_tools

REPO_ROOT = Path(__file__).resolve().parents[2]


def _session_base_system_prompt() -> str:
    """ChatService.create_session と同じ base 合成。"""
    cfg = load_config(REPO_ROOT / "config.yaml")
    date_context = format_date_context_ja(now_jst())
    base_core = f"{date_context}\n\n{cfg.distill.system_prompt.rstrip()}"
    return build_system_prompt(base=base_core, factual_guard=True)


def _tool_defs() -> list[ToolDefinition]:
    cfg = load_config(REPO_ROOT / "config.yaml")
    tools_map = load_tools(REPO_ROOT / cfg.distill.tools_file)
    return list(tools_map.values())


def test_factual_guard_appears_once_per_style() -> None:
    base = _session_base_system_prompt()
    styles = load_styles(REPO_ROOT / "styles.yaml")
    tool_defs = _tool_defs()
    for style_id in ("prose", "qa_short", "dialog", "report"):
        preset = styles[style_id]
        prompt = build_column_system_prompt(
            base_system_prompt=base,
            tool_defs=tool_defs,
            style_preset=preset,
        )
        assert prompt.count(_FACTUAL_GUARD.strip()) == 1, style_id


def test_chat_path_matches_streamer_helper() -> None:
    """service base + streamer 列合成が LLM に渡す最終 prompt と一致する。"""
    base = _session_base_system_prompt()
    styles = load_styles(REPO_ROOT / "styles.yaml")
    tool_defs = _tool_defs()
    prompt = build_column_system_prompt(
        base_system_prompt=base,
        tool_defs=tool_defs,
        style_preset=styles["prose"],
    )
    assert "仮想データ" in prompt
    assert prompt.index("利用可能なツール:") < prompt.index(styles["prose"].instruction)
