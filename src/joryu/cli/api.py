"""joryu-api: ジョブ投入用 REST API サーバー。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="joryu-api",
        description="蒸留ジョブ投入用 REST API (FastAPI + uvicorn)。",
    )
    p.add_argument("--host", default="127.0.0.1", help="bind host (既定: 127.0.0.1)")
    p.add_argument("--port", type=int, default=8000, help="bind port (既定: 8000)")
    p.add_argument(
        "--repo-root",
        default="",
        help="リポジトリルート (既定: cwd または JORYU_REPO_ROOT)",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repo_root = Path(args.repo_root).resolve() if args.repo_root else Path.cwd().resolve()

    try:
        import uvicorn
    except ImportError:
        print(
            "[joryu-api] uvicorn not installed. Run: uv sync --extra api",
            file=sys.stderr,
        )
        return 2

    from joryu.api.app import create_app

    app = create_app(repo_root=repo_root)
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
