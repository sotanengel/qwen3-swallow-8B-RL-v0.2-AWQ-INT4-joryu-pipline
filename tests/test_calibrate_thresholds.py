"""calibrate_thresholds スクリプトの smoke テスト。"""

from __future__ import annotations

import importlib.util
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "calibrate_thresholds",
    _ROOT / "scripts" / "calibrate_thresholds.py",
)
_mod = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(_mod)
calibrate = _mod.calibrate


def test_calibrate_thresholds_smoke(tmp_path: Path):
    pairs = [(0.9 if i % 2 == 0 else 0.3, i % 2 == 0) for i in range(50)]
    report = calibrate(pairs)
    assert report["paired_count"] == 50
    assert 0.0 <= report["recommended_ok_min"] <= 1.0
