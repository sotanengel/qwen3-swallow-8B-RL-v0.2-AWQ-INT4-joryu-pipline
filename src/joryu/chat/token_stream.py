"""SSE token チャンク出力。"""

from __future__ import annotations

from collections.abc import AsyncIterator

TOKEN_CHUNK_SIZE = 8


def chunk_text(text: str, size: int = TOKEN_CHUNK_SIZE) -> list[str]:
    if not text:
        return [""]
    return [text[i : i + size] for i in range(0, len(text), size)]


class TokenStreamer:
    """テキストを token SSE イベントに分割する。"""

    def __init__(self, *, chunk_size: int = TOKEN_CHUNK_SIZE) -> None:
        self._chunk_size = chunk_size

    async def stream(self, column_id: str, text: str) -> AsyncIterator[dict[str, object]]:
        for chunk in chunk_text(text, self._chunk_size):
            yield {"type": "token", "column": column_id, "delta": chunk}
