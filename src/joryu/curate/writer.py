"""curate 出力分離書き込み (R-14)。

- responses.high_quality.jsonl   (採用)
- responses.rejected.jsonl       (棄却 + rejected_by)
- scores.jsonl                   (全件のスコア + signal_versions + record_hash)
"""

from __future__ import annotations

from pathlib import Path
from types import TracebackType
from typing import Any

from joryu.writer import JsonlAppendWriter


class CurateWriter:
    """3 ファイルを並行管理する context manager。"""

    HIGH_QUALITY = "responses.high_quality.jsonl"
    REJECTED = "responses.rejected.jsonl"
    SCORES = "scores.jsonl"

    def __init__(self, dst_dir: str | Path) -> None:
        self._dst = Path(dst_dir)
        self._high: JsonlAppendWriter | None = None
        self._rej: JsonlAppendWriter | None = None
        self._scores: JsonlAppendWriter | None = None
        self.kept = 0
        self.rejected = 0
        self.total = 0

    def __enter__(self) -> CurateWriter:
        self._dst.mkdir(parents=True, exist_ok=True)
        self._high = JsonlAppendWriter(self._dst / self.HIGH_QUALITY).__enter__()
        self._rej = JsonlAppendWriter(self._dst / self.REJECTED).__enter__()
        self._scores = JsonlAppendWriter(self._dst / self.SCORES).__enter__()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        for w in (self._high, self._rej, self._scores):
            if w is not None:
                w.__exit__(exc_type, exc, tb)

    def write(
        self,
        record: dict[str, Any],
        *,
        accepted: bool,
        final_score: float,
        rejected_by: list[str],
        signal_versions: dict[str, str],
        signal_scores: dict[str, float],
        signal_raw: dict[str, object],
        record_hash: str,
    ) -> None:
        assert self._high is not None and self._rej is not None and self._scores is not None
        self.total += 1
        score_row = {
            "record_hash": record_hash,
            "prompt": record.get("prompt"),
            "config_hash": record.get("config_hash"),
            "mode": record.get("mode"),
            "style_id": record.get("style_id"),
            "category": record.get("category"),
            "final_score": final_score,
            "accepted": accepted,
            "rejected_by": rejected_by,
            "signal_versions": signal_versions,
            "signal_scores": signal_scores,
            "signal_raw": signal_raw,
        }
        self._scores.write(score_row)
        if accepted:
            self.kept += 1
            self._high.write(record)
        else:
            self.rejected += 1
            out = dict(record)
            out["rejected_by"] = rejected_by
            out["final_score"] = final_score
            self._rej.write(out)
