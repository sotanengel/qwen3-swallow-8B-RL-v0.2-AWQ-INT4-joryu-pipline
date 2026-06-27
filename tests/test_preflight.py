"""preflight.py: git 差分映射とディスク preflight のユニットテスト。"""

from __future__ import annotations

import argparse
import platform
from pathlib import Path

import pytest

from joryu.preflight import (
    DISK_REQUIRED_GB,
    PreflightError,
    changed_services_from_git,
    check_disk_space,
    curation_needs_refresh,
    docker_image_exists,
    ensure_curation,
    ensure_dashboard_data_paths,
    ensure_prompt_bank,
    ensure_stats_json,
    ensure_vllm_limits,
    jsonl_has_content,
    path_affects_service,
    required_disk_gb,
    resolve_prompt_bank_seed_path,
    resolve_prompt_csv_path,
    resolve_up_services,
    resolve_vllm_limits_path,
    save_up_state,
    services_missing_build_at_head,
    services_to_build,
    should_force_recreate,
    should_up_mcp,
    stop_joryu_for_up,
    vllm_limits_probe_needed,
)


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("src/joryu/cli/up.py", {"joryu"}),
        ("src/joryu/distill.py", {"api", "joryu"}),
        ("src/joryu/preflight.py", {"api", "joryu"}),
        ("src/joryu/jobs/runner.py", {"api", "mcp"}),
        ("src/joryu/docker_delegate.py", {"api", "joryu"}),
        ("src/joryu/docker_runtime.py", {"api", "joryu"}),
        ("src/joryu/stats.py", {"api", "joryu"}),
        ("docker-compose.yml", {"api", "joryu", "mcp"}),
        ("src/joryu/jobs/models.py", {"api", "mcp"}),
        ("src/joryu/api/app.py", {"api", "mcp"}),
        ("Dockerfile.api", {"api", "mcp"}),
        ("Dockerfile", {"joryu"}),
        ("pyproject.toml", {"joryu"}),
        ("dashboard/src/app/page.tsx", {"dashboard"}),
        ("dashboard/Dockerfile", {"dashboard"}),
        ("dashboard/public/.gitkeep", {"dashboard"}),
        ("dashboard/public/responses.jsonl", set()),
        ("dashboard/public/stats.json", set()),
        ("README.md", {"joryu"}),
        ("docs/architecture.md", set()),
    ],
)
def test_path_affects_service(path: str, expected: set[str]) -> None:
    assert path_affects_service(path) == expected


def test_changed_services_from_git_merges_sources() -> None:
    def _fake_git(args: list[str], **_kwargs: object) -> _GitResult:
        if args[:3] == ["git", "diff", "--name-only"] and args[-1] == "HEAD":
            return _GitResult(stdout="src/joryu/cli/up.py\n")
        if args[:3] == ["git", "diff", "--name-only"] and args[-1] == "--cached":
            return _GitResult(stdout="dashboard/package.json\n")
        if args[:2] == ["git", "ls-files"]:
            return _GitResult(stdout="dashboard/public/.gitkeep\n")
        if args[:2] == ["git", "rev-parse"]:
            return _GitResult(stdout="newhead\n")
        return _GitResult(stdout="")

    changed = changed_services_from_git(Path("."), git_runner=_fake_git)
    assert changed == {"joryu", "dashboard"}


def test_changed_services_includes_commits_since_last_up(tmp_path: Path) -> None:
    state_dir = tmp_path / "data" / ".joryu"
    state_dir.mkdir(parents=True)
    (state_dir / "up-state.json").write_text(
        '{"git_head": "oldhead"}\n',
        encoding="utf-8",
    )

    def _fake_git(args: list[str], **_kwargs: object) -> _GitResult:
        if args[:2] == ["git", "rev-parse"]:
            return _GitResult(stdout="newhead\n")
        if args[:3] == ["git", "diff", "--name-only"] and args[-1] == "oldhead..newhead":
            return _GitResult(stdout="Dockerfile.api\n")
        return _GitResult(stdout="")

    changed = changed_services_from_git(tmp_path, git_runner=_fake_git)
    assert changed == {"api", "mcp"}


def test_services_to_build_first_run_builds_all_up_targets() -> None:
    assert services_to_build(
        ["dashboard", "api"],
        set(),
        no_build=False,
        first_run=True,
    ) == ["dashboard", "api", "joryu"]


def test_services_to_build_builds_joryu_when_image_missing() -> None:
    assert services_to_build(
        ["dashboard", "api"],
        set(),
        no_build=False,
        inspect_runner=lambda *_args, **_kwargs: _InspectResult(returncode=1),
    ) == ["joryu"]


def test_services_to_build_skips_joryu_when_image_exists_and_no_diff() -> None:
    assert (
        services_to_build(
            ["dashboard", "api"],
            set(),
            no_build=False,
            inspect_runner=lambda *_args, **_kwargs: _InspectResult(returncode=0),
        )
        == []
    )


def test_services_to_build_rebuilds_unbuilt_at_current_head(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("joryu.preflight.git_head_at", lambda _root, **_: "head-abc")
    save_up_state(tmp_path, "head-abc")
    assert services_missing_build_at_head(["dashboard", "api"], tmp_path) == {
        "dashboard",
        "api",
    }
    assert services_to_build(
        ["dashboard", "api"],
        set(),
        no_build=False,
        first_run=False,
        repo_root=tmp_path,
        inspect_runner=lambda *_args, **_kwargs: _InspectResult(returncode=0),
    ) == ["dashboard", "api"]


def test_services_to_build_skips_when_built_at_head(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("joryu.preflight.git_head_at", lambda _root, **_: "head-abc")
    save_up_state(tmp_path, "head-abc", built_services=["dashboard", "api", "joryu"])
    assert services_missing_build_at_head(["dashboard", "api"], tmp_path) == set()
    assert (
        services_to_build(
            ["dashboard", "api"],
            set(),
            no_build=False,
            first_run=False,
            repo_root=tmp_path,
            inspect_runner=lambda *_args, **_kwargs: _InspectResult(returncode=0),
        )
        == []
    )


def test_docker_image_exists() -> None:
    assert docker_image_exists(
        "joryu:latest",
        inspect_runner=lambda *_args, **_kwargs: _InspectResult(returncode=0),
    )
    assert not docker_image_exists(
        "joryu:latest",
        inspect_runner=lambda *_args, **_kwargs: _InspectResult(returncode=1),
    )


def test_services_to_build_force_build() -> None:
    assert services_to_build(
        ["dashboard", "api"],
        set(),
        no_build=False,
        force_build=True,
    ) == ["dashboard", "api", "joryu"]


def test_resolve_up_services_default_no_changes() -> None:
    args = argparse.Namespace(frontend_only=False, backend_only=False)
    assert resolve_up_services(args, set()) == ["dashboard", "api", "joryu"]


def test_resolve_up_services_default_with_joryu_diff() -> None:
    args = argparse.Namespace(frontend_only=False, backend_only=False)
    assert resolve_up_services(args, {"joryu"}) == ["dashboard", "api", "joryu"]


def test_resolve_up_services_default_with_both_diffs() -> None:
    args = argparse.Namespace(frontend_only=False, backend_only=False)
    assert resolve_up_services(args, {"joryu", "dashboard"}) == ["dashboard", "api", "joryu"]
    assert resolve_up_services(args, {"api", "dashboard"}) == ["dashboard", "api", "joryu"]


def test_should_up_mcp_requires_enabled_and_url(tmp_path: Path) -> None:
    cfg = tmp_path / "config.yaml"
    cfg.write_text("mcp:\n  enabled: true\n  url: http://mcp:8200\n", encoding="utf-8")
    assert should_up_mcp(tmp_path) is True

    cfg.write_text("mcp:\n  enabled: true\n  url: ''\n", encoding="utf-8")
    assert should_up_mcp(tmp_path) is False

    cfg.write_text("mcp:\n  enabled: false\n  url: http://mcp:8200\n", encoding="utf-8")
    assert should_up_mcp(tmp_path) is False


def test_resolve_up_services_includes_mcp_when_config_enabled(tmp_path: Path) -> None:
    (tmp_path / "config.yaml").write_text(
        "mcp:\n  enabled: true\n  url: http://mcp:8200\n",
        encoding="utf-8",
    )
    args = argparse.Namespace(frontend_only=False, backend_only=False)
    assert resolve_up_services(args, set(), repo_root=tmp_path) == [
        "dashboard",
        "mcp",
        "api",
        "joryu",
    ]


def test_resolve_up_services_skips_mcp_for_frontend_only(tmp_path: Path) -> None:
    (tmp_path / "config.yaml").write_text(
        "mcp:\n  enabled: true\n  url: http://mcp:8200\n",
        encoding="utf-8",
    )
    args = argparse.Namespace(frontend_only=True, backend_only=False)
    assert resolve_up_services(args, set(), repo_root=tmp_path) == ["dashboard"]


def test_services_to_build_intersection() -> None:
    def _image_exists(*_args: object, **_kwargs: object) -> _InspectResult:
        return _InspectResult(returncode=0)

    assert services_to_build(["dashboard", "joryu"], {"joryu"}, no_build=False) == ["joryu"]
    assert services_to_build(["dashboard"], {"joryu"}, no_build=False) == []
    assert services_to_build(["dashboard"], {"dashboard"}, no_build=True) == []
    assert services_to_build(
        ["dashboard", "api"],
        {"joryu"},
        no_build=False,
        inspect_runner=_image_exists,
    ) == ["joryu"]
    assert services_to_build(
        ["dashboard", "api"],
        {"dashboard", "joryu"},
        no_build=False,
        inspect_runner=_image_exists,
    ) == [
        "dashboard",
        "joryu",
    ]
    assert services_to_build(["dashboard", "api"], set(), no_build=False, force_build=True) == [
        "dashboard",
        "api",
        "joryu",
    ]


def test_required_disk_gb_sums_thresholds() -> None:
    assert required_disk_gb(["dashboard"]) == DISK_REQUIRED_GB["dashboard"]
    assert required_disk_gb(["joryu"]) == DISK_REQUIRED_GB["joryu"]
    assert required_disk_gb(["dashboard", "joryu"]) == (
        DISK_REQUIRED_GB["dashboard"] + DISK_REQUIRED_GB["joryu"]
    )


def test_check_disk_space_aborts_when_insufficient() -> None:
    # dashboard 閾値 (2 GB) を下回る空き容量を投入
    free_bytes = int(1 * 1024**3)
    with pytest.raises(PreflightError, match="空き容量不足"):
        check_disk_space(
            ["dashboard"],
            Path("."),
            force=False,
            disk_usage_fn=lambda _p: (100, 100, free_bytes),
        )


def test_check_disk_space_skipped_with_force() -> None:
    free_bytes = int(1 * 1024**3)
    check_disk_space(
        ["joryu"],
        Path("."),
        force=True,
        disk_usage_fn=lambda _p: (100, 100, free_bytes),
    )


def test_resolve_prompt_bank_seed_path_uses_default_seed(tmp_path: Path) -> None:
    seed = tmp_path / "scripts" / "seeds" / "training_prompts.jsonl"
    seed.parent.mkdir(parents=True)
    seed.write_text('{"prompt":"seed"}\n', encoding="utf-8")
    from joryu.config import Config

    assert resolve_prompt_bank_seed_path(tmp_path, Config()) == seed.resolve()


def test_ensure_prompt_bank_copies_zst_seed(tmp_path: Path) -> None:
    import zstandard as zstd

    payload = b'{"prompt":"seed"}\n'
    seed = tmp_path / "scripts" / "seeds" / "training_prompts.jsonl.zst"
    seed.parent.mkdir(parents=True)
    seed.write_bytes(zstd.ZstdCompressor(level=3).compress(payload))
    (tmp_path / "config.yaml").write_text(
        'distill:\n  prompt_bank: "data/prompts/training_prompts.jsonl"\n',
        encoding="utf-8",
    )

    ensure_prompt_bank(tmp_path)

    bank = tmp_path / "data" / "prompts" / "training_prompts.jsonl"
    assert bank.read_bytes() == payload


def test_ensure_prompt_bank_copies_seed_jsonl(tmp_path: Path) -> None:
    seed = tmp_path / "scripts" / "seeds" / "training_prompts.jsonl"
    seed.parent.mkdir(parents=True)
    seed.write_text('{"prompt":"seed"}\n', encoding="utf-8")
    (tmp_path / "config.yaml").write_text(
        'distill:\n  prompt_bank: "data/prompts/training_prompts.jsonl"\n',
        encoding="utf-8",
    )
    messages: list[str] = []

    ensure_prompt_bank(tmp_path, log=lambda msg: messages.append(msg))

    bank = tmp_path / "data" / "prompts" / "training_prompts.jsonl"
    assert bank.read_text(encoding="utf-8") == '{"prompt":"seed"}\n'
    assert any("copied from" in msg for msg in messages)


def test_resolve_prompt_csv_path_prefers_config(tmp_path: Path) -> None:
    csv_path = tmp_path / "src.csv"
    csv_path.write_text("分野,プロンプト\n国語,桜\n", encoding="utf-8")
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(
        f'distill:\n  prompt_csv: "{csv_path.as_posix()}"\n',
        encoding="utf-8",
    )
    from joryu.paths import resolve_optional_config

    cfg = resolve_optional_config(cfg_path)
    assert resolve_prompt_csv_path(tmp_path, cfg) == csv_path.resolve()


def test_resolve_prompt_csv_path_uses_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    csv_path = tmp_path / "env.csv"
    csv_path.write_text("分野,プロンプト\n国語,桜\n", encoding="utf-8")
    monkeypatch.setenv("JORYU_PROMPT_CSV", str(csv_path))
    from joryu.config import Config

    assert resolve_prompt_csv_path(tmp_path, Config()) == csv_path.resolve()


def test_ensure_prompt_bank_generates_from_csv(tmp_path: Path) -> None:
    csv_path = tmp_path / "prompts.csv"
    csv_path.write_text("分野,プロンプト\n国語,桜\n数学,1+1\n", encoding="utf-8")
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(
        f'distill:\n  prompt_bank: "data/prompts/training_prompts.jsonl"\n'
        f'  prompt_csv: "{csv_path.as_posix()}"\n',
        encoding="utf-8",
    )
    messages: list[str] = []

    ensure_prompt_bank(tmp_path, log=lambda msg: messages.append(msg))

    bank = tmp_path / "data" / "prompts" / "training_prompts.jsonl"
    assert bank.is_file()
    assert bank.read_text(encoding="utf-8").count("\n") == 2
    assert any("2 rows" in msg for msg in messages)


def test_ensure_prompt_bank_skips_when_exists(tmp_path: Path) -> None:
    bank = tmp_path / "data" / "prompts" / "training_prompts.jsonl"
    bank.parent.mkdir(parents=True)
    bank.write_text('{"prompt":"existing"}\n', encoding="utf-8")
    csv_path = tmp_path / "prompts.csv"
    csv_path.write_text("分野,プロンプト\n国語,桜\n", encoding="utf-8")
    (tmp_path / "config.yaml").write_text(
        f'distill:\n  prompt_bank: "data/prompts/training_prompts.jsonl"\n'
        f'  prompt_csv: "{csv_path.as_posix()}"\n',
        encoding="utf-8",
    )
    messages: list[str] = []

    ensure_prompt_bank(tmp_path, log=lambda msg: messages.append(msg))

    assert bank.read_text(encoding="utf-8") == '{"prompt":"existing"}\n'
    assert messages == []


def test_ensure_prompt_bank_raises_when_missing_source(tmp_path: Path) -> None:
    (tmp_path / "config.yaml").write_text(
        'distill:\n  prompt_bank: "data/prompts/training_prompts.jsonl"\n',
        encoding="utf-8",
    )
    with pytest.raises(PreflightError, match="prompt bank"):
        ensure_prompt_bank(tmp_path)


def test_ensure_dashboard_data_paths_creates_jsonl_and_symlink(tmp_path: Path) -> None:
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        "distill:\n  out_dir: data/distilled\n  out_file: responses.jsonl\n",
        encoding="utf-8",
    )
    ensure_dashboard_data_paths(tmp_path)
    jsonl_path = tmp_path / "data" / "distilled" / "responses.jsonl"
    public_jsonl = tmp_path / "dashboard" / "public" / "responses.jsonl"
    assert jsonl_path.is_file()
    assert public_jsonl.exists()
    assert public_jsonl.stat().st_size >= 0
    if public_jsonl.is_symlink():
        assert public_jsonl.resolve() == jsonl_path.resolve()
    elif platform.system() != "Windows":
        pytest.fail("expected symlink on non-Windows platform")


def test_ensure_dashboard_data_paths_refreshes_stale_empty_public_jsonl(tmp_path: Path) -> None:
    (tmp_path / "config.yaml").write_text(
        "distill:\n  out_dir: data/distilled\n  out_file: responses.jsonl\n",
        encoding="utf-8",
    )
    src = tmp_path / "data" / "distilled" / "responses.jsonl"
    src.parent.mkdir(parents=True)
    src.write_text('{"prompt":"p"}\n', encoding="utf-8")
    public_jsonl = tmp_path / "dashboard" / "public" / "responses.jsonl"
    public_jsonl.parent.mkdir(parents=True)
    public_jsonl.write_text("", encoding="utf-8")

    ensure_dashboard_data_paths(tmp_path)

    assert public_jsonl.stat().st_size > 0


def test_jsonl_has_content(tmp_path: Path) -> None:
    empty = tmp_path / "empty.jsonl"
    empty.write_text("\n\n", encoding="utf-8")
    assert jsonl_has_content(empty) is False

    filled = tmp_path / "filled.jsonl"
    filled.write_text('{"prompt":"x"}\n', encoding="utf-8")
    assert jsonl_has_content(filled) is True


def test_ensure_stats_json_skips_empty(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "config.yaml").write_text(
        "distill:\n  out_dir: data/distilled\n  out_file: responses.jsonl\n",
        encoding="utf-8",
    )
    (tmp_path / "data" / "distilled").mkdir(parents=True)
    (tmp_path / "data" / "distilled" / "responses.jsonl").touch()
    calls: list[list[str]] = []

    def fake_stats(argv: list[str] | None = None) -> int:
        calls.append(list(argv or []))
        return 0

    monkeypatch.setattr("joryu.cli.stats.main", fake_stats)
    assert ensure_stats_json(tmp_path) is None
    assert calls == []


def test_ensure_stats_json_runs_when_content(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "config.yaml").write_text(
        "distill:\n  out_dir: data/distilled\n  out_file: responses.jsonl\n",
        encoding="utf-8",
    )
    jsonl = tmp_path / "data" / "distilled" / "responses.jsonl"
    jsonl.parent.mkdir(parents=True)
    jsonl.write_text('{"prompt":"P","answer":"A"}\n', encoding="utf-8")
    (tmp_path / "dashboard" / "public").mkdir(parents=True)
    calls: list[list[str]] = []

    def fake_stats(argv: list[str] | None = None) -> int:
        calls.append(list(argv or []))
        return 0

    monkeypatch.setattr("joryu.cli.stats.main", fake_stats)
    rc = ensure_stats_json(tmp_path)
    assert rc == 0
    assert len(calls) == 1


def test_curation_needs_refresh_when_missing(tmp_path: Path) -> None:
    (tmp_path / "config.yaml").write_text(
        "distill:\n  out_dir: data/distilled\n  out_file: responses.jsonl\n",
        encoding="utf-8",
    )
    jsonl = tmp_path / "data" / "distilled" / "responses.jsonl"
    jsonl.parent.mkdir(parents=True)
    jsonl.write_text('{"prompt":"P","answer":"A"}\n', encoding="utf-8")
    assert curation_needs_refresh(tmp_path) is True


def test_ensure_curation_skips_when_fresh(tmp_path: Path, monkeypatch) -> None:
    import os

    (tmp_path / "config.yaml").write_text(
        "distill:\n  out_dir: data/distilled\n  out_file: responses.jsonl\n",
        encoding="utf-8",
    )
    jsonl = tmp_path / "data" / "distilled" / "responses.jsonl"
    jsonl.parent.mkdir(parents=True)
    jsonl.write_text('{"prompt":"P","answer":"A"}\n', encoding="utf-8")
    curation = tmp_path / "dashboard" / "public" / "curation.json"
    curation.parent.mkdir(parents=True)
    curation.write_text("{}", encoding="utf-8")
    os.utime(curation, (jsonl.stat().st_mtime + 10, jsonl.stat().st_mtime + 10))

    def fail_curate(*args, **kwargs) -> int:
        raise AssertionError("should not run")

    monkeypatch.setattr("joryu.cli.curate.main", fail_curate)
    assert ensure_curation(tmp_path, ["dashboard", "api"]) is None


def test_ensure_curation_runs_with_skip_llm(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "config.yaml").write_text(
        "distill:\n  out_dir: data/distilled\n  out_file: responses.jsonl\n",
        encoding="utf-8",
    )
    jsonl = tmp_path / "data" / "distilled" / "responses.jsonl"
    jsonl.parent.mkdir(parents=True)
    jsonl.write_text('{"prompt":"P","answer":"A"}\n', encoding="utf-8")
    calls: list[list[str]] = []

    def fake_curate(argv: list[str] | None = None) -> int:
        calls.append(list(argv or []))
        return 0

    monkeypatch.setattr("joryu.cli.curate.main", fake_curate)
    monkeypatch.setattr("joryu.preflight.joryu_container_running", lambda **_: False)
    rc = ensure_curation(tmp_path, ["dashboard", "api"])
    assert rc == 0
    assert calls == [["--config", "config.yaml", "--skip-llm"]]


def test_vllm_limits_probe_needed_for_api_without_limits(tmp_path: Path) -> None:
    (tmp_path / "config.yaml").write_text(
        "model:\n  limits_probe_file: data/vllm_limits.json\n",
        encoding="utf-8",
    )
    assert vllm_limits_probe_needed(tmp_path, up_services=["dashboard", "api"]) is True


def test_vllm_limits_probe_needed_skips_frontend_only(tmp_path: Path) -> None:
    assert vllm_limits_probe_needed(tmp_path, up_services=["dashboard"]) is False


def test_vllm_limits_probe_needed_skips_fresh_limits(tmp_path: Path) -> None:
    from joryu.config import Config
    from joryu.vllm_limits import VllmLimits, vllm_config_fingerprint, write_probe_limits

    cfg_yaml = "model:\n  limits_probe_file: data/vllm_limits.json\n"
    (tmp_path / "config.yaml").write_text(cfg_yaml, encoding="utf-8")
    cfg = Config()
    limits_path = resolve_vllm_limits_path(tmp_path)
    write_probe_limits(
        limits_path,
        VllmLimits(num_ctx=1024, num_predict=640),
        extra={"config_fingerprint": vllm_config_fingerprint(cfg)},
    )
    assert vllm_limits_probe_needed(tmp_path, up_services=["dashboard", "api"]) is False


def test_vllm_limits_probe_needed_joryu_built_skips_when_daemon_up_and_fresh(
    tmp_path: Path,
) -> None:
    from joryu.config import Config
    from joryu.vllm_limits import VllmLimits, vllm_config_fingerprint, write_probe_limits

    cfg_yaml = "model:\n  limits_probe_file: data/vllm_limits.json\n"
    (tmp_path / "config.yaml").write_text(cfg_yaml, encoding="utf-8")
    cfg = Config()
    write_probe_limits(
        resolve_vllm_limits_path(tmp_path),
        VllmLimits(num_ctx=1024, num_predict=640),
        extra={"config_fingerprint": vllm_config_fingerprint(cfg)},
    )
    assert (
        vllm_limits_probe_needed(
            tmp_path,
            up_services=["dashboard", "api", "joryu"],
            joryu_built=True,
        )
        is False
    )


def test_vllm_limits_probe_needed_joryu_built_still_probes_api_only(
    tmp_path: Path,
) -> None:
    from joryu.config import Config
    from joryu.vllm_limits import VllmLimits, vllm_config_fingerprint, write_probe_limits

    cfg_yaml = "model:\n  limits_probe_file: data/vllm_limits.json\n"
    (tmp_path / "config.yaml").write_text(cfg_yaml, encoding="utf-8")
    cfg = Config()
    write_probe_limits(
        resolve_vllm_limits_path(tmp_path),
        VllmLimits(num_ctx=1024, num_predict=640),
        extra={"config_fingerprint": vllm_config_fingerprint(cfg)},
    )
    assert (
        vllm_limits_probe_needed(
            tmp_path,
            up_services=["dashboard", "api"],
            joryu_built=True,
        )
        is True
    )


def test_ensure_curation_skips_llm_when_joryu_in_up_services(
    tmp_path: Path,
    monkeypatch,
) -> None:
    (tmp_path / "config.yaml").write_text(
        "distill:\n  out_dir: data/distilled\n  out_file: responses.jsonl\n",
        encoding="utf-8",
    )
    jsonl = tmp_path / "data" / "distilled" / "responses.jsonl"
    jsonl.parent.mkdir(parents=True)
    jsonl.write_text('{"prompt":"P","answer":"A"}\n', encoding="utf-8")
    calls: list[list[str]] = []

    def fake_curate(argv: list[str] | None = None) -> int:
        calls.append(list(argv or []))
        return 0

    monkeypatch.setattr("joryu.cli.curate.main", fake_curate)
    monkeypatch.setattr("joryu.preflight.joryu_container_running", lambda **_: True)
    rc = ensure_curation(tmp_path, ["dashboard", "api", "joryu"])
    assert rc == 0
    assert calls == [["--config", "config.yaml", "--skip-llm"]]


def test_stop_joryu_for_up_noop_when_not_running(monkeypatch) -> None:
    calls: list[list[str]] = []

    def fake_run(cmd: list[str], **_kwargs: object) -> _InspectResult:
        calls.append(cmd)
        return _InspectResult()

    monkeypatch.setattr("joryu.preflight.joryu_container_running", lambda **_: False)
    stop_joryu_for_up(docker_run=fake_run)
    assert calls == []


def test_stop_joryu_for_up_stops_running_container(monkeypatch) -> None:
    calls: list[list[str]] = []

    def fake_run(cmd: list[str], **_kwargs: object) -> _InspectResult:
        calls.append(cmd)
        return _InspectResult()

    monkeypatch.setattr("joryu.preflight.joryu_container_running", lambda **_: True)
    stop_joryu_for_up(docker_run=fake_run)
    assert calls == [["docker", "stop", "--time", "30", "joryu"]]


def test_ensure_vllm_limits_runs_probe_when_needed(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "config.yaml").write_text(
        "model:\n  limits_probe_file: data/vllm_limits.json\n",
        encoding="utf-8",
    )
    calls: list[str] = []

    def fake_probe(**kwargs) -> int:
        calls.append(str(kwargs.get("config")))
        return 0

    monkeypatch.setattr("joryu.vllm_probe.run_vllm_probe", fake_probe)
    monkeypatch.setattr("joryu.preflight.docker_image_exists", lambda *_args, **_kwargs: True)
    rc = ensure_vllm_limits(tmp_path, up_services=["dashboard", "api"])
    assert rc == 0
    assert len(calls) == 1


def test_should_force_recreate_when_joryu_runtime_changed() -> None:
    assert should_force_recreate(
        ["dashboard", "api"],
        {"joryu"},
        [],
        first_run=False,
    )


def test_should_force_recreate_skips_dashboard_only_change() -> None:
    assert not should_force_recreate(
        ["dashboard", "api"],
        {"dashboard"},
        [],
        first_run=False,
    )


def test_ensure_vllm_limits_skips_when_fresh(tmp_path: Path, monkeypatch) -> None:
    from joryu.config import Config
    from joryu.vllm_limits import VllmLimits, vllm_config_fingerprint, write_probe_limits

    cfg_yaml = "model:\n  limits_probe_file: data/vllm_limits.json\n"
    (tmp_path / "config.yaml").write_text(cfg_yaml, encoding="utf-8")
    cfg = Config()
    write_probe_limits(
        resolve_vllm_limits_path(tmp_path),
        VllmLimits(num_ctx=1024, num_predict=640),
        extra={"config_fingerprint": vllm_config_fingerprint(cfg)},
    )

    def fail_probe(**kwargs) -> int:
        raise AssertionError("should not run")

    monkeypatch.setattr("joryu.vllm_probe.run_vllm_probe", fail_probe)
    assert ensure_vllm_limits(tmp_path, up_services=["dashboard", "api"]) is None


class _GitResult:
    def __init__(self, stdout: str = "", returncode: int = 0) -> None:
        self.stdout = stdout
        self.returncode = returncode


class _InspectResult:
    def __init__(self, returncode: int = 0) -> None:
        self.returncode = returncode
