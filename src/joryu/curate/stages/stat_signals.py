"""Stat signal CurateStage (#258)。"""

from __future__ import annotations

from joryu.curate.signals import Signal, SignalResult
from joryu.curate.stage import CurateContext


class StatSignalsStage:
    """統計シグナル群を評価する Stage。"""

    name = "stat_signals"

    def __init__(self, signals: tuple[Signal, ...]) -> None:
        self._signals = signals

    def apply(self, context: CurateContext) -> CurateContext:
        results: list[SignalResult] = list(context.signal_results)
        for signal in self._signals:
            results.append(signal.evaluate(context.record))
        context.signal_results = results
        return context


__all__ = ["StatSignalsStage"]
