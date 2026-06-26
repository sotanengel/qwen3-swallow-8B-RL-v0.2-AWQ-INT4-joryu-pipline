"""token_stream のテスト。"""

from __future__ import annotations

import asyncio

from joryu.chat.token_stream import TokenStreamer, chunk_text


def test_chunk_text_empty() -> None:
    assert chunk_text("") == [""]


def test_chunk_text_splits() -> None:
    assert chunk_text("abcdefgh", size=4) == ["abcd", "efgh"]
    assert chunk_text("abcdefghi", size=4) == ["abcd", "efgh", "i"]


def test_token_streamer_yields_events() -> None:
    streamer = TokenStreamer(chunk_size=3)

    async def collect() -> list[dict[str, object]]:
        events = []
        async for event in streamer.stream("prose", "hello"):
            events.append(event)
        return events

    events = asyncio.run(collect())
    assert len(events) == 2
    assert events[0] == {"type": "token", "column": "prose", "delta": "hel"}
    assert events[1] == {"type": "token", "column": "prose", "delta": "lo"}
