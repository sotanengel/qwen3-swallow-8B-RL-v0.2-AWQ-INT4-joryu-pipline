"""joryu-up 実行前の git 差分検出とディスク preflight。"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

# Docker build に最低限欲しいホスト空き容量 (GB)。
# 過去は full from-scratch build を想定した保守的見積 (dashboard=5/api=2/joryu=25, 計32GB)
# だったが、既存 image が存在する rebuild 系では layer cache が効くため実消費はもっと小さい。
# - joryu image 実測: 21.7GB (full build), 増分 rebuild: 数GB
# - api/dashboard image: 0.2-0.8GB
# 「rebuild に最低限必要な C: 余裕」として現実値に寄せる。
# 初回 full build で足りない時は `--force` でスキップ可。
DISK_REQUIRED_GB: dict[str, float] = {
    "dashboard": 2.0,
    "api": 1.0,
    "joryu": 10.0,
}

_JORYU_PATHS = frozenset(
    {
        "Dockerfile",
        "Dockerfile.api",
        "pyproject.toml",
        "uv.lock",
        "config.yaml",
        "styles.yaml",
        "tools.yaml",
        "README.md",
        ".dockerignore",
    }
)
_JORYU_PREFIXES = ("src/", "scripts/")
_API_PREFIXES = ("src/joryu/api/", "src/joryu/jobs/")
# API ジョブ実行時に joryu コンテナへも載るモジュール (api + joryu 両方 rebuild)
_JORYU_JOB_RUNTIME_PATHS = frozenset(
    {
        "docker-compose.yml",
        "src/joryu/distill.py",
        "src/joryu/docker_delegate.py",
        "src/joryu/docker_runtime.py",
        "src/joryu/stats.py",
        "src/joryu/preflight.py",
        "src/joryu/paths.py",
        "src/joryu/vllm_client.py",
        "src/joryu/vllm_limits.py",
        "src/joryu/vllm_probe.py",
        "src/joryu/jobs/runner.py",
        "src/joryu/cli/distill.py",
        "src/joryu/cli/stats.py",
        "src/joryu/cli/probe_vllm.py",
    }
)
_DASHBOARD_PREFIX = "dashboard/"
_DASHBOARD_RUNTIME_PATHS = frozenset(
    {
        "dashboard/public/responses.jsonl",
        "dashboard/public/stats.json",
    }
)

_SERVICE_ORDER = ("dashboard", "api", "joryu")
_DEFAULT_UP = ("dashboard", "api")
_UP_STATE_REL = Path("data") / ".joryu" / "up-state.json"


class PreflightError(Exception):
    """preflight 失敗 (ディスク不足など)。"""


class _GitRunner(Protocol):
    def __call__(
        self,
        args: list[str],
        *,
        cwd: Path,
        capture_output: bool,
        text: bool,
        check: bool,
    ) -> subprocess.CompletedProcess[str]: ...


class _InspectRunner(Protocol):
    def __call__(
        self,
        args: list[str],
        *,
        capture_output: bool,
        text: bool,
        check: bool,
    ) -> subprocess.CompletedProcess[str]: ...


JORYU_JOB_IMAGE = "joryu:latest"


def docker_image_exists(
    image: str,
    *,
    inspect_runner: _InspectRunner | None = None,
) -> bool:
    """ローカルに Docker イメージが存在するか。"""
    runner = inspect_runner or subprocess.run
    result = runner(
        ["docker", "image", "inspect", image],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0


def path_affects_service(path: str) -> set[str]:
    """build context 上、変更パスが影響する compose サービス名を返す。"""
    normalized = path.replace("\\", "/")
    if normalized in _DASHBOARD_RUNTIME_PATHS:
        return set()
    if normalized.startswith(_API_PREFIXES) or normalized == "Dockerfile.api":
        return {"api"}
    if normalized in _JORYU_JOB_RUNTIME_PATHS:
        return {"api", "joryu"}
    if normalized.startswith(_DASHBOARD_PREFIX):
        return {"dashboard"}
    if normalized in _JORYU_PATHS or normalized.startswith(_JORYU_PREFIXES):
        return {"joryu"}
    return set()


def _git_lines(repo_root: Path, args: list[str], git_runner: _GitRunner) -> list[str]:
    result = git_runner(
        args,
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return []
    return [line for line in result.stdout.splitlines() if line.strip()]


def up_state_path(repo_root: Path) -> Path:
    return repo_root / _UP_STATE_REL


def load_up_state(repo_root: Path) -> dict[str, Any] | None:
    path = up_state_path(repo_root)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if isinstance(data, dict) and isinstance(data.get("git_head"), str):
        return data
    return None


def save_up_state(
    repo_root: Path,
    git_head: str,
    *,
    built_services: list[str] | None = None,
) -> None:
    path = up_state_path(repo_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    prev = load_up_state(repo_root) or {}
    payload: dict[str, Any] = {"git_head": git_head}
    built: dict[str, str] = dict(prev.get("built_services") or {})
    if built_services:
        for svc in built_services:
            built[svc] = git_head
    if built:
        payload["built_services"] = built
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def services_missing_build_at_head(
    up_services: list[str],
    repo_root: Path,
    *,
    git_runner: _GitRunner | None = None,
) -> set[str]:
    """up 対象のうち、現在 HEAD で docker build されていないサービス。"""
    head = git_head_at(repo_root, git_runner=git_runner)
    if not head:
        return set()
    state = load_up_state(repo_root)
    built: dict[str, str] = dict((state or {}).get("built_services") or {})
    return {svc for svc in up_services if built.get(svc) != head}


def git_head_at(repo_root: Path, *, git_runner: _GitRunner | None = None) -> str | None:
    runner = git_runner or subprocess.run
    lines = _git_lines(repo_root, ["git", "rev-parse", "HEAD"], runner)
    return lines[0] if lines else None


def _paths_from_working_tree(repo_root: Path, git_runner: _GitRunner) -> set[str]:
    paths: set[str] = set()
    paths.update(_git_lines(repo_root, ["git", "diff", "--name-only", "HEAD"], git_runner))
    paths.update(_git_lines(repo_root, ["git", "diff", "--name-only", "--cached"], git_runner))
    paths.update(
        _git_lines(
            repo_root,
            ["git", "ls-files", "--others", "--exclude-standard"],
            git_runner,
        )
    )
    return paths


def _paths_since_last_up(
    repo_root: Path,
    *,
    git_runner: _GitRunner,
    state: dict[str, Any] | None,
    head: str | None,
) -> set[str]:
    if not state or not head:
        return set()
    last_head = state["git_head"]
    if last_head == head:
        return set()
    return set(
        _git_lines(
            repo_root,
            ["git", "diff", "--name-only", f"{last_head}..{head}"],
            git_runner,
        )
    )


def changed_services_from_git(
    repo_root: Path,
    *,
    git_runner: _GitRunner | None = None,
) -> set[str]:
    """rebuild が必要なサービスを返す。

    未コミットの作業ツリー差分に加え、前回 ``joryu-up`` 成功時の HEAD から
    現在の HEAD までに入ったコミット（``git pull`` 後など）も対象にする。
    """
    runner = git_runner or subprocess.run
    head = git_head_at(repo_root, git_runner=runner)
    state = load_up_state(repo_root)
    paths = _paths_from_working_tree(repo_root, runner)
    paths.update(_paths_since_last_up(repo_root, git_runner=runner, state=state, head=head))

    services: set[str] = set()
    for path in paths:
        services.update(path_affects_service(path))
    return services


def is_first_up_run(repo_root: Path) -> bool:
    """前回成功した joryu-up の記録が無い。"""
    return load_up_state(repo_root) is None


def resolve_up_services(args: argparse.Namespace, changed: set[str]) -> list[str]:
    """CLI フラグから `docker compose up` 対象サービスを決定。

    git 差分 (`changed`) は build 対象の判定にのみ使う。既定モードでは常に
    dashboard + api を起動する。
    """
    del changed  # build 判定は services_to_build 側
    if args.full:
        return list(_SERVICE_ORDER)
    if args.backend_only:
        return ["joryu"]
    if args.frontend_only:
        return ["dashboard"]
    return list(_DEFAULT_UP)


def services_to_build(
    up_services: list[str],
    changed: set[str],
    *,
    no_build: bool,
    force_build: bool = False,
    first_run: bool = False,
    repo_root: Path | None = None,
    inspect_runner: _InspectRunner | None = None,
) -> list[str]:
    """`up` 対象のうち rebuild が必要なサービスだけ build する。"""
    if no_build:
        return []
    if force_build:
        candidates = list(up_services)
    elif first_run:
        candidates = list(up_services)
    else:
        stale: set[str] = set()
        if repo_root is not None:
            stale = services_missing_build_at_head(up_services, repo_root)
        candidates = [svc for svc in up_services if svc in changed or svc in stale]

    # api を up する = ジョブが joryu:latest を docker run する。
    if "api" in up_services and "joryu" not in candidates:
        needs_joryu = (
            "joryu" in changed
            or first_run
            or force_build
            or not docker_image_exists(JORYU_JOB_IMAGE, inspect_runner=inspect_runner)
        )
        if needs_joryu:
            candidates.append("joryu")

    return [svc for svc in _SERVICE_ORDER if svc in candidates]


def should_force_recreate(
    up_services: list[str],
    changed: set[str],
    build_services: list[str],
    *,
    first_run: bool,
) -> bool:
    """compose up で `--force-recreate` が必要か。

    api コンテナは uvicorn プロセスが Python モジュールをキャッシュするため、
    ジョブランナー (api) や蒸留ジョブ (joryu) のランタイム差分では再起動が必要。
    イメージ rebuild 時も再作成する。
    """
    if first_run or build_services:
        return True
    if "api" in up_services and ("api" in changed or "joryu" in changed):
        return True
    return False


def required_disk_gb(services: list[str]) -> float:
    """ビルド対象サービスに必要なホスト空き容量 (GB)。"""
    return sum(DISK_REQUIRED_GB[svc] for svc in services)


def check_disk_space(
    services: list[str],
    repo_root: Path,
    *,
    force: bool,
    disk_usage_fn: Callable[[Path], tuple[int, int, int]] | None = None,
) -> None:
    """空き容量不足なら PreflightError。force=True ならスキップ。"""
    if force or not services:
        return

    usage = (disk_usage_fn or shutil.disk_usage)(repo_root)
    free_gb = usage[2] / (1024**3)
    need_gb = required_disk_gb(services)

    if free_gb >= need_gb:
        return

    service_list = ", ".join(services)
    msg = (
        f"[joryu-up] 空き容量不足: {free_gb:.1f} GB 空き / {need_gb:.0f} GB 必要 ({service_list})\n"
        "  Docker Desktop の Disk image size を確認するか、"
        "`docker system prune -af` で不要イメージを削除してください。\n"
        "  容量不足を承知で続行する場合は `--force` を付けて再実行してください。"
    )
    raise PreflightError(msg)


_DEFAULT_PROMPT_CSV_REL = Path("../make-japan-ai-great-again/src/mjaga/data/training_prompts.csv")
_DEFAULT_PROMPT_BANK_SEED_REL = Path("scripts/seeds/training_prompts.jsonl")
_DEFAULT_PROMPT_BANK_SEED_ZST_REL = Path("scripts/seeds/training_prompts.jsonl.zst")


def _resolve_existing_path(repo_root: Path, candidates: list[Path]) -> Path | None:
    for raw in candidates:
        path = raw if raw.is_absolute() else (repo_root / raw)
        resolved = path.resolve()
        if resolved.is_file():
            return resolved
    return None


def resolve_prompt_bank_seed_path(repo_root: Path, cfg: Any) -> Path | None:
    """prompt bank コピー元 JSONL のパスを解決する。見つからなければ None。"""
    candidates: list[Path] = []
    seed = getattr(cfg.distill, "prompt_bank_seed", "")
    if isinstance(seed, str) and seed.strip():
        candidates.append(Path(seed.strip()))
    env_seed = os.environ.get("JORYU_PROMPT_BANK_SEED", "").strip()
    if env_seed:
        candidates.append(Path(env_seed))
    candidates.append(_DEFAULT_PROMPT_BANK_SEED_REL)
    candidates.append(_DEFAULT_PROMPT_BANK_SEED_ZST_REL)
    return _resolve_existing_path(repo_root, candidates)


def _materialize_prompt_bank_from_seed(seed: Path, bank_path: Path) -> None:
    bank_path.parent.mkdir(parents=True, exist_ok=True)
    if seed.suffix == ".zst":
        import zstandard as zstd

        data = zstd.ZstdDecompressor().decompress(seed.read_bytes())
        bank_path.write_bytes(data)
        return
    shutil.copy2(seed, bank_path)


def resolve_prompt_csv_path(repo_root: Path, cfg: Any) -> Path | None:
    """prompt bank 生成元 CSV のパスを解決する。見つからなければ None。"""
    candidates: list[Path] = []
    prompt_csv = getattr(cfg.distill, "prompt_csv", "")
    if isinstance(prompt_csv, str) and prompt_csv.strip():
        candidates.append(Path(prompt_csv.strip()))
    env_csv = os.environ.get("JORYU_PROMPT_CSV", "").strip()
    if env_csv:
        candidates.append(Path(env_csv))
    candidates.append(_DEFAULT_PROMPT_CSV_REL)
    return _resolve_existing_path(repo_root, candidates)


def _emit_preflight_log(message: str, log: Callable[[str], None] | None) -> None:
    if log is not None:
        log(message)
        return
    import sys

    print(message, file=sys.stderr)


def ensure_prompt_bank(
    repo_root: Path,
    *,
    log: Callable[[str], None] | None = None,
) -> None:
    """prompt bank JSONL が無ければ seed JSONL のコピーまたは CSV 変換で用意する。"""
    from joryu.migrate import csv_to_jsonl
    from joryu.paths import DEFAULT_CONFIG, resolve_optional_config

    cfg = resolve_optional_config(repo_root / DEFAULT_CONFIG)
    bank_path = (repo_root / cfg.distill.prompt_bank).resolve()
    if bank_path.is_file():
        return

    seed = resolve_prompt_bank_seed_path(repo_root, cfg)
    if seed is not None:
        _materialize_prompt_bank_from_seed(seed, bank_path)
        _emit_preflight_log(f"[joryu-up] prompt bank copied from {seed}", log)
        return

    src = resolve_prompt_csv_path(repo_root, cfg)
    if src is None:
        raise PreflightError(
            f"[joryu-up] prompt bank が見つかりません: {cfg.distill.prompt_bank}\n"
            "  scripts/seeds/training_prompts.jsonl を配置するか、"
            "config.yaml の distill.prompt_csv / distill.prompt_bank_seed を設定してください。\n"
            "  手動生成: uv run python scripts/migrate_csv_to_jsonl.py "
            f"--src <csv> --dst {cfg.distill.prompt_bank}"
        )

    n = csv_to_jsonl(src, bank_path)
    _emit_preflight_log(f"[joryu-up] prompt bank: {n} rows from {src}", log)


def resolve_distill_jsonl(repo_root: Path) -> Path:
    """config から蒸留 JSONL の絶対パスを返す。"""
    from joryu.paths import DEFAULT_CONFIG, resolve_optional_config

    cfg = resolve_optional_config(repo_root / DEFAULT_CONFIG)
    return repo_root / cfg.distill.out_dir / cfg.distill.out_file


def jsonl_has_content(path: Path) -> bool:
    """JSONL に非空行が 1 行以上あるか。"""
    if not path.is_file():
        return False
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                return True
    return False


def ensure_stats_json(
    repo_root: Path,
    *,
    force: bool = False,
    log: Callable[[str], None] | None = None,
) -> int | None:
    """responses.jsonl から stats.json を更新する。スキップ時は None。"""
    from joryu.cli.stats import main as stats_main
    from joryu.paths import DEFAULT_CONFIG, resolve_stats_output_path

    jsonl = resolve_distill_jsonl(repo_root)
    if not force and not jsonl_has_content(jsonl):
        return None
    out = resolve_stats_output_path(repo_root=repo_root)
    if out is None:
        return None
    cfg = repo_root / DEFAULT_CONFIG
    _emit_preflight_log(f"[joryu-up] refreshing stats.json from {jsonl}", log)
    return stats_main(["--config", str(cfg), "--output", str(out)])


def curation_needs_refresh(repo_root: Path) -> bool:
    """curation.json が未生成または蒸留 JSONL より古いか。"""
    from joryu.paths import CURATION_JSON_REL

    jsonl = resolve_distill_jsonl(repo_root)
    if not jsonl_has_content(jsonl):
        return False
    curation = repo_root / CURATION_JSON_REL
    if not curation.is_file():
        return True
    return curation.stat().st_mtime < jsonl.stat().st_mtime


def joryu_container_running(*, docker_run: _InspectRunner | None = None) -> bool:
    """joryu コンテナが起動中か。"""
    runner = docker_run or subprocess.run
    try:
        proc = runner(
            ["docker", "inspect", "-f", "{{.State.Running}}", "joryu"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return False
    return proc.returncode == 0 and proc.stdout.strip() == "true"


def ensure_curation(
    repo_root: Path,
    up_services: list[str],
    *,
    log: Callable[[str], None] | None = None,
) -> int | None:
    """curation.json が必要なら joryu-curate を同期実行。スキップ時は None。"""
    if not curation_needs_refresh(repo_root):
        return None

    from joryu.cli.curate import main as curate_main
    from joryu.paths import DEFAULT_CONFIG

    use_llm = "joryu" in up_services and joryu_container_running()
    argv = ["--config", DEFAULT_CONFIG]
    if not use_llm:
        argv.append("--skip-llm")
        _emit_preflight_log("[joryu-up] joryu-curate (--skip-llm: vLLM 未起動)", log)
    else:
        _emit_preflight_log("[joryu-up] joryu-curate (LLM judge)", log)
    return curate_main(argv)


def resolve_vllm_limits_path(repo_root: Path) -> Path:
    """config.model.limits_probe_file の絶対パスを返す。"""
    from joryu.paths import DEFAULT_CONFIG, resolve_limits_probe_path, resolve_optional_config

    cfg = resolve_optional_config(repo_root / DEFAULT_CONFIG)
    return resolve_limits_probe_path(cfg.model.limits_probe_file, repo_root=repo_root)


def vllm_limits_probe_needed(
    repo_root: Path,
    *,
    up_services: list[str],
    joryu_built: bool = False,
    force: bool = False,
) -> bool:
    """VRAM プローブが必要か。api/joryu を up する場合に limits 未作成・古い・joryu rebuild 時。"""
    if force:
        return True
    if "api" not in up_services and "joryu" not in up_services:
        return False
    from joryu.paths import DEFAULT_CONFIG, resolve_optional_config
    from joryu.vllm_limits import limits_probe_stale, vllm_config_fingerprint

    limits_path = resolve_vllm_limits_path(repo_root)
    if not limits_path.is_file():
        return True
    if joryu_built:
        return True
    cfg = resolve_optional_config(repo_root / DEFAULT_CONFIG)
    return limits_probe_stale(limits_path, vllm_config_fingerprint(cfg))


def ensure_vllm_limits(
    repo_root: Path,
    *,
    up_services: list[str],
    joryu_built: bool = False,
    force: bool = False,
    log: Callable[[str], None] | None = None,
) -> int | None:
    """GPU 蒸留ジョブ向けに vLLM VRAM 上限をプローブ。不要時は None。"""
    if not vllm_limits_probe_needed(
        repo_root,
        up_services=up_services,
        joryu_built=joryu_built,
        force=force,
    ):
        return None

    if not docker_image_exists(JORYU_JOB_IMAGE):
        raise PreflightError(
            "[joryu-up] joryu:latest が見つかりません。"
            " VRAM プローブの前に joryu イメージを build してください。"
        )

    from joryu.paths import DEFAULT_CONFIG
    from joryu.vllm_probe import run_vllm_probe

    _emit_preflight_log("[joryu-up] joryu-probe-vllm (GPU VRAM 上限)", log)
    rc = run_vllm_probe(config=DEFAULT_CONFIG)
    if rc != 0:
        raise PreflightError(
            "[joryu-up] joryu-probe-vllm が失敗しました。\n"
            "  手動: uv run joryu-probe-vllm\n"
            "  または data/vllm_limits.json を配置してください。"
        )
    return rc


def ensure_dashboard_data_paths(repo_root: Path) -> None:
    """蒸留 JSONL を dashboard から参照できるようディレクトリと symlink を整備する。"""
    from joryu.paths import DEFAULT_CONFIG, dashboard_public, resolve_optional_config

    cfg = resolve_optional_config(repo_root / DEFAULT_CONFIG)

    distilled_dir = repo_root / cfg.distill.out_dir
    distilled_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = distilled_dir / cfg.distill.out_file
    if not jsonl_path.exists():
        jsonl_path.touch()

    public_dir = dashboard_public(repo_root)
    public_jsonl = public_dir / cfg.distill.out_file

    if public_jsonl.exists() or public_jsonl.is_symlink():
        return

    try:
        public_jsonl.symlink_to(jsonl_path.resolve(), target_is_directory=False)
    except OSError:
        try:
            rel = Path(os.path.relpath(jsonl_path.resolve(), public_dir))
            public_jsonl.symlink_to(rel, target_is_directory=False)
        except OSError:
            pass
