"""蒸留・curation ジョブのデータモデル。"""

from __future__ import annotations

import argparse
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from joryu.paths import DEFAULT_CONFIG


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobKind(StrEnum):
    DISTILL = "distill"
    CURATE = "curate"
    SEED_GEN = "seed_gen"


@dataclass
class DistillJobSpec:
    """joryu-distill と同等のジョブ仕様。"""

    count: int = 0
    duration: str = ""
    style: list[str] = field(default_factory=list)
    temperature: str = ""
    top_p: str = ""
    config: str = DEFAULT_CONFIG
    tool_ids: list[str] = field(default_factory=list)
    tool_loop: bool = False
    max_turns: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_cli_namespace(cls, args: argparse.Namespace) -> DistillJobSpec:
        """joryu-distill CLI の argparse.Namespace から仕様を構築する。"""
        from joryu.variants import parse_comma_list

        style = parse_comma_list(args.style) if getattr(args, "style", "") else []
        tool_ids = (
            parse_comma_list(getattr(args, "tool_ids", "")) if getattr(args, "tool_ids", "") else []
        )
        max_turns = getattr(args, "max_turns", None)
        return cls(
            count=int(getattr(args, "count", 0)),
            duration=str(getattr(args, "duration", "") or ""),
            style=style,
            temperature=str(getattr(args, "temperature", "") or ""),
            top_p=str(getattr(args, "top_p", "") or ""),
            config=str(getattr(args, "config", DEFAULT_CONFIG) or DEFAULT_CONFIG),
            tool_ids=tool_ids,
            tool_loop=bool(getattr(args, "tool_loop", False)),
            max_turns=int(max_turns) if max_turns is not None else None,
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DistillJobSpec:
        style = data.get("style") or []
        if isinstance(style, str):
            style = [s.strip() for s in style.split(",") if s.strip()]
        tool_ids = data.get("tool_ids") or []
        if isinstance(tool_ids, str):
            tool_ids = [s.strip() for s in tool_ids.split(",") if s.strip()]
        max_turns = data.get("max_turns")
        return cls(
            count=int(data.get("count", 0)),
            duration=str(data.get("duration") or ""),
            style=list(style),
            temperature=str(data.get("temperature") or ""),
            top_p=str(data.get("top_p") or ""),
            config=str(data.get("config") or DEFAULT_CONFIG),
            tool_ids=list(tool_ids),
            tool_loop=bool(data.get("tool_loop", False)),
            max_turns=int(max_turns) if max_turns is not None else None,
        )

    def to_distill_argv(self, *, bank: str = "", out: str = "") -> list[str]:
        """joryu-distill に渡す追加引数 (--config 除く)。"""
        argv: list[str] = ["--count", str(self.count)]
        if self.duration:
            argv.extend(["--duration", self.duration])
        if bank:
            argv.extend(["--bank", bank])
        if out:
            argv.extend(["--out", out])
        if self.style:
            argv.extend(["--style", ",".join(self.style)])
        if self.temperature:
            argv.extend(["--temperature", self.temperature])
        if self.top_p:
            argv.extend(["--top-p", self.top_p])
        if self.tool_ids:
            argv.extend(["--tool-ids", ",".join(self.tool_ids)])
        if self.tool_loop:
            argv.append("--tool-loop")
        if self.max_turns is not None:
            argv.extend(["--max-turns", str(self.max_turns)])
        return argv


@dataclass
class CurateJobSpec:
    """joryu-curate と同等のジョブ仕様。"""

    config: str = DEFAULT_CONFIG
    skip_llm: bool = False
    threshold: float | None = None
    screening: bool = False
    prompt_bank: bool = False
    src: str = ""
    judge_base_url: str = ""

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CurateJobSpec:
        threshold = data.get("threshold")
        return cls(
            config=str(data.get("config") or DEFAULT_CONFIG),
            skip_llm=bool(data.get("skip_llm", False)),
            threshold=float(threshold) if threshold is not None else None,
            screening=bool(data.get("screening", False)),
            prompt_bank=bool(data.get("prompt_bank", False)),
            src=str(data.get("src") or ""),
            judge_base_url=str(data.get("judge_base_url") or ""),
        )

    def to_curate_argv(self) -> list[str]:
        """joryu-curate に渡す追加引数 (--config 除く)。"""
        argv: list[str] = []
        if self.skip_llm:
            argv.append("--skip-llm")
        if self.threshold is not None:
            argv.extend(["--threshold", str(self.threshold)])
        if self.screening:
            argv.append("--screening")
        if self.prompt_bank:
            argv.append("--prompt-bank")
        if self.src:
            argv.extend(["--src", self.src])
        if self.judge_base_url:
            argv.extend(["--judge-base-url", self.judge_base_url])
        return argv


SEED_GEN_MODE_CREATE = "create"
SEED_GEN_MODE_CHECK = "check"
SEED_GEN_MODES = (SEED_GEN_MODE_CREATE, SEED_GEN_MODE_CHECK)


@dataclass
class SeedGenJobSpec:
    """joryu-seed-gen と同等のジョブ仕様。"""

    config: str = DEFAULT_CONFIG
    bank: str = ""
    domains_config: str = ""
    domain: str = ""
    target_total: int = 230000
    mode: str = SEED_GEN_MODE_CREATE
    resume: bool = False
    sim_threshold: float = 0.85
    batch_size: int = 8
    llm_base_url: str = ""
    judge_base_url: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SeedGenJobSpec:
        mode = str(data.get("mode") or SEED_GEN_MODE_CREATE).strip()
        if mode not in SEED_GEN_MODES:
            raise ValueError(f"unknown seed_gen mode: {mode}")
        return cls(
            config=str(data.get("config") or DEFAULT_CONFIG),
            bank=str(data.get("bank") or ""),
            domains_config=str(data.get("domains_config") or ""),
            domain=str(data.get("domain") or ""),
            target_total=int(data.get("target_total", 230000)),
            mode=mode,
            resume=bool(data.get("resume", False)),
            sim_threshold=float(data.get("sim_threshold", 0.85)),
            batch_size=int(data.get("batch_size", 8)),
            llm_base_url=str(data.get("llm_base_url") or ""),
            judge_base_url=str(data.get("judge_base_url") or ""),
        )

    def to_seed_gen_argv(self) -> list[str]:
        argv: list[str] = ["--mode", self.mode]
        if self.bank:
            argv.extend(["--bank", self.bank])
        if self.domains_config:
            argv.extend(["--domains-config", self.domains_config])
        if self.domain:
            argv.extend(["--domain", self.domain])
        argv.extend(["--target-total", str(self.target_total)])
        argv.extend(["--sim-threshold", str(self.sim_threshold)])
        argv.extend(["--batch-size", str(self.batch_size)])
        if self.resume:
            argv.append("--resume")
        if self.llm_base_url:
            argv.extend(["--llm-base-url", self.llm_base_url])
        if self.judge_base_url:
            argv.extend(["--judge-base-url", self.judge_base_url])
        return argv


@dataclass
class JobRecord:
    """永続化されるジョブレコード。"""

    id: str
    kind: JobKind
    spec: DistillJobSpec | CurateJobSpec | SeedGenJobSpec
    status: JobStatus
    created_at: str
    started_at: str | None = None
    finished_at: str | None = None
    exit_code: int | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind.value,
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
        kind = JobKind(data.get("kind", JobKind.DISTILL.value))
        spec_data = data.get("spec") or {}
        if kind == JobKind.CURATE:
            spec: DistillJobSpec | CurateJobSpec | SeedGenJobSpec = CurateJobSpec.from_dict(
                spec_data
            )
        elif kind == JobKind.SEED_GEN:
            spec = SeedGenJobSpec.from_dict(spec_data)
        else:
            spec = DistillJobSpec.from_dict(spec_data)
        return cls(
            id=str(data["id"]),
            kind=kind,
            spec=spec,
            status=JobStatus(data["status"]),
            created_at=str(data["created_at"]),
            started_at=data.get("started_at"),
            finished_at=data.get("finished_at"),
            exit_code=data.get("exit_code"),
            error=data.get("error"),
        )

    @classmethod
    def create(
        cls,
        spec: DistillJobSpec | CurateJobSpec | SeedGenJobSpec,
        *,
        kind: JobKind | None = None,
    ) -> JobRecord:
        if kind is None:
            if isinstance(spec, CurateJobSpec):
                kind = JobKind.CURATE
            elif isinstance(spec, SeedGenJobSpec):
                kind = JobKind.SEED_GEN
            else:
                kind = JobKind.DISTILL
        return cls(
            id=str(uuid.uuid4()),
            kind=kind,
            spec=spec,
            status=JobStatus.QUEUED,
            created_at=datetime.now(UTC).isoformat(),
        )
