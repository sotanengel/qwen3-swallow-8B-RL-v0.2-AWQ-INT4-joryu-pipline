"""`joryu-curate` CLI (R-15)。

蒸留 JSONL から高品質サブセットを抽出する。--skip-llm で統計シグナルのみで判定。
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from joryu.config import Config, load_config
from joryu.curate.judge_client import (
    DEFAULT_RUBRIC_PROMPT,
    FakeJudgeClient,
    JudgeClient,
    VllmJudgeClient,
)
from joryu.curate.loader import iter_records
from joryu.curate.meta import write_curation_meta
from joryu.curate.record_hash import compute_record_hash
from joryu.curate.scoring import build_composite, select_by_threshold
from joryu.curate.signals.llm_judge import LLMRubricSignal
from joryu.curate.signals.stat import build_default_stat_signals
from joryu.curate.stats import DEFAULT_CURATION_OUTPUT, write_curation_json
from joryu.curate.writer import CurateWriter
from joryu.stats import resolve_repo_root


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="joryu-curate",
        description="蒸留 JSONL から高品質サブセットを抽出する。",
    )
    p.add_argument("--config", default="config.yaml")
    p.add_argument(
        "--src",
        default="",
        help="入力 JSONL (.jsonl / .jsonl.zst)。未指定なら config から導出。",
    )
    p.add_argument(
        "--dst",
        default="",
        help="出力ディレクトリ。未指定なら data/curated/<YYYYMMDD_HHMMSS>/。",
    )
    p.add_argument("--threshold", type=float, default=None)
    p.add_argument("--top-k", type=int, default=None)
    p.add_argument(
        "--keep-rate",
        type=float,
        default=None,
        help="採用率 (0-1)。指定時は threshold/top-k を無視。",
    )
    p.add_argument("--judge-model", default=None)
    p.add_argument("--judge-mode", default=None, choices=["thinking", "nothinking"])
    p.add_argument("--skip-llm", action="store_true", help="LLM judge をスキップ (高速モード)。")
    p.add_argument(
        "--count",
        type=int,
        default=0,
        help="評価上限 (0 = 全件)。",
    )
    return p


def _resolve_paths(cfg: Config, args: argparse.Namespace) -> tuple[Path, Path]:
    src = Path(args.src) if args.src else Path(cfg.distill.out_dir) / cfg.distill.out_file
    if args.dst:
        dst = Path(args.dst)
    else:
        ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        dst = Path(cfg.curate.out_dir) / ts
    return src, dst


def _git_sha() -> str | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
        return out.stdout.strip() or None
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None


def _build_judge(cfg: Config, args: argparse.Namespace) -> JudgeClient | None:
    """skip_llm=True もしくは vLLM 未インストールなら None。

    プロセス内環境変数 `JORYU_CURATE_FAKE_JUDGE=1` で常に Fake を使用 (CI 用)。
    """
    if args.skip_llm or cfg.curate.skip_llm:
        return None
    if os.environ.get("JORYU_CURATE_FAKE_JUDGE") == "1":
        return FakeJudgeClient()
    try:
        from joryu.vllm_client import VllmClient
    except Exception:  # pragma: no cover - lazy import only
        return None
    chat = VllmClient.from_config(cfg.model, cfg.vllm)
    return VllmJudgeClient(
        chat,
        rubric_prompt=DEFAULT_RUBRIC_PROMPT,
        judge_mode=args.judge_mode or cfg.curate.judge_mode,
    )


def main(
    argv: list[str] | None = None,
    *,
    _judge: JudgeClient | None = None,
    _print: Any = None,
) -> int:
    log = _print if _print is not None else print
    args = build_parser().parse_args(argv)
    cfg_path = Path(args.config)
    cfg = load_config(cfg_path) if cfg_path.exists() else Config()

    # CLI 引数で curate config を上書き
    if args.threshold is not None:
        cfg.curate.threshold = args.threshold
    if args.top_k is not None:
        cfg.curate.top_k = args.top_k
    if args.keep_rate is not None:
        cfg.curate.keep_rate = args.keep_rate
    if args.judge_model is not None:
        cfg.curate.judge_model = args.judge_model
    if args.judge_mode is not None:
        cfg.curate.judge_mode = args.judge_mode
    if args.skip_llm:
        cfg.curate.skip_llm = True

    src, dst = _resolve_paths(cfg, args)
    if not src.exists():
        log(f"[joryu-curate] 入力が見つかりません: {src}", file=sys.stderr)
        return 2

    judge: JudgeClient | None = _judge if _judge is not None else _build_judge(cfg, args)
    stat_signals = build_default_stat_signals(cfg.curate.thresholds)
    llm_signal = LLMRubricSignal(judge=judge) if judge is not None else None

    composites = []
    records: list[dict[str, Any]] = []
    record_hashes: list[str] = []
    llm_calls = 0
    input_records = 0
    schema_skipped = 0
    log(f"[joryu-curate] 入力: {src}", file=sys.stderr)
    log(f"[joryu-curate] 出力: {dst}", file=sys.stderr)

    for i, rec in enumerate(iter_records(src), 1):
        if args.count and i > args.count:
            break
        input_records += 1
        schema_ok = rec.pop("_schema_ok", True)
        if not schema_ok:
            schema_skipped += 1
            records.append(rec)
            record_hashes.append(compute_record_hash(rec))
            composites.append(_schema_rejected_composite(stat_signals))
            continue
        stat_results = [s.evaluate(rec) for s in stat_signals]
        hard = any(r.hard_reject for r in stat_results)
        llm_results = []
        if llm_signal is not None and not hard:
            llm_results = [llm_signal.evaluate(rec)]
            llm_calls += 1
        composites.append(
            build_composite(
                stat_results=stat_results,
                llm_results=llm_results,
                w_stat=cfg.curate.weights_stat,
                w_llm=cfg.curate.weights_llm,
            )
        )
        records.append(rec)
        record_hashes.append(compute_record_hash(rec))

    selections = select_by_threshold(
        composites,
        threshold=cfg.curate.threshold,
        top_k=cfg.curate.top_k,
        keep_rate=cfg.curate.keep_rate,
    )

    with CurateWriter(dst) as writer:
        for rec, comp, sel, rh in zip(records, composites, selections, record_hashes, strict=True):
            writer.write(
                rec,
                accepted=sel.accepted,
                final_score=sel.final_score,
                rejected_by=sel.rejected_by,
                signal_versions=comp.signal_versions,
                signal_scores=comp.signal_scores,
                signal_raw=comp.signal_raw,
                record_hash=rh,
            )

    signal_versions = _collect_signal_versions(stat_signals, llm_signal)
    write_curation_meta(
        dst,
        src_path=src,
        input_records=input_records,
        kept=writer.kept,
        rejected=writer.rejected,
        curate_fingerprints=cfg.curate_fingerprints(),
        judge_model=cfg.curate.judge_model,
        judge_mode=cfg.curate.judge_mode,
        signal_versions=signal_versions,
        cli_args=vars(args),
        git_sha=_git_sha(),
        llm_calls_total=llm_calls,
    )

    # dashboard/public/curation.json
    repo_root = resolve_repo_root(out_path=Path(cfg.distill.out_dir) / cfg.distill.out_file)
    dashboard_dst: Path | None = (
        repo_root / DEFAULT_CURATION_OUTPUT if repo_root is not None else None
    )
    if dashboard_dst is not None:
        write_curation_json(dst / "scores.jsonl", dashboard_dst)
    else:
        # フォールバック: dst 内に curation.json も置く
        write_curation_json(dst / "scores.jsonl", dst / "curation.json")

    keep_rate = (writer.kept / input_records) if input_records else 0.0
    log(
        f"[joryu-curate] 入力 {input_records} 件 → 採用 {writer.kept} ({keep_rate:.1%}) / "
        f"棄却 {writer.rejected} / schema NG {schema_skipped} / LLM 呼び出し {llm_calls} 回",
        file=sys.stderr,
    )
    log(f"[joryu-curate] meta: {dst / 'curation_meta.json'}", file=sys.stderr)
    return 0


def _schema_rejected_composite(stat_signals: list) -> Any:
    """schema 欠損レコード用のダミー composite (常にハード棄却 = 'schema')。"""
    from joryu.curate.scoring import CompositeScore

    versions = {s.code: s.version for s in stat_signals}
    return CompositeScore(
        stat_score=0.0,
        llm_score=None,
        final_score=0.0,
        hard_rejected_by=["schema"],
        signal_versions=versions,
        signal_scores={},
        signal_raw={},
    )


def _collect_signal_versions(
    stat_signals: list,
    llm_signal: LLMRubricSignal | None,
) -> dict[str, str]:
    versions = {s.code: s.version for s in stat_signals}
    if llm_signal is not None:
        versions[llm_signal.code] = llm_signal.version
    return versions


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
