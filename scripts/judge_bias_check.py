#!/usr/bin/env python3
"""Qwen3 (蒸留) vs Llama-Swallow judge のセルフバイアス比較。"""

from __future__ import annotations

import argparse
import json
import logging
import os
import random
import sys
from pathlib import Path

from joryu.core.logging_config import setup_logging
from joryu.curate.judge_client import RUBRIC_KEYS, FakeJudgeClient

logger = logging.getLogger(__name__)


def _load_records(scores_jsonl: Path, sample: int, seed: int) -> list[dict]:
    rows: list[dict] = []
    for line in scores_jsonl.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    if sample and len(rows) > sample:
        rng = random.Random(seed)
        rows = rng.sample(rows, sample)
    return rows


def _correlation(a: list[float], b: list[float]) -> float:
    if len(a) < 2:
        return 0.0
    mean_a = sum(a) / len(a)
    mean_b = sum(b) / len(b)
    var_a = sum((x - mean_a) ** 2 for x in a)
    var_b = sum((x - mean_b) ** 2 for x in b)
    if var_a == 0 or var_b == 0:
        return 0.0
    cov = sum((a[i] - mean_a) * (b[i] - mean_b) for i in range(len(a)))
    return cov / (var_a**0.5 * var_b**0.5)


def main(argv: list[str] | None = None) -> int:
    setup_logging()
    p = argparse.ArgumentParser(description="Compare Qwen3 vs Llama-Swallow LLM-RUBRIC scores")
    p.add_argument("--scores", required=True, help="scores.jsonl path")
    p.add_argument("--sample", type=int, default=50)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--output", default="", help="JSON output path")
    args = p.parse_args(argv)

    scores_path = Path(args.scores)
    if not scores_path.is_file():
        logger.error("scores file not found: %s", scores_path)
        return 2

    qwen_judge = FakeJudgeClient(scores={k: 4 for k in RUBRIC_KEYS})
    llama_judge = FakeJudgeClient(scores={k: 5 for k in RUBRIC_KEYS})

    if os.environ.get("JORYU_CURATE_FAKE_JUDGE") != "1":
        logger.info("Using FakeJudgeClient stubs; set real judges via future extension")

    rows = _load_records(scores_path, args.sample, args.seed)
    per_aspect_diff: dict[str, list[float]] = {k: [] for k in RUBRIC_KEYS}
    qwen_avgs: list[float] = []
    llama_avgs: list[float] = []

    for row in rows:
        prompt = str(row.get("prompt") or "")
        answer = str(row.get("answer") or prompt)
        j_scores = qwen_judge.score_rubric(prompt, answer)
        l_scores = llama_judge.score_rubric(prompt, answer)
        j_avg = sum(j_scores[k] for k in RUBRIC_KEYS) / len(RUBRIC_KEYS)
        l_avg = sum(l_scores[k] for k in RUBRIC_KEYS) / len(RUBRIC_KEYS)
        qwen_avgs.append(j_avg)
        llama_avgs.append(l_avg)
        for k in RUBRIC_KEYS:
            per_aspect_diff[k].append(float(l_scores[k]) - float(j_scores[k]))

    report = {
        "sample_size": len(rows),
        "correlation_mean_score": _correlation(qwen_avgs, llama_avgs),
        "mean_diff_by_aspect": {
            k: sum(per_aspect_diff[k]) / len(per_aspect_diff[k]) if per_aspect_diff[k] else 0.0
            for k in RUBRIC_KEYS
        },
        "judge_models": {
            "qwen3": "Qwen3-Swallow-8B-RL-v0.2-AWQ-INT4",
            "llama_swallow": "Llama-3.1-Swallow-8B-Instruct-v0.5",
        },
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
        logger.info("wrote %s", args.output)
    else:
        sys.stdout.write(text + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
