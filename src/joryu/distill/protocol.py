"""Distill Stage Protocol (#251)。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from joryu.config import Config
from joryu.prompt_bank import EffectiveSampling, PromptRow
from joryu.tool_executor import ToolExecutor
from joryu.vllm.protocol import SupportsChat


@dataclass
class DistillContext:
    """1 variant 蒸留の共有コンテキスト。"""

    config: Config
    client: SupportsChat
    row: PromptRow
    eff: EffectiveSampling
    model_name: str
    config_hash: str
    messages: list[dict[str, str]]
    turns_holder: dict[str, Any] = field(default_factory=dict)
    executor: ToolExecutor | None = None
    use_tool_loop: bool = False
    no_think_fallback: bool = False


class Stage(Protocol):
    """record を段階的に enrich する Stage。"""

    def process(self, record: dict[str, Any], context: DistillContext) -> dict[str, Any]: ...


__all__ = ["DistillContext", "Stage"]
