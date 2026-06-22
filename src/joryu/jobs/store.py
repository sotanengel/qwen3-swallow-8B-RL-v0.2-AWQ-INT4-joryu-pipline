"""ファイルベースのジョブ永続化。"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

from joryu.jobs.models import JobRecord


class JobStore:
    """data/jobs/<id>.json と <id>.log を管理する。"""

    def __init__(self, jobs_dir: Path) -> None:
        self.jobs_dir = jobs_dir
        self.jobs_dir.mkdir(parents=True, exist_ok=True)

    def _record_path(self, job_id: str) -> Path:
        return self.jobs_dir / f"{job_id}.json"

    def log_path(self, job_id: str) -> Path:
        return self.jobs_dir / f"{job_id}.log"

    def save(self, record: JobRecord) -> None:
        path = self._record_path(record.id)
        payload = json.dumps(record.to_dict(), ensure_ascii=False, indent=2)
        tmp = path.with_suffix(f"{path.suffix}.tmp")
        tmp.write_text(payload, encoding="utf-8")
        # Windows では他スレッドが読み取り中だと os.replace が一時的に
        # PermissionError を投げることがあるため、短い retry を入れる。
        for attempt in range(10):
            try:
                os.replace(tmp, path)
                return
            except PermissionError:
                if attempt == 9:
                    raise
                time.sleep(0.02)

    def load(self, job_id: str) -> JobRecord:
        path = self._record_path(job_id)
        if not path.exists():
            raise FileNotFoundError(f"job not found: {job_id}")
        data = json.loads(path.read_text(encoding="utf-8"))
        return JobRecord.from_dict(data)

    def list_all(self) -> list[JobRecord]:
        records: list[JobRecord] = []
        for path in self.jobs_dir.glob("*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                records.append(JobRecord.from_dict(data))
            except (json.JSONDecodeError, KeyError, ValueError):
                continue
        records.sort(key=lambda r: r.created_at, reverse=True)
        return records

    def read_log(self, job_id: str, *, offset: int = 0) -> tuple[str, int]:
        path = self.log_path(job_id)
        if not path.exists():
            return "", 0
        text = path.read_text(encoding="utf-8", errors="replace")
        if offset < 0:
            offset = 0
        if offset >= len(text):
            return "", len(text)
        return text[offset:], len(text)

    def append_log(self, job_id: str, chunk: str) -> None:
        path = self.log_path(job_id)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(chunk)
