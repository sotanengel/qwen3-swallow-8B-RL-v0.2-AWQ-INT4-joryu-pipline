"""JSONL atomic 追記と state.json (#320)。"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from joryu.io.jsonl import iter_jsonl
from joryu.prompt_bank import load_prompt_bank

logger = logging.getLogger(__name__)

DEFAULT_STATE_REL = "data/seed_gen/state.json"


@dataclass
class DomainState:
    generated: int = 0
    accepted: int = 0
    rejected_exact: int = 0
    rejected_similar: int = 0


@dataclass
class SeedGenState:
    updated_at: str = ""
    domains: dict[str, DomainState] = field(default_factory=dict)
    checkpoint: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "updated_at": self.updated_at,
            "domains": {k: asdict(v) for k, v in self.domains.items()},
            "checkpoint": dict(self.checkpoint),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SeedGenState:
        dom_raw = data.get("domains") or {}
        domains: dict[str, DomainState] = {}
        if isinstance(dom_raw, dict):
            for key, val in dom_raw.items():
                if isinstance(val, dict):
                    domains[str(key)] = DomainState(
                        generated=int(val.get("generated", 0)),
                        accepted=int(val.get("accepted", 0)),
                        rejected_exact=int(val.get("rejected_exact", 0)),
                        rejected_similar=int(val.get("rejected_similar", 0)),
                    )
        return SeedGenState(
            updated_at=str(data.get("updated_at") or ""),
            domains=domains,
            checkpoint=dict(data.get("checkpoint") or {}),
        )


def load_state(path: Path) -> SeedGenState:
    if not path.is_file():
        return SeedGenState()
    return SeedGenState.from_dict(json.loads(path.read_text(encoding="utf-8")))


def save_state(path: Path, state: SeedGenState) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    state.updated_at = datetime.now(UTC).isoformat()
    tmp = path.with_suffix(".tmp")
    tmp.write_text(
        json.dumps(state.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    os.replace(tmp, path)


def atomic_append_jsonl(bank_path: Path, new_rows: list[dict[str, Any]]) -> None:
    """既存 JSONL を保持したまま新規行のみ atomic 追記。"""
    if not new_rows:
        return
    bank_path.parent.mkdir(parents=True, exist_ok=True)
    existing_lines: list[str] = []
    if bank_path.is_file():
        existing_lines = bank_path.read_text(encoding="utf-8").splitlines()
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{bank_path.name}.",
        suffix=".tmp",
        dir=str(bank_path.parent),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            for line in existing_lines:
                if line.strip():
                    fh.write(line + "\n")
            for row in new_rows:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_name, bank_path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def read_bank_bytes(path: Path) -> bytes:
    if not path.is_file():
        return b""
    return path.read_bytes()


def make_seed_row(
    prompt: str, domain: str, sampling: dict[str, Any] | None = None
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "id": str(uuid.uuid4()),
        "prompt": prompt,
        "domain": domain,
    }
    if sampling:
        row["sampling"] = sampling
    return row


def count_bank_rows(path: Path) -> int:
    if not path.is_file():
        return 0
    return sum(1 for _ in iter_jsonl(path, logger=logger, log_prefix="seed_gen bank"))


def load_bank_prompts(path: Path) -> list[str]:
    if not path.is_file():
        return []
    return [r.prompt for r in load_prompt_bank(path)]


__all__ = [
    "DEFAULT_STATE_REL",
    "atomic_append_jsonl",
    "count_bank_rows",
    "DomainState",
    "load_bank_prompts",
    "load_state",
    "make_seed_row",
    "read_bank_bytes",
    "save_state",
    "SeedGenState",
]
