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
) -> int:
    """蒸留を実行し、新規に書き込んだレコード数を返す。

    Parameters
    ----------
    config:
        設定。`config.distill.prompt_bank` / `out_dir+out_file` が既定パス。
    bank_path:
        prompt bank の上書き。
    out_path:
        出力 JSONL の上書き。
    client:
        SupportsChat 実装。`None` の場合は VllmClient を構築。
    count:
        0 = 全件、>0 = 新規生成件数の上限（バリアント含む）。
    deadline:
        UNIX 秒の時刻。超えたら次の prompt 前で打ち切る。
    style_presets:
        CLI `--style` から解決した文体プリセットリスト。
    temperatures:
        CLI `--temperature` スイープ値。
    top_ps:
        CLI `--top-p` スイープ値。
    """
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

    if client is None:
        client = VllmClient.from_config(config.model, config.vllm)

    fingerprint = config.fingerprint()
    n = 0
    with JsonlAppendWriter(out_p) as writer:
        for variant in pending:
            if deadline is not None and time.time() >= deadline:
                logger.info("[distill] deadline reached; stopping")
                break
            if count and n >= count:
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
                print(
                    f"[distill] skip row due to error: {exc}",
                    file=sys.stderr,
                )
                continue

            if eff.mode == "nothinking":
                thinking = None
            record = _build_record(
                row=row,
                eff=eff,
                thinking=thinking,
                answer=(answer or "").strip(),
                model_name=config.model.name,
                config_hash=fingerprint,
            )
            writer.write(record)
            n += 1
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
