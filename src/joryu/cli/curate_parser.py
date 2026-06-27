"""#253: Curate CLI 分割 — Parser。"""

from __future__ import annotations

import argparse


def build_curate_parser() -> argparse.ArgumentParser:
    """joryu-curate argparse を構築する。"""
    from joryu.cli.curate import build_parser

    return build_parser()


CurateOptionParser = build_curate_parser

__all__ = ["CurateOptionParser", "build_curate_parser"]
