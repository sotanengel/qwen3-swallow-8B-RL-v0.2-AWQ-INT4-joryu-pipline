"""DistillJobSpec の CLI / API / argv 契約テスト。"""

from __future__ import annotations

from dataclasses import fields
from typing import Any

import pytest
from fastapi.testclient import TestClient

from joryu.api.app import create_app
from joryu.cli.distill import build_parser
from joryu.jobs.models import DistillJobSpec


def test_distill_job_spec_field_names_match_dashboard_contract() -> None:
    names = {f.name for f in fields(DistillJobSpec)}
    assert names == {
        "count",
        "duration",
        "mode",
        "style",
        "temperature",
        "top_p",
        "config",
        "tool_ids",
        "tool_loop",
        "max_turns",
    }


def test_from_cli_namespace_round_trips_to_distill_argv() -> None:
    parser = build_parser()
    args = parser.parse_args(
        [
            "--count",
            "5",
            "--duration",
            "30m",
            "--mode",
            "nothinking",
            "--style",
            "polite,casual",
            "--temperature",
            "0.7,1.0",
            "--top-p",
            "0.9",
            "--bank",
            "data/prompts/x.jsonl",
            "--out",
            "data/out.jsonl",
        ]
    )
    spec = DistillJobSpec.from_cli_namespace(args)
    argv = spec.to_distill_argv(bank=args.bank, out=args.out)
    assert argv == [
        "--count",
        "5",
        "--duration",
        "30m",
        "--bank",
        "data/prompts/x.jsonl",
        "--out",
        "data/out.jsonl",
        "--mode",
        "nothinking",
        "--style",
        "polite,casual",
        "--temperature",
        "0.7,1.0",
        "--top-p",
        "0.9",
    ]


def test_from_dict_accepts_api_body_shape() -> None:
    body: dict[str, Any] = {
        "count": 2,
        "duration": "1h",
        "mode": "thinking",
        "style": ["polite"],
        "temperature": "0.6",
        "top_p": "0.95",
        "config": "config.yaml",
    }
    spec = DistillJobSpec.from_dict(body)
    assert spec.count == 2
    assert spec.style == ["polite"]
    assert spec.to_distill_argv() == [
        "--count",
        "2",
        "--duration",
        "1h",
        "--mode",
        "thinking",
        "--style",
        "polite",
        "--temperature",
        "0.6",
        "--top-p",
        "0.95",
    ]


@pytest.fixture
def api_client(tmp_path):
    (tmp_path / "config.yaml").write_text(
        """
model:
  name: test-model
  mode: thinking
distill:
  prompt_bank: data/prompts/training_prompts.jsonl
  out_dir: data/distilled
  out_file: responses.jsonl
  styles_file: styles.yaml
  system_prompt: test
export:
  out_dir: exports
""".strip(),
        encoding="utf-8",
    )
    (tmp_path / "styles.yaml").write_text(
        """
styles:
  polite:
    label: 丁寧語
    instruction: 丁寧に。
""".strip(),
        encoding="utf-8",
    )
    (tmp_path / "tools.yaml").write_text(
        """
tools:
  search:
    description: Web search
    parameters:
      type: object
      properties:
        query:
          type: string
      required: [query]
""".strip(),
        encoding="utf-8",
    )
    (tmp_path / "data" / "prompts").mkdir(parents=True)
    (tmp_path / "data" / "prompts" / "training_prompts.jsonl").write_text(
        '{"prompt":"hello"}\n',
        encoding="utf-8",
    )
    return TestClient(create_app(repo_root=tmp_path))


def test_api_create_job_accepts_distill_job_spec_fields(api_client: TestClient) -> None:
    resp = api_client.post(
        "/api/jobs",
        json={
            "count": 1,
            "duration": "",
            "mode": None,
            "style": [],
            "temperature": "",
            "top_p": "",
            "config": "config.yaml",
        },
    )
    assert resp.status_code == 201
    spec = resp.json()["spec"]
    for key in (
        "count",
        "duration",
        "mode",
        "style",
        "temperature",
        "top_p",
        "config",
        "tool_ids",
        "tool_loop",
        "max_turns",
    ):
        assert key in spec
