"""チャットターンの JSONL 永続化。"""

from __future__ import annotations

from typing import Any

from joryu.chat.persistence import build_chat_record
from joryu.chat.session import ChatSession
from joryu.responses_store import record_id
from joryu.vllm_client import ChatResult
from joryu.writer import JsonlAppendWriter


class TurnPersistence:
    """build_chat_record + JsonlAppendWriter の組。"""

    def persist_turn(
        self,
        *,
        session: ChatSession,
        style_id: str,
        system_prompt: str,
        user_text: str,
        turn_index: int,
        final_chat: ChatResult,
        turns: list[dict[str, Any]],
        sampling: dict[str, Any],
    ) -> tuple[dict[str, Any], str]:
        final_answer = (final_chat.answer or "").strip()
        record = build_chat_record(
            prompt=user_text,
            style_id=style_id,
            system_prompt=system_prompt,
            session_id=session.session_id,
            turn_index=turn_index,
            thinking=final_chat.thinking,
            answer=final_answer,
            model_name=session.model_name,
            config_hash=session.config_hash,
            chat=final_chat,
            turns=turns,
            sampling=sampling,
            tools=session.tools,
            tool_ids=session.tool_ids,
        )
        with JsonlAppendWriter(session.out_path) as writer:
            writer.write(record)
        return record, record_id(record)
