"""verify_record_replay.py: tools フィールドから chat_template 入力を再構築。"""

from joryu.record_replay import rebuild_chat_template_inputs


def test_rebuild_chat_template_inputs_from_record() -> None:
    record = {
        "prompt": "hello",
        "system_prompt": "sys",
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "search",
                    "description": "search",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ],
    }
    inputs = rebuild_chat_template_inputs(record)
    assert inputs["tools"][0]["function"]["name"] == "search"
    assert inputs["messages"][1]["content"] == "hello"


def test_rebuild_rejects_invalid_tool_schema() -> None:
    record = {"prompt": "p", "system_prompt": "s", "tools": [{"type": "bad"}]}
    try:
        rebuild_chat_template_inputs(record)
    except ValueError as exc:
        assert "type=function" in str(exc)
    else:
        raise AssertionError("expected ValueError")
