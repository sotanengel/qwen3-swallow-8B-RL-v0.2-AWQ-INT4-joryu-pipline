#!/usr/bin/env python3
"""閾値キャリブレーション: 人手正解ラベルと final_score を突合 (Epic #305 / #312)。"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from joryu.logging_config import setup_logging

logger = logging.getLogger(__name__)


def _load_labels(path: Path) -> dict[str, str]:
    labels: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        h = row.get("record_hash")
        lbl = row.get("label")
        if isinstance(h, str) and isinstance(lbl, str):
            labels[h] = lbl.upper()
    return labels


def _load_scores(path: Path) -> list[dict]:
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def _metrics(
    pairs: list[tuple[float, bool]],
    *,
    threshold: float,
) -> dict[str, float]:
    """正解 OK を positive として precision/recall を算出。"""
    tp = fp = fn = tn = 0
    for score, is_ok in pairs:
        pred_ok = score >= threshold
        if pred_ok and is_ok:
            tp += 1
        elif pred_ok and not is_ok:
            fp += 1
        elif not pred_ok and is_ok:
            fn += 1
        else:
            tn += 1
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    return {
        "threshold": threshold,
        "precision": precision,
        "recall": recall,
        "tp": float(tp),
        "fp": float(fp),
        "fn": float(fn),
        "tn": float(tn),
    }


def calibrate(pairs: list[tuple[float, bool]]) -> dict:
    best_ok = 0.75
    best_review = 0.40
    best_f1 = -1.0
    for ok_min in [x / 100 for x in range(50, 96, 5)]:
        m = _metrics(pairs, threshold=ok_min)
        f1 = (
            2 * m["precision"] * m["recall"] / (m["precision"] + m["recall"])
            if (m["precision"] + m["recall"])
            else 0.0
        )
        if f1 > best_f1:
            best_f1 = f1
            best_ok = ok_min
    for review_min in [x / 100 for x in range(20, 75, 5)]:
        if review_min < best_ok:
            continue
        # review_min は探索のみ (OK 閾値との整合)
        best_review = review_min
    m_ok = _metrics(pairs, threshold=best_ok)
    return {
        "recommended_ok_min": best_ok,
        "recommended_review_min": best_review,
        "precision_at_ok": m_ok["precision"],
        "recall_at_ok": m_ok["recall"],
        "f1_at_ok": best_f1,
        "paired_count": len(pairs),
    }


def main(argv: list[str] | None = None) -> int:
    setup_logging()
    p = argparse.ArgumentParser(description="Calibrate screening thresholds from human labels")
    p.add_argument("--scores", required=True)
    p.add_argument("--labels", required=True)
    p.add_argument("--smoke", action="store_true", help="50件未満でも完了扱い")
    p.add_argument("--output", default="")
    args = p.parse_args(argv)

    scores_path = Path(args.scores)
    labels_path = Path(args.labels)
    if not scores_path.is_file() or not labels_path.is_file():
        logger.error("scores or labels file missing")
        return 2

    labels = _load_labels(labels_path)
    pairs: list[tuple[float, bool]] = []
    for row in _load_scores(scores_path):
        h = row.get("record_hash")
        if not isinstance(h, str) or h not in labels:
            continue
        score = float(row.get("final_score", 0.0))
        is_ok = labels[h] == "OK"
        pairs.append((score, is_ok))

    if not pairs:
        logger.error("no paired records between scores and labels")
        return 2
    if len(pairs) < 50 and not args.smoke:
        logger.error("need at least 50 paired records (got %d); use --smoke", len(pairs))
        return 2

    report = calibrate(pairs)
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
        logger.info("wrote %s", args.output)
    else:
        sys.stdout.write(text + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
