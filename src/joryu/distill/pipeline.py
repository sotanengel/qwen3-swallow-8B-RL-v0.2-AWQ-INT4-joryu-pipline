"""DistillPipeline ランナー (#251)。"""

from __future__ import annotations

import logging
import sys
import time
from collections.abc import Callable
from functools import partial
from pathlib import Path
from typing import Any

from joryu.config import Config
from joryu.distill.keys import variant_run_key
from joryu.distill.protocol import DistillContext, Stage
from joryu.distill.record import record_from_chat
from joryu.distill.stages import LoopStage, make_build_with_turns, make_tool_loop_chat_fn
from joryu.distill.stats import StatsRefreshThrottler, default_stats_refresher
from joryu.distill_live import DistillLiveState
from joryu.distill_retry import generate_until_complete
from joryu.paths import DEFAULT_CONFIG, resolve_config_relative, resolve_repo_root
from joryu.progress import load_done_keys, load_truncated_run_keys
from joryu.progress_reporter import DistillProgressReporter
from joryu.prompt_bank import PromptRow, load_prompt_bank
from joryu.prompt_dedup import PromptDedupGuard
from joryu.styles import StylePreset, load_styles, resolve_style_ids
from joryu.tool_executor import ToolExecutor, build_default_executor
from joryu.tools import load_tools
from joryu.variants import expand_variants
from joryu.vllm.common import is_prompt_context_overflow_error
from joryu.vllm.protocol import SupportsChat, VllmError
from joryu.writer import JsonlAppendWriter

logger = logging.getLogger(__name__)


def _resolve_tools_path(
    config: Config,
    *,
    config_path: Path | None,
    out_p: Path,
) -> Path:
    if config_path is not None:
        return resolve_config_relative(config_path, config.distill.tools_file)
    root = resolve_repo_root(out_path=out_p)
    if root is not None:
        return resolve_config_relative(root / DEFAULT_CONFIG, config.distill.tools_file)
    rel = Path(config.distill.tools_file)
    if rel.is_absolute():
        return rel.resolve()
    return rel.resolve()


def _should_retry_without_tools(exc: VllmError, *, had_tools: bool) -> bool:
    if not had_tools:
        return False
    detail = str(exc)
    return is_prompt_context_overflow_error(detail) or "prompt too long" in detail


def _generate_variant_record(
    *,
    client: SupportsChat,
    messages: list[dict[str, str]],
    eff: Any,
    include_tools: bool,
    use_tool_loop: bool,
    loop_executor: ToolExecutor | None,
    loop_max_turns: int,
    turns_holder: dict[str, Any],
    build_record: Callable[[Any], dict[str, Any]],
    no_think_fallback: bool,
    tool_loop_dedupe: bool,
    deadline: float | None,
    config: Config,
    on_retry: Callable[[int, dict[str, Any]], None] | None,
    log: Callable[..., Any],
) -> tuple[dict[str, Any] | None, int]:
    tools = (eff.tools or None) if include_tools else None
    active_tool_loop = use_tool_loop and loop_executor is not None and include_tools
    chat_fn = (
        make_tool_loop_chat_fn(
            client,
            loop_executor,
            loop_max_turns,
            turns_holder,
            no_think_fallback=no_think_fallback,
            tool_loop_dedupe=tool_loop_dedupe,
        )
        if active_tool_loop and loop_executor is not None
        else None
    )
    build_with_turns = make_build_with_turns(
        build_record,
        use_tool_loop=active_tool_loop,
        turns_holder=turns_holder,
        client=client if include_tools else None,
        messages=messages if include_tools else None,
        tools=tools,
        sampling=eff.sampling,
        no_think_fallback=no_think_fallback,
    )
    return generate_until_complete(
        client=client,
        messages=messages,
        tools=tools,
        sampling=eff.sampling,
        build_record=build_with_turns,
        chat_fn=chat_fn,
        deadline=deadline,
        min_interval_sec=config.distill.min_interval_sec,
        max_tokens_cap=config.distill.truncation_retry_max_tokens,
        max_attempts=config.distill.truncation_retry_max_attempts,
        on_retry=on_retry,
        log=log,
    )


def _report_truncation_retry(
    attempt: int,
    _record: dict[str, Any],
    *,
    run_key: str,
    row: PromptRow,
    eff: Any,
    stats_throttler: StatsRefreshThrottler | None,
) -> None:
    DistillLiveState.report_retry(
        run_key=run_key,
        prompt=row.prompt,
        style_id=eff.style_id,
        attempts=attempt,
    )
    if stats_throttler is not None:
        stats_throttler.maybe_refresh(force=True)


class DistillPipeline:
    """Stage 連結蒸留パイプライン。"""

    def __init__(self, stages: tuple[Stage, ...] | None = None) -> None:
        self._stages = stages or (LoopStage(),)

    def apply_stages(self, record: dict[str, Any], context: DistillContext) -> dict[str, Any]:
        for stage in self._stages:
            record = stage.process(record, context)
        return record

    def run(
        self,
        config: Config,
        *,
        bank_path: str | Path | None = None,
        out_path: str | Path | None = None,
        client: SupportsChat | None = None,
        count: int = 0,
        deadline: float | None = None,
        redo_truncated: bool = False,
        style_presets: list[StylePreset] | None = None,
        temperatures: list[float] | None = None,
        top_ps: list[float] | None = None,
        executor: ToolExecutor | None = None,
        tool_loop: bool | None = None,
        tool_loop_max_turns: int | None = None,
        override_tool_ids: list[str] | None = None,
        config_path: Path | None = None,
        _print: Any = None,
        stats_refresher: Callable[[Path], None] | None = None,
    ) -> int:
        return run_distill(
            config,
            bank_path=bank_path,
            out_path=out_path,
            client=client,
            count=count,
            deadline=deadline,
            redo_truncated=redo_truncated,
            style_presets=style_presets,
            temperatures=temperatures,
            top_ps=top_ps,
            executor=executor,
            tool_loop=tool_loop,
            tool_loop_max_turns=tool_loop_max_turns,
            override_tool_ids=override_tool_ids,
            config_path=config_path,
            _print=_print,
            stats_refresher=stats_refresher,
            pipeline=self,
        )


def run_distill(
    config: Config,
    *,
    bank_path: str | Path | None = None,
    out_path: str | Path | None = None,
    client: SupportsChat | None = None,
    count: int = 0,
    deadline: float | None = None,
    redo_truncated: bool = False,
    style_presets: list[StylePreset] | None = None,
    temperatures: list[float] | None = None,
    top_ps: list[float] | None = None,
    executor: ToolExecutor | None = None,
    tool_loop: bool | None = None,
    tool_loop_max_turns: int | None = None,
    override_tool_ids: list[str] | None = None,
    config_path: Path | None = None,
    _print: Any = None,
    stats_refresher: Callable[[Path], None] | None = None,
    pipeline: DistillPipeline | None = None,
) -> int:
    """蒸留を実行し、新規に書き込んだレコード数を返す。"""
    pipe = pipeline or DistillPipeline()
    log = _print if _print is not None else print

    bank_p = Path(bank_path) if bank_path else Path(config.distill.prompt_bank)
    out_p = Path(out_path) if out_path else Path(config.distill.out_dir) / config.distill.out_file

    rows = load_prompt_bank(bank_p)
    if override_tool_ids:
        rows = [
            row.model_copy(update={"tool_ids": list(override_tool_ids)})
            if not row.tool_ids
            else row
            for row in rows
        ]
    tools_path = _resolve_tools_path(config, config_path=config_path, out_p=out_p)
    tools_registry = load_tools(tools_path)
    all_variants = expand_variants(
        rows,
        config,
        style_presets=style_presets,
        temperatures=temperatures,
        top_ps=top_ps,
        tools_registry=tools_registry,
    )
    done = load_done_keys(out_p)
    if redo_truncated and out_p.exists():
        truncated_keys = load_truncated_run_keys(out_p)
        if truncated_keys:
            done -= truncated_keys
            log(
                f"[joryu-distill] --redo-truncated: {len(truncated_keys)} 件を再蒸留対象に含める",
                file=sys.stderr,
            )
    pending = [v for v in all_variants if variant_run_key(v) not in done]

    total_in_bank = len(all_variants)
    already_done = total_in_bank - len(pending)
    run_total = min(count, len(pending)) if count else len(pending)

    if run_total == 0:
        log(f"[joryu-distill] 処理対象なし → {out_p}", file=sys.stderr)
        return 0

    work = pending[:count] if count else pending

    if client is None:
        from joryu.vllm.factory import resolve_chat_client

        client = resolve_chat_client(config.model, config.vllm)

    use_tool_loop = config.distill.tool_loop if tool_loop is None else tool_loop
    no_think_fallback = config.distill.no_think_fallback
    tool_loop_dedupe = config.distill.tool_loop_dedupe
    loop_max_turns = (
        config.distill.tool_loop_max_turns if tool_loop_max_turns is None else tool_loop_max_turns
    )
    loop_executor = executor
    if use_tool_loop and loop_executor is None:
        loop_executor = build_default_executor()

    reporter = DistillProgressReporter(
        prefix="[joryu-distill]",
        total_in_bank=total_in_bank,
        already_done=already_done,
        run_total=run_total,
        action_label="蒸留",
        log=log,
    )
    reporter.log_start()

    fingerprint = config.fingerprint()
    n = 0
    stats_throttler = (
        StatsRefreshThrottler(out_p, stats_refresher) if stats_refresher is not None else None
    )
    DistillLiveState.begin()
    dedup_guard = PromptDedupGuard(max_per_key=config.distill.max_records_per_prompt_style)
    try:
        with JsonlAppendWriter(out_p) as writer:
            for i, variant in enumerate(work, 1):
                if deadline is not None and time.time() >= deadline:
                    logger.info("[distill] deadline reached; stopping")
                    log("[joryu-distill] 実行時間上限に達しました", file=sys.stderr)
                    break

                row = variant.row
                eff = variant.eff
                run_key = variant_run_key(variant)
                messages = [
                    {"role": "system", "content": eff.system_prompt},
                    {"role": "user", "content": row.prompt},
                ]

                build_record = partial(
                    record_from_chat,
                    row=row,
                    eff=eff,
                    model_name=config.model.name,
                    config_hash=fingerprint,
                )
                turns_holder: dict[str, Any] = {"turns": []}
                had_tools = bool(eff.tools)
                on_retry = partial(
                    _report_truncation_retry,
                    run_key=run_key,
                    row=row,
                    eff=eff,
                    stats_throttler=stats_throttler,
                )

                tools_disabled_retry = False
                record: dict[str, Any] | None = None
                try:
                    record, _attempts = _generate_variant_record(
                        client=client,
                        messages=messages,
                        eff=eff,
                        include_tools=True,
                        use_tool_loop=use_tool_loop,
                        loop_executor=loop_executor,
                        loop_max_turns=loop_max_turns,
                        turns_holder=turns_holder,
                        build_record=build_record,
                        no_think_fallback=no_think_fallback,
                        tool_loop_dedupe=tool_loop_dedupe,
                        deadline=deadline,
                        config=config,
                        on_retry=on_retry,
                        log=log,
                    )
                except VllmError as exc:
                    if "failed to load vLLM model" in str(exc):
                        logger.error("[distill] vLLM load failed; aborting job")
                        log(
                            "[joryu-distill] vLLM ロード失敗 — ジョブを中止します。"
                            " `uv run joryu-up` または `uv run joryu-probe-vllm` で"
                            " GPU 上限を記録してください。",
                            file=sys.stderr,
                        )
                        log(f"[joryu-distill] [{i}/{run_total}] エラー: {exc}", file=sys.stderr)
                        reporter.update(i)
                        break
                    if _should_retry_without_tools(exc, had_tools=had_tools):
                        log(
                            "[joryu-distill] コンテキスト超過 — ツール無効で再試行します",
                            file=sys.stderr,
                        )
                        turns_holder = {"turns": []}
                        try:
                            record, _attempts = _generate_variant_record(
                                client=client,
                                messages=messages,
                                eff=eff,
                                include_tools=False,
                                use_tool_loop=use_tool_loop,
                                loop_executor=loop_executor,
                                loop_max_turns=loop_max_turns,
                                turns_holder=turns_holder,
                                build_record=build_record,
                                no_think_fallback=no_think_fallback,
                                tool_loop_dedupe=tool_loop_dedupe,
                                deadline=deadline,
                                config=config,
                                on_retry=on_retry,
                                log=log,
                            )
                            tools_disabled_retry = True
                        except VllmError as retry_exc:
                            logger.warning(
                                "[distill] row failed after tools-disabled retry (prompt=%r): %s",
                                row.prompt[:40],
                                retry_exc,
                            )
                            log(
                                f"[joryu-distill] [{i}/{run_total}] エラー: {retry_exc}",
                                file=sys.stderr,
                            )
                            reporter.update(i)
                            continue
                    else:
                        logger.warning("[distill] row failed (prompt=%r): %s", row.prompt[:40], exc)
                        log(
                            f"[joryu-distill] [{i}/{run_total}] エラー: {exc}",
                            file=sys.stderr,
                        )
                        reporter.update(i)
                        continue
                except Exception as exc:  # noqa: BLE001
                    logger.warning("[distill] row failed (prompt=%r): %s", row.prompt[:40], exc)
                    log(
                        f"[joryu-distill] [{i}/{run_total}] エラー: {exc}",
                        file=sys.stderr,
                    )
                    reporter.update(i)
                    continue

                if record is None:
                    log(
                        f"[joryu-distill] [{i}/{run_total}] "
                        "打ち切りのまま deadline 到達 — 書き込みスキップ",
                        file=sys.stderr,
                    )
                    reporter.update(i)
                    continue

                if tools_disabled_retry:
                    record["tools_disabled_retry"] = True

                context = DistillContext(
                    config=config,
                    client=client,
                    row=row,
                    eff=eff,
                    model_name=config.model.name,
                    config_hash=fingerprint,
                    messages=messages,
                    turns_holder=turns_holder,
                    executor=loop_executor,
                    use_tool_loop=use_tool_loop,
                    no_think_fallback=no_think_fallback,
                )
                record = pipe.apply_stages(record, context)

                DistillLiveState.clear_retry(run_key)
                final_answer = str(record.get("answer") or "")
                style_key = eff.style_id if eff.style_id is not None else ""
                if dedup_guard.should_skip(prompt=row.prompt, style_id=style_key):
                    log(
                        f"[joryu-distill] [{i}/{run_total}] "
                        f"重複プロンプト上限 — スキップ (style={style_key!r})",
                        file=sys.stderr,
                    )
                    reporter.update(i)
                    continue
                writer.write(record)
                dedup_guard.record(prompt=row.prompt, style_id=style_key)
                n += 1
                reporter.record_success(row.prompt, final_answer, style_id=eff.style_id)
                reporter.update(i)
                if stats_throttler is not None:
                    stats_throttler.maybe_refresh()
    finally:
        DistillLiveState.end()
        if stats_throttler is not None:
            stats_throttler.maybe_refresh(force=True)

    reporter.log_finish(n, out_path=out_p)
    return n


def load_style_presets_from_config(
    config: Config,
    style_ids: list[str],
) -> list[StylePreset]:
    if not style_ids:
        return []
    styles = load_styles(config.distill.styles_file)
    return resolve_style_ids(style_ids, styles)


__all__ = [
    "DistillPipeline",
    "default_stats_refresher",
    "load_style_presets_from_config",
    "run_distill",
    "variant_run_key",
]
