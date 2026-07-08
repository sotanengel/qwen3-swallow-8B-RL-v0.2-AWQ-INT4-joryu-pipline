"""Bench 結果 JSON の整形。"""

from __future__ import annotations

import json
import logging
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from joryu.core.config import Config

logger = logging.getLogger(__name__)


def _get_git_sha() -> str:
    try:
        out = subprocess.check_output(["git", "show", "-s", "--format=%H", "HEAD"])
        return out.decode("utf-8").strip()
    except Exception:  # noqa: BLE001
        return "unknown"


def _get_gpu_name() -> str:
    # CI / Fake backend では GPU がないことが多いので best-effort に留める。
    try:
        import torch  # type: ignore

        if torch.cuda.is_available():
            name = torch.cuda.get_device_name(0)
            return name or "unknown"
    except Exception:
        pass

    try:
        out = subprocess.check_output(["nvidia-smi", "-L"], stderr=subprocess.STDOUT, timeout=2)
        text = out.decode("utf-8", errors="ignore").strip().splitlines()
        if text:
            return text[0][:200]
    except Exception:
        pass

    return "unknown"


def build_bench_report(*, cfg: Config, metrics: dict[str, Any], kind: str) -> dict[str, Any]:
    now = datetime.now(UTC).isoformat()
    return {
        "kind": kind,
        "timestamp": now,
        "config_fingerprint": cfg.fingerprint(),
        "git_sha": _get_git_sha(),
        "gpu_name": _get_gpu_name(),
        "metrics": metrics,
    }


def write_report_json(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


__all__ = ["build_bench_report", "write_report_json"]
