"""蒸留実行中の live 状態 (ダッシュボードアラート用)。"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from joryu.distill_retry import TRUNCATION_RETRY_ALERT_THRESHOLD


@dataclass
class TruncationRetryAlert:
    prompt_preview: str
    style_id: str | None
    attempts: int
    updated_at: str


class DistillLiveState:
    """プロセス内の蒸留 live 状態。stats.json 更新時にマージされる。"""

    _lock = threading.Lock()
    _active = False
    _alerts: dict[str, TruncationRetryAlert] = {}

    @classmethod
    def begin(cls) -> None:
        with cls._lock:
            cls._active = True
            cls._alerts.clear()

    @classmethod
    def end(cls) -> None:
        with cls._lock:
            cls._active = False
            cls._alerts.clear()

    @classmethod
    def report_retry(
        cls,
        *,
        run_key: str,
        prompt: str,
        style_id: str | None,
        attempts: int,
    ) -> None:
        if attempts < TRUNCATION_RETRY_ALERT_THRESHOLD:
            return
        preview = prompt if len(prompt) <= 80 else prompt[:80] + "…"
        with cls._lock:
            cls._alerts[run_key] = TruncationRetryAlert(
                prompt_preview=preview,
                style_id=style_id,
                attempts=attempts,
                updated_at=datetime.now(UTC).isoformat(),
            )

    @classmethod
    def clear_retry(cls, run_key: str) -> None:
        with cls._lock:
            cls._alerts.pop(run_key, None)

    @classmethod
    def to_dict(cls) -> dict[str, Any]:
        with cls._lock:
            return {
                "active": cls._active,
                "truncation_retries": [
                    {
                        "prompt_preview": alert.prompt_preview,
                        "style_id": alert.style_id,
                        "attempts": alert.attempts,
                        "updated_at": alert.updated_at,
                    }
                    for alert in cls._alerts.values()
                ],
            }
