"""joryu-llm-serve: vLLM 常駐デーモン CLI。"""

from __future__ import annotations

import argparse
import sys

from joryu.config import load_config
from joryu.llm_server import create_llm_app, warmup_client
from joryu.paths import DEFAULT_CONFIG, resolve_cli_config_path
from joryu.vllm_client import VllmClient


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="joryu-llm-serve",
        description="vLLM モデルを常駐ロードし HTTP API で推論を提供する。",
    )
    p.add_argument("--host", default="0.0.0.0", help="bind host (既定: 0.0.0.0)")
    p.add_argument("--port", type=int, default=0, help="bind port (0 = config vllm.serve_port)")
    p.add_argument(
        "--config",
        default=DEFAULT_CONFIG,
        help=f"設定 YAML (既定: {DEFAULT_CONFIG})",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config_path = resolve_cli_config_path(args.config)
    cfg = load_config(config_path)
    port = args.port or cfg.vllm.serve_port

    try:
        import uvicorn
    except ImportError:
        print(
            "[joryu-llm-serve] uvicorn not installed. Run: uv sync --extra api",
            file=sys.stderr,
        )
        return 2

    print(
        f"[joryu-llm-serve] loading model (warmup) before serving on {args.host}:{port}",
        file=sys.stderr,
    )
    client = VllmClient.from_config(cfg.model, cfg.vllm)
    warmup_client(client)
    app = create_llm_app(client, model_loaded=True)
    uvicorn.run(app, host=args.host, port=port, log_level="info")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
