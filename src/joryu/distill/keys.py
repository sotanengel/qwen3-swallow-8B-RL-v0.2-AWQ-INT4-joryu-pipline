"""variant resume キー (#251)。"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from joryu.core.variants import DistillVariant
from joryu.persistence.progress import load_done_keys, run_key_from_parts, tools_hash_from_tools


def variant_run_key(variant: DistillVariant) -> str:
    """DistillVariant から resume キーを構築。"""
    return run_key_from_parts(
        prompt=variant.row.prompt,
        style_id=variant.eff.style_id,
        temperature=variant.eff.sampling.get("temperature"),
        top_p=variant.eff.sampling.get("top_p"),
        tools_hash=tools_hash_from_tools(variant.eff.tools),
    )


def count_done_variants(path: Path, all_variants: Sequence[DistillVariant]) -> int:
    """responses.jsonl の完了キーと照合し、バンク内の処理済 variant 数を返す。"""
    done = load_done_keys(path)
    if not done:
        return 0
    return sum(1 for variant in all_variants if variant_run_key(variant) in done)


__all__ = ["count_done_variants", "variant_run_key"]
