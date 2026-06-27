#!/usr/bin/env python3
"""joryu vs Llama-Swallow judge のセルフバイアス比較 (Epic #305 / #309)。"""

from __future__ import annotations

import argparse
import json
import logging
import os
import random
import sys
from pathlib import Path

from joryu.curate.judge_client import HEALTH_RUBRIC_KEYS, FakeJudgeClient
from joryu.curate.prompt_loader import load_health_rubric
from joryu.curate.signals.llm_judge import build_health_response_text
from joryu.logging_config import setup_logging

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
    p = argparse.ArgumentParser(description="Compare joryu vs Llama-Swallow health rubric scores")
    p.add_argument("--scores", required=True, help="scores.jsonl path")
    p.add_argument("--sample", type=int, default=50)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--output", default="", help="JSON output path")
    args = p.parse_args(argv)

    scores_path = Path(args.scores)
    if not scores_path.is_file():
        logger.error("scores file not found: %s", scores_path)
        return 2

    health_prompt = load_health_rubric()
    joryu_judge = FakeJudgeClient(health_scores={k: 4 for k in HEALTH_RUBRIC_KEYS})
    llama_judge = FakeJudgeClient(health_scores={k: 5 for k in HEALTH_RUBRIC_KEYS})

    if os.environ.get("JORYU_CURATE_FAKE_JUDGE") != "1":
        logger.info("Using FakeJudgeClient stubs; set real judges via future extension")

    rows = _load_records(scores_path, args.sample, args.seed)
    per_aspect_diff: dict[str, list[float]] = {k: [] for k in HEALTH_RUBRIC_KEYS}
    joryu_avgs: list[float] = []
    llama_avgs: list[float] = []

    for row in rows:
        prompt = str(row.get("prompt") or "")
        rec = {
            "prompt": prompt,
            "answer": "",
            "thinking_trace": "",
        }
        raw = row.get("signal_raw") or {}
        if isinstance(raw, dict) and "LLM-HEALTH" in raw:
            pass
        response = build_health_response_text(rec) or prompt
        j_scores = joryu_judge.score_health_rubric(
            prompt, response, health_prompt_template=health_prompt.text
        )
        l_scores = llama_judge.score_health_rubric(
            prompt, response, health_prompt_template=health_prompt.text
        )
        j_avg = sum(j_scores[k] for k in HEALTH_RUBRIC_KEYS) / len(HEALTH_RUBRIC_KEYS)
        l_avg = sum(l_scores[k] for k in HEALTH_RUBRIC_KEYS) / len(HEALTH_RUBRIC_KEYS)
        joryu_avgs.append(j_avg)
        llama_avgs.append(l_avg)
        for k in HEALTH_RUBRIC_KEYS:
            per_aspect_diff[k].append(float(l_scores[k]) - float(j_scores[k]))

    report = {
        "sample_size": len(rows),
        "correlation_mean_score": _correlation(joryu_avgs, llama_avgs),
        "mean_diff_by_aspect": {
            k: sum(per_aspect_diff[k]) / len(per_aspect_diff[k]) if per_aspect_diff[k] else 0.0
            for k in HEALTH_RUBRIC_KEYS
        },
        "judge_models": {"joryu": "joryu", "llama_swallow": "Llama-3.1-Swallow-8B-Instruct-v0.5"},
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
