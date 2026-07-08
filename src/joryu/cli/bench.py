"""joryu-bench: throughput / quality ベンチハーネス。"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from joryu.bench.compare import QualityCompareThresholds
from joryu.bench.quality import run_quality_bench
from joryu.bench.report import build_bench_report, write_report_json
from joryu.bench.throughput import run_throughput_bench
from joryu.cli.common import add_config_argument
from joryu.core.config import load_config
from joryu.vllm.protocol import SupportsChat

logger = logging.getLogger(__name__)


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="joryu-bench",
        description="Throughput / Quality bench harness",
    )
    add_config_argument(p)
    sub = p.add_subparsers(dest="cmd", required=True)

    t = sub.add_parser("throughput", help="Throughput metrics を出す")
    t.add_argument(
        "--bank",
        default="",
        help="prompt bank JSONL (既定: config.distill.prompt_bank)",
    )
    t.add_argument("--out", default="", help="出力 JSON（既定: data/bench/throughput.json）")
    t.add_argument("--count", type=int, default=0, help="新規生成件数 (0 = 全件)")
    t.add_argument("--fake", action="store_true", help="FakeVllmClient を使う（GPU 不要）")
    t.add_argument("--fake-answer", default="今日は晴れです。", help="Fake answer")

    q = sub.add_parser("quality", help="品質シグナル集計")
    q.add_argument(
        "--bank",
        default="",
        help="prompt bank JSONL (既定: config.distill.prompt_bank)",
    )
    q.add_argument("--out", default="", help="出力 JSON（既定: data/bench/quality.json）")
    q.add_argument("--count", type=int, default=0, help="新規生成件数 (0 = 全件)")
    q.add_argument("--fake", action="store_true", help="FakeVllmClient を使う（GPU 不要）")
    q.add_argument("--fake-answer", default="今日は晴れです。", help="Fake answer")
    q.add_argument("--baseline", default="", help="ベースライン JSON を比較する")

    return p


def _resolve_bank_path(cfg, bank_arg: str) -> Path:
    if bank_arg:
        p = Path(bank_arg)
        return p if p.is_absolute() else p.resolve()
    return Path(cfg.distill.prompt_bank)


def _resolve_out_path(default_name: str, out_arg: str) -> Path:
    if out_arg:
        p = Path(out_arg)
        return p if p.is_absolute() else p.resolve()
    return Path("data/bench") / default_name


def _make_fake_client(answer: str) -> SupportsChat:
    # tests の Fake を流用する（CLI は開発補助のため許容）。
    try:
        from tests.conftest import FakeVllmClient

        return FakeVllmClient(answer=answer)
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(
            "FakeVllmClient is unavailable; run from repo root with tests/ available"
        ) from exc


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    cfg = load_config(args.config)

    bank_path = _resolve_bank_path(cfg, args.bank)
    out_json = _resolve_out_path(
        "throughput.json" if args.cmd == "throughput" else "quality.json", args.out
    )
    tmp_jsonl = out_json.with_suffix(".jsonl")

    client: SupportsChat | None = None
    if getattr(args, "fake", False):
        client = _make_fake_client(args.fake_answer)

    if args.cmd == "throughput":
        metrics = run_throughput_bench(
            cfg=cfg,
            bank_path=bank_path,
            out_path=tmp_jsonl,
            client=client,
            count=args.count,
        )
    else:
        metrics = run_quality_bench(
            cfg=cfg,
            bank_path=bank_path,
            out_path=tmp_jsonl,
            client=client,
            count=args.count,
        )

    report = build_bench_report(cfg=cfg, metrics=metrics, kind=args.cmd)
    write_report_json(out_json, report)
    logger.info("[bench] wrote %s", out_json)

    # （オプション）baseline 比較
    baseline_path = getattr(args, "baseline", "") or ""
    if baseline_path:
        import json

        baseline = json.loads(Path(baseline_path).read_text(encoding="utf-8"))
        if args.cmd == "quality":
            from joryu.bench.compare import compare_quality_metrics

            compare_quality_metrics(
                metrics=metrics,
                baseline=baseline,
                thresholds=QualityCompareThresholds(),
            )

    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
