"""プロンプトチェック済み状態 (checked_keys) の管理。"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from joryu.core.prompt_bank import PromptRow


@dataclass
class PromptCheckState:
    checked_keys: set[str] = field(default_factory=set)
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "checked_keys": sorted(self.checked_keys),
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> PromptCheckState:
        if not data:
            return cls()
        raw = data.get("checked_keys") or []
        keys: set[str] = set()
        if isinstance(raw, list):
            keys = {str(k) for k in raw if k}
        return cls(
            checked_keys=keys,
            updated_at=str(data.get("updated_at") or ""),
        )


@dataclass(frozen=True)
class PromptCheckStatus:
    bank_total: int
    checked_count: int
    unchecked_count: int
    check_completed: bool


def prompt_check_key(row: PromptRow) -> str:
    """PromptRow の安定キー。id 優先、なければ prompt 内容 hash。"""
    if row.id:
        return f"id:{row.id}"
    digest = hashlib.sha256(row.prompt.encode("utf-8")).hexdigest()
    return f"hash:{digest}"


def partition_by_checked(
    rows: list[PromptRow],
    checked_keys: set[str],
) -> tuple[list[PromptRow], list[PromptRow]]:
    checked: list[PromptRow] = []
    unchecked: list[PromptRow] = []
    for row in rows:
        if prompt_check_key(row) in checked_keys:
            checked.append(row)
        else:
            unchecked.append(row)
    return checked, unchecked


def mark_checked(state: Any, keys: set[str] | list[str]) -> None:
    """SeedGenState.prompt_check にキーを追加する。"""
    if not keys:
        return
    pc = state.prompt_check
    pc.checked_keys.update(keys)
    pc.updated_at = datetime.now(UTC).isoformat()


def mark_all_unchecked(
    rows: list[PromptRow],
    state: Any,
    *,
    domain: str = "",
) -> int:
    """未チェック行を一括登録。domain 指定時はその分野のみ。追加件数を返す。"""
    dom = domain.strip()
    keys: list[str] = []
    for row in rows:
        if dom and (row.domain or "") != dom:
            continue
        key = prompt_check_key(row)
        if key not in state.prompt_check.checked_keys:
            keys.append(key)
    mark_checked(state, keys)
    return len(keys)


def compute_check_status(
    rows: list[PromptRow],
    checked_keys: set[str],
) -> PromptCheckStatus:
    total = len(rows)
    checked_count = sum(1 for row in rows if prompt_check_key(row) in checked_keys)
    unchecked = total - checked_count
    return PromptCheckStatus(
        bank_total=total,
        checked_count=checked_count,
        unchecked_count=unchecked,
        check_completed=total == 0 or unchecked == 0,
    )


__all__ = [
    "PromptCheckState",
    "PromptCheckStatus",
    "compute_check_status",
    "mark_all_unchecked",
    "mark_checked",
    "partition_by_checked",
    "prompt_check_key",
]
