"""joryu-export: 蒸留 JSONL を zstd 圧縮 + meta.json で `exports/<ts>/` に書き出す。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from joryu.cli.common import add_config_argument, resolve_cli_config, resolve_cli_distill_input
from joryu.export import DEFAULT_LEVEL, export_jsonl


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="joryu-export",
        description=(
            "蒸留 JSONL を zstd 圧縮し、meta.json + SHA256SUMS をつけて exports/<ts>/ に出力する。"
        ),
    )
    add_config_argument(p)
    p.add_argument(
        "--input",
        default="",
        help="入力 JSONL (既定: config.distill.out_dir/out_file)",
    )
    p.add_argument(
        "--out-dir",
        default="",
        help="出力親ディレクトリ (既定: config.export.out_dir)",
    )
    p.add_argument(
        "--level",
        type=int,
        default=0,
        help=f"zstd 圧縮レベル (1-22, 既定 0 = config の値, 全体既定 {DEFAULT_LEVEL})",
    )
    p.add_argument(
        "--bundle-tar",
        action="store_true",
        help="同階層に <timestamp>.tar も生成 (他リポジトリへの転送向け)",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    cfg = resolve_cli_config(args)

    src = resolve_cli_distill_input(args, cfg)
    out_dir = Path(args.out_dir) if args.out_dir else Path(cfg.export.out_dir)
    level = args.level if args.level > 0 else (cfg.export.level or DEFAULT_LEVEL)
    bundle_tar = args.bundle_tar or cfg.export.bundle_tar

    if not src.exists():
        print(f"[joryu-export] input not found: {src}", file=sys.stderr)
        return 2

    res = export_jsonl(src, out_dir=out_dir, level=level, bundle_tar=bundle_tar)
    print(
        f"[joryu-export] wrote {res.compressed_path}  (meta: {res.meta_path.name})",
        file=sys.stderr,
    )
    if res.tar_path is not None:
        print(f"[joryu-export] bundled: {res.tar_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
