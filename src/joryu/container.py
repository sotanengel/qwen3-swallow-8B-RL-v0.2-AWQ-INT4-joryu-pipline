"""DependencyContainer (#259)。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from joryu.config import Config, load_config
from joryu.config_resolver import resolve_config_path
from joryu.tool_executor import ToolExecutor, build_default_executor
from joryu.vllm.factory import resolve_chat_client
from joryu.vllm.protocol import SupportsChat


@dataclass
class DependencyContainer:
    """CLI / API 共有 DI 容器。"""

    config: Config
    config_path: Path
    chat_client: SupportsChat | None = None
    executor: ToolExecutor | None = None

    @classmethod
    def build(cls, config_path: str | Path | None = None) -> DependencyContainer:
        path = resolve_config_path(config_path)
        cfg = load_config(path)
        client = resolve_chat_client(cfg.model, cfg.vllm)
        return cls(
            config=cfg,
            config_path=path,
            chat_client=client,
            executor=build_default_executor(),
        )


def build_container(config_path: str | Path | None = None) -> DependencyContainer:
    return DependencyContainer.build(config_path)


__all__ = ["DependencyContainer", "build_container"]
