"""分野別プロンプトカウント (#313)。"""

from __future__ import annotations

from joryu.prompt_bank import PromptRow
from joryu.seed_gen.config import SeedGenConfig


def resolve_row_domain(row: PromptRow, cfg: SeedGenConfig) -> str | None:
    if row.domain:
        return row.domain
    if row.category:
        return cfg.category_to_domain_map().get(row.category)
    return None


def count_by_domain(rows: list[PromptRow], cfg: SeedGenConfig) -> dict[str, int]:
    counts = {d.key: 0 for d in cfg.domains}
    for row in rows:
        dom = resolve_row_domain(row, cfg)
        if dom and dom in counts:
            counts[dom] += 1
    return counts


__all__ = ["count_by_domain", "resolve_row_domain"]
