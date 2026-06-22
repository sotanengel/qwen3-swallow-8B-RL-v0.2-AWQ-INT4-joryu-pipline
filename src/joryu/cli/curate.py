"""`joryu-curate` CLI (R-15)。

蒸留 JSONL から高品質サブセットを抽出する。--skip-llm で統計シグナルのみで判定。
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from joryu.cli.common import add_config_argument, resolve_cli_config
from joryu.config import Config
from joryu.curate.artifacts import find_latest_run_artifact
from joryu.curate.best_of_n import apply_best_of_n, parse_strategy
from joryu.curate.cache import (
    CacheCounters,
    CacheIndex,
    auto_detect_cache_paths,
    load_cache_index,
    signal_result_from_cache,
)
from joryu.curate.judge_client import (
    DEFAULT_RUBRIC_PROMPT,
    FakeJudgeClient,
    JudgeClient,
    VllmJudgeClient,
)
from joryu.curate.loader import iter_records
from joryu.curate.meta import format_incremental_summary, write_curation_meta
from joryu.curate.minhash_index import (
    DEFAULT_INDEX_FILENAME,
    GlobalDuplicateIndex,
)
from joryu.curate.progress import clear_existing_outputs, load_resume_state
from joryu.curate.record_hash import compute_record_hash
from joryu.curate.scoring import build_composite, select_by_threshold
from joryu.curate.signals.llm_judge import LLMRubricSignal
from joryu.curate.signals.stat import (
    SAMP_OUT_CODE,
    SAMP_OUT_VERSION,
    DupGlobal,
    apply_samp_out_filter,
    build_default_stat_signals,
)
from joryu.curate.stats import DEFAULT_CURATION_OUTPUT, write_curation_json
from joryu.curate.style_presets import load_style_rules
from joryu.curate.writer import CurateWriter
from joryu.paths import resolve_distill_output, resolve_repo_root
from joryu.preflight import git_head_at


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="joryu-curate",
        description="蒸留 JSONL から高品質サブセットを抽出する。",
    )
    add_config_argument(p)
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
        "--best-of-n",
        default="off",
        help="best-of-N 選択戦略: off / auto / rubric_max / pair_tournament / n=<int> (R-12)",
    )
    resume = p.add_mutually_exclusive_group()
    resume.add_argument(
        "--resume",
        dest="resume",
        action="store_true",
        default=True,
        help="同一ラン内で中断された場合に途中の scores.jsonl から再開 (既定)",
    )
    resume.add_argument(
        "--no-resume",
        dest="resume",
        action="store_false",
        help="既存出力を削除してゼロから再評価",
    )
    p.add_argument(
        "--count",
        type=int,
        default=0,
        help="評価上限 (0 = 全件)。",
    )
    p.add_argument(
        "--cache-from",
        action="append",
        default=None,
        help="過去ランの scores.jsonl (ファイルまたは run ディレクトリ) を再利用。"
        " 複数回指定可。未指定なら --dst の親ディレクトリで最新ランを自動検出。",
    )
    p.add_argument(
        "--no-cache",
        action="store_true",
        help="過去ランを無視して全件再評価 (R-20)。",
    )
    p.add_argument(
        "--rescore-only",
        action="store_true",
        help="LLM 呼び出しはせず、合成スコアと採否判定だけやり直す (閾値チューニング用, R-23)。",
    )
    return p


def _resolve_paths(cfg: Config, args: argparse.Namespace) -> tuple[Path, Path]:
    src = resolve_distill_output(cfg, args.src or None)
    if args.dst:
        dst = Path(args.dst)
    else:
        ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        dst = Path(cfg.curate.out_dir) / ts
    return src, dst


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
    cfg = resolve_cli_config(args)

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

    # --resume / --no-resume: 既存 scores.jsonl からの再開判定
    scores_path = dst / "scores.jsonl"
    if not args.resume:
        if dst.exists():
            clear_existing_outputs(dst)
            log("[joryu-curate] --no-resume: 既存出力を削除", file=sys.stderr)
    resume_state = load_resume_state(scores_path) if args.resume else None
    if resume_state and resume_state.total > 0:
        log(
            f"[joryu-curate] --resume: 既存 {resume_state.total} 件をスキップ"
            f" (採用 {resume_state.kept} / 棄却 {resume_state.rejected})",
            file=sys.stderr,
        )

    judge: JudgeClient | None = _judge if _judge is not None else _build_judge(cfg, args)
    style_rules = load_style_rules(cfg.distill.styles_file)
    stat_signals = build_default_stat_signals(cfg.curate.thresholds, style_rules=style_rules)

    # MinHash 永続化 (R-24): 過去ラン or 直近 cache_from から index をロード
    dup_index_path = _resolve_dup_index_path(args, dst)
    dup_index = (
        GlobalDuplicateIndex.load(
            dup_index_path,
            threshold=cfg.curate.thresholds.dup_glob_jaccard,
        )
        if dup_index_path is not None
        else GlobalDuplicateIndex(threshold=cfg.curate.thresholds.dup_glob_jaccard)
    )
    if len(dup_index) > 0:
        log(
            f"[joryu-curate] MinHash index ロード: {len(dup_index)} 件 ({dup_index.backend})",
            file=sys.stderr,
        )
    for s in stat_signals:
        if isinstance(s, DupGlobal):
            s.inject_index(dup_index)

    llm_signal = LLMRubricSignal(judge=judge) if judge is not None else None

    # キャッシュ (R-20 / R-23)
    cache_index: CacheIndex = _build_cache_index(args, dst, log)
    # per-record の signal バージョン (キャッシュ照合用)。SAMP-OUT はバッチ post-hoc なので除外。
    expected_versions = {s.code: s.version for s in stat_signals}
    if llm_signal is not None:
        expected_versions[llm_signal.code] = llm_signal.version
    counters = CacheCounters()

    composites = []
    records: list[dict[str, Any]] = []
    record_hashes: list[str] = []
    llm_calls = 0
    input_records = 0
    schema_skipped = 0
    log(f"[joryu-curate] 入力: {src}", file=sys.stderr)
    log(f"[joryu-curate] 出力: {dst}", file=sys.stderr)

    skipped_resume = 0
    resume_hashes = resume_state.evaluated_hashes if resume_state else set()
    for i, rec in enumerate(iter_records(src), 1):
        if args.count and i > args.count:
            break
        input_records += 1
        rh = compute_record_hash(rec)
        if rh in resume_hashes:
            # 既に評価済み: スキップ (scores.jsonl の末尾に書き足し済み)
            skipped_resume += 1
            continue
        schema_ok = rec.pop("_schema_ok", True)
        if not schema_ok:
            schema_skipped += 1
            records.append(rec)
            record_hashes.append(rh)
            composites.append(_schema_rejected_composite(stat_signals))
            continue

        reuse = cache_index.lookup(rh, expected_versions=expected_versions)

        if args.rescore_only:
            # --rescore-only: LLM 含めて新規評価せず、キャッシュからのみ合成
            if reuse.cached is None:
                counters.rescore_only_misses += 1
                # 評価不能 → ハード棄却扱い
                records.append(rec)
                record_hashes.append(rh)
                composites.append(_rescore_miss_composite(stat_signals, llm_signal))
                continue
            stat_results = [
                signal_result_from_cache(s.code, s.version, reuse.cached) for s in stat_signals
            ]
            llm_results = (
                [signal_result_from_cache(llm_signal.code, llm_signal.version, reuse.cached)]
                if llm_signal is not None and llm_signal.code in reuse.cached.signal_scores
                else []
            )
            counters.cache_hits_full += 1
            counters.llm_calls_saved += 1 if llm_results else 0
        elif reuse.is_full_hit:
            # 全 version 一致: LLM 含めて完全再利用
            stat_results = [
                signal_result_from_cache(s.code, s.version, reuse.cached) for s in stat_signals
            ]
            llm_results = (
                [signal_result_from_cache(llm_signal.code, llm_signal.version, reuse.cached)]
                if llm_signal is not None and llm_signal.code in reuse.cached.signal_scores
                else []
            )
            counters.cache_hits_full += 1
            if llm_results:
                counters.llm_calls_saved += 1
        else:
            # 新規 or 部分: stale signal だけ再評価
            stat_results = []
            for s in stat_signals:
                if s.code in reuse.reusable_signals and reuse.cached is not None:
                    stat_results.append(signal_result_from_cache(s.code, s.version, reuse.cached))
                else:
                    stat_results.append(s.evaluate(rec))
            hard = any(r.hard_reject for r in stat_results)
            llm_results = []
            if llm_signal is not None and not hard:
                if (
                    reuse.cached is not None
                    and llm_signal.code in reuse.reusable_signals
                    and llm_signal.code in reuse.cached.signal_scores
                ):
                    llm_results = [
                        signal_result_from_cache(llm_signal.code, llm_signal.version, reuse.cached)
                    ]
                    counters.llm_calls_saved += 1
                else:
                    llm_results = [llm_signal.evaluate(rec)]
                    llm_calls += 1
            if reuse.is_partial_hit:
                counters.cache_hits_partial += 1
            else:
                counters.newly_evaluated += 1

        composites.append(
            build_composite(
                stat_results=stat_results,
                llm_results=llm_results,
                w_stat=cfg.curate.weights_stat,
                w_llm=cfg.curate.weights_llm,
            )
        )
        records.append(rec)
        record_hashes.append(rh)

    # SAMP-OUT: bucket 内 z-score 外れ値の post-hoc 棄却。
    samp_out_rejected = apply_samp_out_filter(
        records,
        composites,
        z_min=cfg.curate.thresholds.samp_out_z_min,
        min_bucket_size=cfg.curate.thresholds.samp_out_min_bucket_size,
    )
    if samp_out_rejected:
        log(f"[joryu-curate] SAMP-OUT post-hoc 棄却: {samp_out_rejected} 件", file=sys.stderr)

    # best-of-N: 同一 (prompt, mode) グループから 1 件を採用、他は棄却。
    strategy = parse_strategy(args.best_of_n)
    if strategy != "off":
        bon_results = apply_best_of_n(
            records, composites, record_hashes, strategy=strategy, judge=judge
        )
        bon_rejected = sum(1 for r in bon_results if not r.is_winner and r.group_size > 1)
        if bon_rejected:
            log(
                f"[joryu-curate] best-of-N ({strategy}) で {bon_rejected} 件を棄却",
                file=sys.stderr,
            )

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
    # resume を考慮した最終件数
    total_kept = writer.kept + (resume_state.kept if resume_state else 0)
    total_rejected = writer.rejected + (resume_state.rejected if resume_state else 0)
    incremental = {
        "input_records": input_records,
        "cache_hits_full": counters.cache_hits_full,
        "cache_hits_partial": counters.cache_hits_partial,
        "newly_evaluated": counters.newly_evaluated,
        "llm_calls_total": llm_calls,
        "llm_calls_saved_vs_full_rerun": counters.llm_calls_saved,
        "cache_sources": list(cache_index.sources),
        "rescore_only_misses": counters.rescore_only_misses,
        "resume_skipped": skipped_resume,
    }
    write_curation_meta(
        dst,
        src_path=src,
        input_records=input_records,
        kept=total_kept,
        rejected=total_rejected,
        curate_fingerprints=cfg.curate_fingerprints(),
        judge_model=cfg.curate.judge_model,
        judge_mode=cfg.curate.judge_mode,
        signal_versions=signal_versions,
        cli_args=vars(args),
        git_sha=git_head_at(Path.cwd()),
        llm_calls_total=llm_calls,
        incremental=incremental,
    )

    # MinHash index 永続化 (次ランで使う)
    saved = dup_index.save(dst / DEFAULT_INDEX_FILENAME)
    log(f"[joryu-curate] MinHash index 保存: {saved} ({len(dup_index)} 件)", file=sys.stderr)

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

    keep_rate = (total_kept / input_records) if input_records else 0.0
    log(
        f"[joryu-curate] 入力 {input_records} 件 → 採用 {total_kept} ({keep_rate:.1%}) / "
        f"棄却 {total_rejected} / schema NG {schema_skipped} / "
        f"LLM 呼び出し {llm_calls} 回 / resume スキップ {skipped_resume} 件",
        file=sys.stderr,
    )
    # R-25 差分実行サマリを stderr に整形出力
    log(format_incremental_summary(incremental), file=sys.stderr)
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


def _rescore_miss_composite(stat_signals: list, llm_signal: Any) -> Any:
    """--rescore-only でキャッシュ未ヒットだったレコード用 (棄却理由 = 'rescore_miss')。"""
    from joryu.curate.scoring import CompositeScore

    versions = {s.code: s.version for s in stat_signals}
    if llm_signal is not None:
        versions[llm_signal.code] = llm_signal.version
    return CompositeScore(
        stat_score=0.0,
        llm_score=None,
        final_score=0.0,
        hard_rejected_by=["rescore_miss"],
        signal_versions=versions,
        signal_scores={},
        signal_raw={},
    )


def _build_cache_index(args: argparse.Namespace, dst: Path, log: Any) -> CacheIndex:
    """--cache-from / --no-cache の指示に従ってキャッシュ index を構築する。"""
    if args.no_cache:
        return CacheIndex()
    if args.cache_from:
        paths = [Path(p) for p in args.cache_from]
    else:
        paths = auto_detect_cache_paths(dst.parent, current_dst=dst)
    if not paths:
        return CacheIndex()
    index = load_cache_index(paths)
    if len(index) > 0:
        log(
            f"[joryu-curate] キャッシュロード: {len(index)} 件 (sources={index.sources})",
            file=sys.stderr,
        )
    return index


def _resolve_dup_index_path(args: argparse.Namespace, dst: Path) -> Path | None:
    """MinHash index のロード元パスを決める。

    優先順位:
    1. --no-cache 指定時は新規作成 (None)
    2. --cache-from の最後のディレクトリ配下の minhash.index
    3. dst.parent 配下の最新ランの minhash.index
    4. なければ None (空 index で開始)
    """
    if args.no_cache:
        return None
    if args.cache_from:
        last = Path(args.cache_from[-1])
        if last.is_file():
            last = last.parent
        candidate = last / DEFAULT_INDEX_FILENAME
        return candidate if candidate.exists() else None
    return find_latest_run_artifact(
        dst.parent,
        exclude=dst,
        marker=DEFAULT_INDEX_FILENAME,
    )


def _collect_signal_versions(
    stat_signals: list,
    llm_signal: LLMRubricSignal | None,
) -> dict[str, str]:
    versions = {s.code: s.version for s in stat_signals}
    # SAMP-OUT は per-record の Signal ではなく post-hoc バッチフィルタなので、
    # build_default_stat_signals に入らない。ここで明示的に記録する。
    versions[SAMP_OUT_CODE] = SAMP_OUT_VERSION
    if llm_signal is not None:
        versions[llm_signal.code] = llm_signal.version
    return versions


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
