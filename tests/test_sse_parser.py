"""SSE format_sse / merge_streams のパーサ・エラー経路テスト。"""

from __future__ import annotations

import asyncio
import json

from joryu.chat.sse import format_sse, merge_streams


def test_sse_parser_format_sse_roundtrip() -> None:
    payload = {"type": "token", "column": "prose", "delta": "hello"}
    rendered = format_sse(dict(payload))
    assert rendered.startswith("event: token\n")
    assert "data:" in rendered
    data_line = next(line for line in rendered.splitlines() if line.startswith("data: "))
    parsed = json.loads(data_line.removeprefix("data: "))
    assert parsed["column"] == "prose"
    assert parsed["delta"] == "hello"


def test_sse_parser_merge_streams_malformed_stream_yields_error() -> None:
    async def _failing_stream():
        raise ValueError("malformed upstream")
        yield {"type": "token"}  # pragma: no cover

    async def _ok_stream():
        yield {"type": "token", "column": "prose", "delta": "x"}

    async def _collect() -> list[dict]:
        events: list[dict] = []
        async for event in merge_streams(
            [
                ("bad", _failing_stream()),
                ("good", _ok_stream()),
            ],
        ):
            events.append(event)
        return events

    events = asyncio.run(_collect())
    error_events = [e for e in events if e.get("type") == "error"]
    assert len(error_events) == 1
    assert error_events[0]["column"] == "bad"
    assert "malformed upstream" in error_events[0]["message"]
    done_events = [e for e in events if e.get("type") == "column_done"]
    assert any(e["column"] == "bad" and e["finish_reason"] == "error" for e in done_events)


def test_sse_parser_merge_streams_completes_after_slow_stream() -> None:
    async def _slow_stream():
        await asyncio.sleep(0.05)
        yield {"type": "token", "column": "prose", "delta": "late"}

    async def _collect() -> list[dict]:
        events: list[dict] = []

        async def _inner() -> None:
            async for event in merge_streams([("slow", _slow_stream())]):
                events.append(event)

        await asyncio.wait_for(_inner(), timeout=0.5)
        return events

    events = asyncio.run(_collect())
    assert events
    assert events[0]["delta"] == "late"
