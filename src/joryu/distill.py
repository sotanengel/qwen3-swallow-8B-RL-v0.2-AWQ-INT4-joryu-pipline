"""コア蒸留ループ。prompt bank → JSONL レコード。

mode 概念は #94 で削除し、Qwen3 の thinking モードで固定運用する。
"""

from __future__ import annotations

import hashlib
import json
import logging
import sys
import time
from collections.abc import Callable
from dataclasses import asdict, replace
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from typing import Any

from joryu.config import Config
from joryu.dashboard_json import write_dashboard_json
from joryu.distill_live import DistillLiveState
from joryu.distill_retry import generate_until_complete
from joryu.paths import DEFAULT_CONFIG, resolve_config_relative, resolve_repo_root
from joryu.progress import load_done_keys, load_truncated_run_keys, run_key_from_parts
from joryu.progress_reporter import DistillProgressReporter
from joryu.prompt_bank import EffectiveSampling, PromptRow, load_prompt_bank
from joryu.stats import compute_stats, resolve_stats_output_path
from joryu.styles import StylePreset, load_styles, resolve_style_ids
from joryu.tool_calls import ParsedToolCall
from joryu.tool_executor import ToolExecutor, build_default_executor
from joryu.tools import load_tools
from joryu.variants import DistillVariant, expand_variants
from joryu.vllm_client import ChatResult, SupportsChat, VllmError
from joryu.writer import JsonlAppendWriter

logger = logging.getLogger(__name__)

STATS_REFRESH_INTERVAL_SEC = 3.0


def _resolve_tools_path(
    config: Config,
    *,
    config_path: Path | None,
    out_p: Path,
) -> Path:
    """tools.yaml の絶対パスを config 親基準で解決する。"""
    if config_path is not None:
        return resolve_config_relative(config_path, config.distill.tools_file)
    root = resolve_repo_root(out_path=out_p)
    if root is not None:
        return resolve_config_relative(root / DEFAULT_CONFIG, config.distill.tools_file)
    rel = Path(config.distill.tools_file)
    if rel.is_absolute():
        return rel.resolve()
    return rel.resolve()


def _build_record(
    *,
    row: PromptRow,
    eff: EffectiveSampling,
    thinking: str | None,
    answer: str,
    model_name: str,
    config_hash: str,
    chat: ChatResult,
    turns: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    sampling = dict(eff.sampling)
    if chat.effective_max_tokens is not None:
        sampling["effective_max_tokens"] = chat.effective_max_tokens
    return {
        "prompt": row.prompt,
        "category": row.category,
        "style_id": eff.style_id,
        "system_prompt": eff.system_prompt,
        "sampling": sampling,
        "thinking_trace": thinking,
        "reasoning": thinking or "",
        "answer": answer,
        "model": model_name,
        "config_hash": config_hash,
        "finish_reason": chat.finish_reason,
        "prompt_tokens": chat.prompt_tokens,
        "completion_tokens": chat.completion_tokens,
        "tools": eff.tools,
        "tool_ids_requested": row.tool_ids,
        "tool_calls": [asdict(c) for c in chat.tool_calls],
        "turns": turns or [],
        "created_at": datetime.now(UTC).isoformat(),
    }


def _record_from_chat(
    chat: ChatResult,
    *,
    row: PromptRow,
    eff: EffectiveSampling,
    model_name: str,
    config_hash: str,
    turns: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    thinking = chat.thinking
    final_answer = (chat.answer or "").strip()
    return _build_record(
        row=row,
        eff=eff,
        thinking=thinking,
        answer=final_answer,
        model_name=model_name,
        config_hash=config_hash,
        chat=chat,
        turns=turns,
    )


def _tool_calls_to_openai(tool_calls: tuple[ParsedToolCall, ...]) -> list[dict[str, Any]]:
    """Qwen3 chat_template 互換の assistant.tool_calls 配列を組み立てる。"""
    return [
        {
            "function": {
                "name": call.name,
                "arguments": json.dumps(call.arguments, ensure_ascii=False),
            }
        }
        for call in tool_calls
    ]


def _append_tool_turn_messages(
    working_messages: list[dict[str, Any]],
    *,
    assistant_content: str,
    tool_calls: tuple[ParsedToolCall, ...],
    tool_results: list[tuple[str, str]],
) -> list[dict[str, Any]]:
    """assistant (tool_calls 付き) + tool 応答を working_messages に追記する。"""
    updated: list[dict[str, Any]] = [
        *working_messages,
        {
            "role": "assistant",
            "content": assistant_content,
            "tool_calls": _tool_calls_to_openai(tool_calls),
        },
    ]
    for name, content in tool_results:
        updated.append({"role": "tool", "content": content, "name": name})
    return updated


def _run_chat_loop(
    client: SupportsChat,
    messages: list[dict[str, Any]],
    *,
    tools: list[dict[str, Any]] | None,
    executor: ToolExecutor | None,
    max_turns: int,
    sampling: dict[str, Any],
) -> tuple[ChatResult, list[dict[str, Any]]]:
    """tool_call が無くなるか max_turns に達するまで chat を回す。"""
    turns: list[dict[str, Any]] = []
    working_messages = list(messages)
    final_chat: ChatResult | None = None
    exhausted = False

    for _turn in range(max_turns):
        chat = client.chat_via_template(
            working_messages,
            enable_thinking=True,
            tools=tools,
            **sampling,
        )
        final_chat = chat
        turns.append(
            {
                "role": "assistant",
                "content": chat.answer,
                "tool_calls": [asdict(c) for c in chat.tool_calls],
            }
        )
        if not chat.tool_calls or executor is None:
            break

        assistant_content = chat.answer or ""
        tool_results: list[tuple[str, str]] = []
        for call in chat.tool_calls:
            if call.name == "<malformed>":
                result = "error: malformed tool_call"
            else:
                try:
                    result = executor.run(call)
                except (KeyError, ValueError) as exc:
                    result = f"error: {exc}"
            tool_results.append((call.name, result))
            turns.append({"role": "tool", "name": call.name, "content": result})
        working_messages = _append_tool_turn_messages(
            working_messages,
            assistant_content=assistant_content,
            tool_calls=chat.tool_calls,
            tool_results=tool_results,
        )
    else:
        exhausted = final_chat is not None and bool(final_chat.tool_calls)

    if final_chat is None:
        raise RuntimeError("chat loop produced no result")

    if exhausted:
        final_chat = ChatResult(
            thinking=final_chat.thinking,
            answer=final_chat.answer,
            finish_reason="tool_loop_exhausted",
            prompt_tokens=final_chat.prompt_tokens,
            completion_tokens=final_chat.completion_tokens,
            effective_max_tokens=final_chat.effective_max_tokens,
            tool_calls=final_chat.tool_calls,
        )
    return final_chat, turns


def _make_tool_loop_chat_fn(
    client: SupportsChat,
    executor: ToolExecutor,
    max_turns: int,
    turns_holder: dict[str, list[dict[str, Any]]],
) -> Callable[..., ChatResult]:
    def _chat_with_loop(
        loop_messages: list[dict[str, str]],
        *,
        tools: list[dict[str, Any]] | None,
        **sampling_kwargs: Any,
    ) -> ChatResult:
        chat, turns = _run_chat_loop(
            client,
            loop_messages,
            tools=tools,
            executor=executor,
            max_turns=max_turns,
            sampling=sampling_kwargs,
        )
        turns_holder["turns"] = turns
        return chat

    return _chat_with_loop


def _aggregate_tool_calls_from_turns(turns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """tool_loop の各 assistant turn から tool_calls を集約する。"""
    aggregated: list[dict[str, Any]] = []
    for turn in turns:
        if turn.get("role") != "assistant":
            continue
        for call in turn.get("tool_calls") or []:
            if isinstance(call, dict) and isinstance(call.get("name"), str):
                aggregated.append(call)
    return aggregated


def _make_build_with_turns(
    build_record: Callable[[ChatResult], dict[str, Any]],
    *,
    use_tool_loop: bool,
    turns_holder: dict[str, list[dict[str, Any]]],
) -> Callable[[ChatResult], dict[str, Any]]:
    def _build_with_turns(chat: ChatResult) -> dict[str, Any]:
        record = build_record(chat)
        if use_tool_loop:
            record["turns"] = turns_holder["turns"]
            aggregated = _aggregate_tool_calls_from_turns(turns_holder["turns"])
            if aggregated:
                record["tool_calls"] = aggregated
        return record

    return _build_with_turns


def _report_truncation_retry(
    attempt: int,
    _record: dict[str, Any],
    *,
    run_key: str,
    row: PromptRow,
    eff: EffectiveSampling,
    stats_throttler: _StatsRefreshThrottler | None,
) -> None:
    DistillLiveState.report_retry(
        run_key=run_key,
        prompt=row.prompt,
        style_id=eff.style_id,
        attempts=attempt,
    )
    if stats_throttler is not None:
        stats_throttler.maybe_refresh(force=True)


def variant_run_key(variant: DistillVariant) -> str:
    """DistillVariant から resume キーを構築。"""
    tool_names = sorted(
        t["function"]["name"]
        for t in variant.eff.tools
        if isinstance(t.get("function"), dict) and isinstance(t["function"].get("name"), str)
    )
    tools_hash = (
        hashlib.sha1(json.dumps(tool_names, ensure_ascii=False).encode()).hexdigest()[:8]
        if tool_names
        else None
    )
    return run_key_from_parts(
        prompt=variant.row.prompt,
        style_id=variant.eff.style_id,
        temperature=variant.eff.sampling.get("temperature"),
        top_p=variant.eff.sampling.get("top_p"),
        tools_hash=tools_hash,
    )


def default_stats_refresher(out_path: Path) -> None:
    """dashboard/public/stats.json を蒸留 JSONL から更新する。"""
    dst = resolve_stats_output_path(out_path=out_path)
    if dst is None:
        return
    stats = compute_stats(out_path)
    live = DistillLiveState.to_dict()
    if live["active"] or live["truncation_retries"]:
        stats["distill_live"] = live
    write_dashboard_json(dst, stats, source_path=out_path)


class _StatsRefreshThrottler:
    """蒸留中の stats.json 更新を間引く。"""

    def __init__(
        self,
        out_path: Path,
        refresher: Callable[[Path], None],
        *,
        interval_sec: float = STATS_REFRESH_INTERVAL_SEC,
        time_fn: Callable[[], float] | None = None,
    ) -> None:
        self._out_path = out_path
        self._refresher = refresher
        self._interval = interval_sec
        self._time_fn = time_fn or time.time
        self._last_refresh = -interval_sec

    def maybe_refresh(self, *, force: bool = False) -> None:
        now = self._time_fn()
        if not force and now - self._last_refresh < self._interval:
            return
        self._refresher(self._out_path)
        self._last_refresh = now


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
) -> int:
    """蒸留を実行し、新規に書き込んだレコード数を返す。"""
    log = _print if _print is not None else print

    bank_p = Path(bank_path) if bank_path else Path(config.distill.prompt_bank)
    if out_path is not None:
        out_p = Path(out_path)
    else:
        out_p = Path(config.distill.out_dir) / config.distill.out_file

    rows = load_prompt_bank(bank_p)
    if override_tool_ids:
        rows = [
            replace(row, tool_ids=list(override_tool_ids)) if not row.tool_ids else row
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
        from joryu.vllm_client import resolve_chat_client

        client = resolve_chat_client(config.model, config.vllm)

    use_tool_loop = config.distill.tool_loop if tool_loop is None else tool_loop
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
        _StatsRefreshThrottler(out_p, stats_refresher) if stats_refresher is not None else None
    )
    DistillLiveState.begin()
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
                    _record_from_chat,
                    row=row,
                    eff=eff,
                    model_name=config.model.name,
                    config_hash=fingerprint,
                )
                turns_holder: dict[str, list[dict[str, Any]]] = {"turns": []}
                chat_fn = (
                    _make_tool_loop_chat_fn(
                        client,
                        loop_executor,
                        loop_max_turns,
                        turns_holder,
                    )
                    if use_tool_loop and loop_executor is not None
                    else None
                )
                build_with_turns = _make_build_with_turns(
                    build_record,
                    use_tool_loop=use_tool_loop,
                    turns_holder=turns_holder,
                )

                on_retry = partial(
                    _report_truncation_retry,
                    run_key=run_key,
                    row=row,
                    eff=eff,
                    stats_throttler=stats_throttler,
                )

                try:
                    record, _attempts = generate_until_complete(
                        client=client,
                        messages=messages,
                        tools=eff.tools or None,
                        sampling=eff.sampling,
                        build_record=build_with_turns,
                        chat_fn=chat_fn,
                        deadline=deadline,
                        min_interval_sec=config.distill.min_interval_sec,
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

                DistillLiveState.clear_retry(run_key)
                final_answer = str(record.get("answer") or "")
                writer.write(record)
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
    """config.distill.styles_file から style ID を解決。"""
    if not style_ids:
        return []
    styles = load_styles(config.distill.styles_file)
    return resolve_style_ids(style_ids, styles)
