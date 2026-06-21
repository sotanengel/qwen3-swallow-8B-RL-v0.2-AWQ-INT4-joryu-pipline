"""コア蒸留ループ。prompt bank → JSONL レコード (per-row sampling/mode 記録)。"""

from __future__ import annotations

import logging
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from joryu.config import Config
from joryu.progress import load_done_keys, run_key_from_parts
from joryu.progress_reporter import DistillProgressReporter
from joryu.prompt_bank import EffectiveSampling, PromptRow, load_prompt_bank
from joryu.styles import StylePreset, load_styles, resolve_style_ids
from joryu.variants import DistillVariant, expand_variants
from joryu.vllm_client import SupportsChat, VllmClient
from joryu.writer import JsonlAppendWriter

logger = logging.getLogger(__name__)


def _build_record(
    *,
    row: PromptRow,
    eff: EffectiveSampling,
    thinking: str | None,
    answer: str,
    model_name: str,
    config_hash: str,
) -> dict[str, Any]:
    return {
        "prompt": row.prompt,
        "category": row.category,
        "style_id": eff.style_id,
        "mode": eff.mode,
        "system_prompt": eff.system_prompt,
        "sampling": dict(eff.sampling),
        "thinking_trace": thinking,
        "reasoning": thinking or "",
        "answer": answer,
        "model": model_name,
        "config_hash": config_hash,
        "created_at": datetime.now(UTC).isoformat(),
    }


def variant_run_key(variant: DistillVariant) -> str:
    """DistillVariant から resume キーを構築。"""
    return run_key_from_parts(
        prompt=variant.row.prompt,
        style_id=variant.eff.style_id,
        mode=variant.eff.mode,
        temperature=variant.eff.sampling.get("temperature"),
        top_p=variant.eff.sampling.get("top_p"),
    )


def run_distill(
    config: Config,
    *,
    bank_path: str | Path | None = None,
    out_path: str | Path | None = None,
    client: SupportsChat | None = None,
    count: int = 0,
    deadline: float | None = None,
    style_presets: list[StylePreset] | None = None,
    temperatures: list[float] | None = None,
    top_ps: list[float] | None = None,
    _print: Any = None,
) -> int:
    """蒸留を実行し、新規に書き込んだレコード数を返す。"""
    log = _print if _print is not None else print

    bank_p = Path(bank_path) if bank_path else Path(config.distill.prompt_bank)
    if out_path is not None:
        out_p = Path(out_path)
    else:
        out_p = Path(config.distill.out_dir) / config.distill.out_file

    rows = load_prompt_bank(bank_p)
    all_variants = expand_variants(
        rows,
        config,
        style_presets=style_presets,
        temperatures=temperatures,
        top_ps=top_ps,
    )
    done = load_done_keys(out_p)
    pending = [v for v in all_variants if variant_run_key(v) not in done]

    total_in_bank = len(all_variants)
    already_done = total_in_bank - len(pending)
    run_total = min(count, len(pending)) if count else len(pending)

    if run_total == 0:
        log(f"[joryu-distill] 処理対象なし → {out_p}", file=sys.stderr)
        return 0

    work = pending[:count] if count else pending

    if client is None:
        client = VllmClient.from_config(config.model, config.vllm)

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
    with JsonlAppendWriter(out_p) as writer:
        for i, variant in enumerate(work, 1):
            if deadline is not None and time.time() >= deadline:
                logger.info("[distill] deadline reached; stopping")
                log("[joryu-distill] 実行時間上限に達しました", file=sys.stderr)
                break

            row = variant.row
            eff = variant.eff
            messages = [
                {"role": "system", "content": eff.system_prompt},
                {"role": "user", "content": row.prompt},
            ]

            enable_thinking = eff.mode == "thinking"
            try:
                thinking, answer = client.chat_via_template(
                    messages,
                    enable_thinking=enable_thinking,
                    **eff.sampling,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("[distill] row failed (prompt=%r): %s", row.prompt[:40], exc)
                log(
                    f"[joryu-distill] [{i}/{run_total}] エラー: {exc}",
                    file=sys.stderr,
                )
                reporter.update(i)
                continue

            if eff.mode == "nothinking":
                thinking = None
            final_answer = (answer or "").strip()
            record = _build_record(
                row=row,
                eff=eff,
                thinking=thinking,
                answer=final_answer,
                model_name=config.model.name,
                config_hash=fingerprint,
            )
            writer.write(record)
            n += 1
            reporter.record_success(row.prompt, final_answer, style_id=eff.style_id)
            reporter.update(i)

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
