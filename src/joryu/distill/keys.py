"""variant resume キー (#251)。"""

from __future__ import annotations

import hashlib
import json

from joryu.progress import run_key_from_parts
from joryu.variants import DistillVariant


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


__all__ = ["variant_run_key"]
