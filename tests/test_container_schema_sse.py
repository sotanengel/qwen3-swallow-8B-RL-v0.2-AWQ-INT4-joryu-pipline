"""DependencyContainer / schema / SSE テスト。"""

from __future__ import annotations

from joryu.config_resolver import resolve_config_path
from joryu.schema import SchemaVersion, validate_mapping_schema
from joryu.streaming.sse import SSEDecoder, SSEEncoder


def test_resolve_config_path_defaults_to_config_yaml() -> None:
    path = resolve_config_path("config.yaml")
    assert path.name == "config.yaml"


def test_schema_version_defaults_to_one() -> None:
    model = SchemaVersion.model_validate({})
    assert model.version == 1


def test_validate_mapping_schema_rejects_bad_version() -> None:
    try:
        validate_mapping_schema({"version": 0}, label="tools.yaml")
    except ValueError as exc:
        assert "tools.yaml" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_sse_encoder_produces_event_block() -> None:
    out = SSEEncoder.encode({"type": "token", "delta": "hi"})
    assert out.startswith("event: token\n")
    assert "hi" in out


def test_sse_decoder_parses_json_data() -> None:
    parsed = SSEDecoder.decode_data_line('{"column":"prose","delta":"x"}')
    assert parsed is not None
    assert parsed["column"] == "prose"
