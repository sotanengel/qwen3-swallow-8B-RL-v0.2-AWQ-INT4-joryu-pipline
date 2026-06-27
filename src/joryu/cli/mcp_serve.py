"""joryu-mcp CLI (stdio / streamable HTTP)。"""

from __future__ import annotations

import argparse


def main() -> None:
    parser = argparse.ArgumentParser(description="joryu MCP server")
    parser.add_argument("--stdio", action="store_true", help="Run with stdio transport")
    parser.add_argument("--http", action="store_true", help="Run with streamable HTTP transport")
    parser.add_argument("--port", type=int, default=8200, help="HTTP port (default: 8200)")
    args = parser.parse_args()

    from joryu.mcp import create_mcp_server

    mcp = create_mcp_server()
    if args.http:
        mcp.settings.port = args.port
        mcp.run(transport="streamable-http")
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
