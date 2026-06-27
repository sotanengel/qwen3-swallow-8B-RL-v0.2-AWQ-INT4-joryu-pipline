"""chat/sse.py の disconnect / cancel テスト。"""

from __future__ import annotations

import asyncio

from joryu.chat.sse import monitor_client_disconnect


class _FakeRequest:
    def __init__(self, *, disconnected_after: int = 1) -> None:
        self._calls = 0
        self._disconnected_after = disconnected_after

    async def is_disconnected(self) -> bool:
        self._calls += 1
        return self._calls >= self._disconnected_after


def test_monitor_client_disconnect_sets_cancel_event_quickly() -> None:
    async def _run() -> None:
        cancel_event = asyncio.Event()
        request = _FakeRequest(disconnected_after=1)
        await asyncio.wait_for(
            monitor_client_disconnect(request, cancel_event, poll_interval=0.01),
            timeout=1.0,
        )
        assert cancel_event.is_set()

    asyncio.run(_run())


def test_tool_loop_stops_when_cancel_event_set() -> None:
    from joryu.chat.tool_loop import ToolLoopRunner
    from tests.conftest import FakeVllmClient

    async def _collect() -> list[dict]:
        cancel_event = asyncio.Event()
        cancel_event.set()
        client = FakeVllmClient(answers=["hello"])
        runner = ToolLoopRunner(max_turns=2)
        events: list[dict] = []
        async for event in runner.run(
            column_id="prose",
            working_messages=[{"role": "system", "content": "base"}],
            column_messages=[],
            tools=None,
            executor=None,
            client=client,
            sampling={"temperature": 0.7},
            cancel_event=cancel_event,
        ):
            events.append(event)
        return events

    events = asyncio.run(_collect())
    assert events
    assert events[-1]["type"] == "_tool_loop_done"
