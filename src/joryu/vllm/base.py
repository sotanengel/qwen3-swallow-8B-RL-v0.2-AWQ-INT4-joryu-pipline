"""HTTP vLLM クライアント共通 base (#256)。"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from joryu.utils.retry import ExponentialBackoff, call_with_retry
from joryu.vllm.common import normalize_vllm_serve_base_url
from joryu.vllm.protocol import VllmError

_DEFAULT_RETRY_BACKOFF = ExponentialBackoff(base=0.5, max_delay=4.0, jitter=0.1)


class HttpVllmBase:
    """base_url / model / timeout / retry policy を共有する HTTP vLLM base。"""

    def __init__(
        self,
        base_url: str,
        *,
        model: str,
        timeout_s: float = 600.0,
        retry_attempts: int = 3,
        retry_backoff: ExponentialBackoff | None = None,
    ) -> None:
        self._base_url = normalize_vllm_serve_base_url(base_url)
        self._model = model
        self._timeout_s = timeout_s
        self._retry_attempts = retry_attempts
        self._retry_backoff = retry_backoff or _DEFAULT_RETRY_BACKOFF

    @property
    def model(self) -> str:
        return self._model

    @property
    def base_url(self) -> str:
        return self._base_url

    def normalized_base_url(self) -> str:
        return self._base_url

    def post_json_with_retry(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        """OpenAI 互換 endpoint へ JSON POST し、retry 付きで dict を返す。"""
        body = json.dumps(payload).encode("utf-8")
        url = f"{self._base_url}{path}"
        req = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        def _post_once() -> dict[str, Any]:
            try:
                with urllib.request.urlopen(req, timeout=self._timeout_s) as resp:
                    return json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", errors="replace")
                raise VllmError(f"vLLM daemon HTTP {exc.code}: {detail}") from exc

        try:
            return call_with_retry(
                _post_once,
                exceptions=(urllib.error.URLError, TimeoutError, OSError),
                attempts=self._retry_attempts,
                backoff=self._retry_backoff,
            )
        except urllib.error.URLError as exc:
            raise VllmError(f"vLLM serve unreachable at {self._base_url}: {exc}") from exc
        except (TimeoutError, OSError) as exc:
            raise VllmError(f"vLLM serve request failed at {self._base_url}: {exc}") from exc


__all__ = ["HttpVllmBase"]
