"""joryu-seed-gen CLI (#321)。"""

from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path

from joryu.jobs.models import SEED_GEN_MODE_CREATE, SEED_GEN_MODES
from joryu.logging_config import setup_logging
from joryu.seed_gen.config import (
    DEFAULT_DOMAINS_REL,
    DEFAULT_TARGET_TOTAL,
    SeedGenConfig,
    resolve_domains_config_path,
)
from joryu.seed_gen.generator import DEFAULT_MODEL
from joryu.seed_gen.pipeline import DEFAULT_BANK_REL, PipelineOptions, run_pipeline
from joryu.seed_gen.writer import DEFAULT_STATE_REL

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="joryu-seed-gen",
        description="プロンプトバンクの生成/チェックを行う (Epic #313)。",
    )
    p.add_argument(
        "--mode",
        choices=list(SEED_GEN_MODES),
        default=SEED_GEN_MODE_CREATE,
        help="create: LLM 生成 + Stage1 dedup / check: Stage2 類似 dedup",
    )
    p.add_argument("--bank", default=DEFAULT_BANK_REL, help="対象 JSONL")
    p.add_argument("--domains-config", default=DEFAULT_DOMAINS_REL, help="分野定義 YAML")
    p.add_argument("--model", default=DEFAULT_MODEL, help="生成 LLM モデル名")
    p.add_argument("--embed-model", default="cl-nagoya/ruri-large", help="埋め込みモデル")
    p.add_argument("--sim-threshold", type=float, default=0.85, help="類似棄却閾値")
    p.add_argument(
        "--target-total", type=int, default=DEFAULT_TARGET_TOTAL, help="全体ターゲット件数"
    )
    p.add_argument("--domain", default="", help="特定分野のみ実行")
    p.add_argument("--batch-size", type=int, default=8, help="LLM 生成バッチサイズ")
    p.add_argument("--resume", action="store_true", help="state.json から再開")
    p.add_argument(
        "--llm-base-url", default="", help="OpenAI 互換 API URL (例 http://127.0.0.1:8100/v1)"
    )
    p.add_argument(
        "--judge-base-url", default="", help="judge (screening) LLM URL (check モードで使用)"
    )
    p.add_argument("--state", default=DEFAULT_STATE_REL, help="state.json パス")
    return p


def main(argv: list[str] | None = None) -> int:
    setup_logging()
    args = build_parser().parse_args(argv)
    repo_root = Path.cwd().resolve()

    domains_path = resolve_domains_config_path(repo_root, args.domains_config)
    cfg = SeedGenConfig.load(domains_path)
    if args.domain:
        cfg = cfg.filter_domain(args.domain.strip())

    bank_path = (
        (repo_root / args.bank).resolve() if not Path(args.bank).is_absolute() else Path(args.bank)
    )
    state_path = (
        (repo_root / args.state).resolve()
        if not Path(args.state).is_absolute()
        else Path(args.state)
    )

    llm_url = args.llm_base_url or os.environ.get("JORYU_VLLM_URL", "").strip()
    if llm_url and not llm_url.endswith("/v1"):
        llm_url = llm_url.rstrip("/") + "/v1"

    opts = PipelineOptions(
        bank_path=bank_path,
        state_path=state_path,
        config=cfg,
        mode=str(args.mode),
        sim_threshold=float(args.sim_threshold),
        batch_size=int(args.batch_size),
        resume=bool(args.resume),
        embed_model=str(args.embed_model),
        llm_base_url=llm_url,
        llm_model=str(args.model),
        target_total_override=int(args.target_total),
        log=logger.info,
    )
    try:
        return run_pipeline(opts)
    except Exception:
        logger.exception("seed_gen failed")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
