#!/usr/bin/env python3
"""vLLM の VRAM 上限をプローブし、data/vllm_limits.json に書き出す。

OOM 時は候補を降順で試行し、成功した最大 (num_ctx, num_predict) を採用する。
"""

from __future__ import annotations

import argparse

from joryu.paths import DEFAULT_CONFIG
from joryu.vllm_probe import run_probe


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Probe vLLM VRAM limits for joryu.")
    parser.add_argument("--config", default=DEFAULT_CONFIG, help="config YAML path")
    parser.add_argument(
        "--out",
        default="",
        help="output JSON path (default: config.model.limits_probe_file)",
    )
    args = parser.parse_args(argv)
    return run_probe(config=args.config, out=args.out or None)


if __name__ == "__main__":
    raise SystemExit(main())
