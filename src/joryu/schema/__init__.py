"""YAML スキーマ version 付与 (#260)。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class SchemaVersion(BaseModel):
    """全 YAML 共通の version フィールド。"""

    version: int = Field(default=1, ge=1)


def validate_mapping_schema(raw: dict[str, Any], *, label: str) -> SchemaVersion:
    """mapping に version があることを検証する。"""
    try:
        return SchemaVersion.model_validate(raw)
    except Exception as exc:
        msg = f"{label}: invalid schema version: {exc}"
        raise ValueError(msg) from exc


__all__ = ["SchemaVersion", "validate_mapping_schema"]
