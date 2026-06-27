"""`.env.example` の存在と必須キー。"""

from __future__ import annotations

from pathlib import Path

REQUIRED_KEYS = [
    "JORYU_SEARCH_PROVIDER",
    "TAVILY_API_KEY",
    "JORYU_WEATHER_PROVIDER",
    "JORYU_FETCH_TIMEOUT",
    "JORYU_FETCH_MAX_BYTES",
    "JORYU_MCP_ENABLED",
    "JORYU_MCP_URL",
]


def test_env_example_exists_and_lists_keys() -> None:
    path = Path(".env.example")
    assert path.is_file()
    text = path.read_text(encoding="utf-8")
    for key in REQUIRED_KEYS:
        assert key in text, f"missing {key} in .env.example"
