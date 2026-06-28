# joryu-vllm-base ビルド観測ノート

このファイルは `joryu-vllm-base:latest` (vLLM コンパイル済みベースイメージ) のビルドが何度も時間切れ／クラッシュする問題を可視化するための**クラッシュ耐性ある作業ノート**である。

各試行・各ボトルネック仮説を時系列で追記し、中断後でも続きから再開できるようにする。

## 現状サマリ

- リポジトリ: `c:/qwen3-swallow-8B-RL-v0.2-AWQ-INT4-joryu-pipline`
- ブランチ: `fix/joryu-up-vllm-base` (PR #329)
- 最新コミット: `dc9d6dc` (limit vLLM compile parallelism)
- ホスト: Windows 11, 12 論理 CPU, 32 GB RAM
- WSL2: `memory=24GB`, `processors=8`
- Docker Desktop: `memory: 24576`, `cpus: 4`, `diskSizeMiB: 102400`
- GPU: RTX 3060 Ti (Compute Capability **8.6**)

## 試行履歴

### 試行 1 (UTC 2026-06-28 04:30〜) — MAX_JOBS=1 ナイーブ並列無し

- Dockerfile: `MAX_JOBS=1`, `NVCC_THREADS=1`, `CMAKE_BUILD_PARALLEL_LEVEL=1`, `TORCH_CUDA_ARCH_LIST` 未設定
- 経過: `#22` torch インストール 48.1s で完了 → `#23 Building vllm @ v0.23.1rc0` で **2 時間以上 hang**
- 中断: ユーザー判断でキャンセル + `docker buildx prune -af`
- 観測:
  - `docker buildx du` で mutable mount アクティブ (実際に何かは動いている)
  - だが進捗ログは `Building vllm @ ...` の 1 行のみ
  - `--progress=plain` 未指定で `setup.py` の出力が完全に隠蔽されていた
- 結論: **直列ビルド + 全 arch + ログ隠蔽** の三重苦で実用不可

### 試行 2 (UTC 2026-06-28 07:04〜) — MAX_JOBS=4 + SM_86 + plain + ccache + verbose

- Dockerfile: `MAX_JOBS=4`, `NVCC_THREADS=2`, `CMAKE_BUILD_PARALLEL_LEVEL=4`, `TORCH_CUDA_ARCH_LIST="8.6"`, `ccache` cache mount, vLLM `-v`
- ビルドコマンド: `bash scripts/build-vllm-base.sh` (`--progress=plain` + tee)
- ログ: `data/logs/build-vllm-base-20260628T070413Z.log` (18 KB で停止)
- 経過:
  - `#1`〜`#21` (build context + apt install + builder uv sync) すべて完走 (合計 ~15 秒)
  - `#22 COPY /usr/local`, `#23 COPY /app` 1 秒台で完走
  - `#24 [stage-1 6/7] RUN uv pip install torch>=2.12.1` で **16 分 hang**
- 観測:
  - `--progress=plain` の効果で stage の遷移は完全に見える (試行 1 比で大改善)
  - bash プロセスは alive、Docker daemon も応答する
  - `docker buildx du` のキャッシュ進行は torch DL 開始位置で停滞
  - 試行 1 では同じ `#22` torch を 48.1s で完了していた → **本来であれば速い箇所**
- 仮説:
  - Docker Desktop の HTTP プロキシ／WSL2 メモリ枯渇による torch wheel (約 2.5 GB) のダウンロード hang
  - WSL2 24GB のうち builder stage が大量に memory を消費している可能性
  - 試行 1 でこの位置を通過していたのは、もっと早いタイミングで Docker daemon が「元気」だったため
- 暫定対処計画:
  - **Docker Desktop と WSL2 を完全再起動** → builder layer がキャッシュ済みなので即 stage-1 から再開
  - 再開後すぐ `#24` (torch) と `#25` (vLLM) に入る想定
  - hang したら再度 md に追記し戦略変更 (e.g. torch を別 RUN で先に install して `--mount=type=cache` を温める)

## ボトルネック仮説と検証

| # | 仮説 | 裏付け | 対処 |
|---|------|--------|------|
| 1 | `MAX_JOBS=1` で nvcc 直列ビルド | vLLM は数百カーネルを生成。1 スレッドだと数時間〜数十時間 | `MAX_JOBS=4`, `NVCC_THREADS=2` に変更 (12 論理 CPU の半分以下) |
| 2 | `TORCH_CUDA_ARCH_LIST` 未指定で SM_70/75/80/86/89/90/100/120 全 arch をビルド | vLLM `setup.py` の既定挙動 | `ENV TORCH_CUDA_ARCH_LIST="8.6"` (RTX 3060 Ti 専用) |
| 3 | `--progress=plain` 未指定で進捗が見えない | 試行 1 で hang か進行中か判別不能 | `scripts/build-vllm-base.sh` で `--progress=plain` 強制、`tee` でログ保存 |
| 4 | CCACHE なしで失敗時に毎回ゼロから | 試行 1 を 3 回繰り返した | `ccache` を `apt install` し `CCACHE_DIR` を BuildKit cache mount |
| 5 | uv pip install のサブプロセス出力が見えない | `setup.py bdist_wheel` の中身が一切出力されない | `uv pip install -v` で setup.py stdout を見せる |

## なぜ以前より時間がかかるのか

| 以前 (`joryu:latest` 17GB) | 今 (`joryu-vllm-base` git ビルド) |
|---|---|
| PyPI の **事前コンパイル済み** `vllm==0.23.0` wheel を `pip install` するだけ | GitHub から vLLM ソースを取得し **337 個の CUDA/C++ ターゲットを nvcc でコンパイル** |
| 数分〜十数分 | 実測: コンパイル段階だけ **40〜90 分** (Docker CPU 4 割当) |
| ただし torch 2.12 との **ABI 不一致で ImportError** → 使えなかった | git ビルドは torch 2.12 と整合するが、初回だけ重い |

試行 1 の `MAX_JOBS=1` は nvcc を直列化し、さらに **2 時間+ hang** した。試行 3 では `MAX_JOBS=4` + `TORCH_CUDA_ARCH_LIST=8.6` で **`[110/337]` まで 40 分** — hang ではなく正常進行。

## なぜプロセスが勝手に終了したか

exit code `4294967295` (= `-1`) は **Docker ビルド失敗ではなく、親 shell の強制終了** を意味する。

主因:
1. **Cursor エージェントの background shell** — 長時間タスク中に新しいチャットや Await 中断で kill される
2. **試行 2** — torch ダウンロード hang 後、Docker 再起動のため意図的 kill
3. Docker Desktop の EOF クラッシュ (試行 1 以前)

対策: `bash scripts/build-vllm-base.sh --detach` で **nohup 切離** し、Cursor セッションから独立させる。進捗確認は `bash scripts/build-vllm-base.sh --status`。

**手動実行の推奨**: 1〜2 時間のビルドは **Windows Terminal / Git Bash を別ウィンドウで開き** `--detach` またはフォアグラウンド実行するのが最も確実。Cursor 内エージェント経由は監視用に `--status` のみ使う。

## WSL / Docker メモリ (29 GB)

- `.wslconfig`: `memory=29GB` (ユーザー更新済み)
- Docker Desktop `settings-store.json`: `linuxVM.memory` を **29696 MiB (29 GB)** に同期
- 反映手順: `wsl --shutdown` → Docker Desktop 再起動 → `wsl -e free -h` で確認

## 次のアクション

- [x] `--detach` / `--status` を `scripts/build-vllm-base.sh` に追加
- [x] WSL 29 GB + Docker memory 同期
- [ ] `bash scripts/build-vllm-base.sh --detach` でビルド再開 (BuildKit cache から `#23` 付近再開見込み)
- [ ] 完了後 `uv run joryu-up` → commit/push

## 試行 2 計画値 (実装中)

- `MAX_JOBS=4`
- `NVCC_THREADS=2`
- `CMAKE_BUILD_PARALLEL_LEVEL=4`
- `TORCH_CUDA_ARCH_LIST="8.6"` (RTX 3060 Ti 専用)
- `ccache` 同梱、`/root/.cache/ccache` を BuildKit cache mount (`id=joryu-ccache`)
- `uv pip install -v "vllm @ git+..."` (verbose 化)
- `docker build --progress=plain ...` を `scripts/build-vllm-base.sh` 経由で実行
- ログ: `data/logs/build-vllm-base-<UTC>.log` (`.gitignore` 済み `data/` 配下)

期待効果:
- 並列 4 → 試行 1 比 **4 倍速**
- arch 1 個のみ → 試行 1 比 **6〜8 倍速** (SM_70-120 のうち 1 つ)
- 合計で**理論上 24〜32 倍速**。1〜2 時間 → 数分〜十数分を期待
- 進捗ログがリアルタイムで見えるため hang か進行中か即判別可能
