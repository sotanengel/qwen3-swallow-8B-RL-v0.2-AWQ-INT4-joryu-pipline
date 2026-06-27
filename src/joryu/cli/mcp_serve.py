"""joryu-mcp CLI (stdio / streamable HTTP)。"""

from __future__ import annotations

import argparse


def main() -> None:
    parser = argparse.ArgumentParser(description="joryu MCP server")
    parser.add_argument("--stdio", action="store_true", help="Run with stdio transport")
    parser.add_argument("--http", action="store_true", help="Run HTTP bridge for McpToolExecutor")
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="HTTP bind address (default: 127.0.0.1)",
    )
    parser.add_argument("--port", type=int, default=8200, help="HTTP port (default: 8200)")
    args = parser.parse_args()

    if args.http:
        from joryu.mcp.http_bridge import run_http_server

        run_http_server(host=args.host, port=args.port)
        return

    from joryu.mcp import create_mcp_server

    mcp = create_mcp_server()
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
