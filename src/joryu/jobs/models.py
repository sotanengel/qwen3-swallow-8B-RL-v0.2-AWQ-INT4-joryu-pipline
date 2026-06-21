"""蒸留ジョブのデータモデル。"""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


@dataclass
class DistillJobSpec:
    """joryu-distill と同等のジョブ仕様。"""

    count: int = 0
    duration: str = ""
    mode: str | None = None
    style: list[str] = field(default_factory=list)
    temperature: str = ""
    top_p: str = ""
    config: str = "config.yaml"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DistillJobSpec:
        style = data.get("style") or []
        if isinstance(style, str):
            style = [s.strip() for s in style.split(",") if s.strip()]
        return cls(
            count=int(data.get("count", 0)),
            duration=str(data.get("duration") or ""),
            mode=data.get("mode"),
            style=list(style),
            temperature=str(data.get("temperature") or ""),
            top_p=str(data.get("top_p") or ""),
            config=str(data.get("config") or "config.yaml"),
        )

    def to_distill_argv(self) -> list[str]:
        """joryu-distill に渡す追加引数 (--config 除く)。"""
        argv: list[str] = ["--count", str(self.count)]
        if self.duration:
            argv.extend(["--duration", self.duration])
        if self.mode:
            argv.extend(["--mode", self.mode])
        if self.style:
            argv.extend(["--style", ",".join(self.style)])
        if self.temperature:
            argv.extend(["--temperature", self.temperature])
        if self.top_p:
            argv.extend(["--top-p", self.top_p])
        return argv


@dataclass
class JobRecord:
    """永続化されるジョブレコード。"""

    id: str
    spec: DistillJobSpec
    status: JobStatus
    created_at: str
    started_at: str | None = None
    finished_at: str | None = None
    exit_code: int | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "spec": self.spec.to_dict(),
            "status": self.status.value,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "exit_code": self.exit_code,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> JobRecord:
        return cls(
            id=str(data["id"]),
            spec=DistillJobSpec.from_dict(data.get("spec") or {}),
            status=JobStatus(data["status"]),
            created_at=str(data["created_at"]),
            started_at=data.get("started_at"),
            finished_at=data.get("finished_at"),
            exit_code=data.get("exit_code"),
            error=data.get("error"),
        )

    @classmethod
    def create(cls, spec: DistillJobSpec) -> JobRecord:
        return cls(
            id=str(uuid.uuid4()),
            spec=spec,
            status=JobStatus.QUEUED,
            created_at=datetime.now(UTC).isoformat(),
        )
