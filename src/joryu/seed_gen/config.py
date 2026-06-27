"""seed_gen 設定ロード (domains.yaml)。"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

DEFAULT_DOMAINS_REL = "src/joryu/seed_gen/domains.yaml"
DEFAULT_TARGET_TOTAL = 230000


@dataclass(frozen=True)
class DomainSpec:
    key: str
    target: int
    seed_templates: list[str] = field(default_factory=list)
    themes: list[str] = field(default_factory=list)


@dataclass
class SeedGenConfig:
    version: int
    target_total: int
    domains: list[DomainSpec]
    legacy_category_aliases: dict[str, list[str]] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path | str) -> SeedGenConfig:
        p = Path(path)
        raw = yaml.safe_load(p.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError(f"domains config must be a mapping: {p}")
        domains_raw = raw.get("domains") or []
        domains: list[DomainSpec] = []
        for item in domains_raw:
            if not isinstance(item, dict):
                continue
            domains.append(
                DomainSpec(
                    key=str(item["key"]),
                    target=int(item["target"]),
                    seed_templates=list(item.get("seed_templates") or []),
                    themes=list(item.get("themes") or []),
                )
            )
        aliases = raw.get("legacy_category_aliases") or {}
        if not isinstance(aliases, dict):
            aliases = {}
        norm_aliases: dict[str, list[str]] = {
            str(k): [str(x) for x in v] for k, v in aliases.items() if isinstance(v, list)
        }
        return cls(
            version=int(raw.get("version", 1)),
            target_total=int(raw.get("target_total", DEFAULT_TARGET_TOTAL)),
            domains=domains,
            legacy_category_aliases=norm_aliases,
        )

    def with_target_total(self, target_total: int) -> SeedGenConfig:
        """各分野 target を比率維持でスケール。"""
        if target_total <= 0:
            raise ValueError("target_total must be positive")
        base = self.target_total
        if base <= 0:
            raise ValueError("invalid base target_total")
        ratio = target_total / base
        scaled = [
            DomainSpec(
                key=d.key,
                target=max(1, int(round(d.target * ratio))),
                seed_templates=list(d.seed_templates),
                themes=list(d.themes),
            )
            for d in self.domains
        ]
        return SeedGenConfig(
            version=self.version,
            target_total=target_total,
            domains=scaled,
            legacy_category_aliases=dict(self.legacy_category_aliases),
        )

    def filter_domain(self, domain_key: str) -> SeedGenConfig:
        filtered = [d for d in self.domains if d.key == domain_key]
        if not filtered:
            raise ValueError(f"unknown domain: {domain_key}")
        total = sum(d.target for d in filtered)
        return SeedGenConfig(
            version=self.version,
            target_total=total,
            domains=filtered,
            legacy_category_aliases=dict(self.legacy_category_aliases),
        )

    def category_to_domain_map(self) -> dict[str, str]:
        out: dict[str, str] = {}
        for domain_key, cats in self.legacy_category_aliases.items():
            for cat in cats:
                out[cat] = domain_key
        return out


def resolve_domains_config_path(repo_root: Path, rel: str) -> Path:
    p = Path(rel)
    if p.is_file():
        return p.resolve()
    candidate = (repo_root / rel).resolve()
    if candidate.is_file():
        return candidate
    raise FileNotFoundError(f"domains config not found: {rel}")


__all__ = [
    "DEFAULT_DOMAINS_REL",
    "DEFAULT_TARGET_TOTAL",
    "DomainSpec",
    "SeedGenConfig",
    "resolve_domains_config_path",
]
