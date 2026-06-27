# 健全性スクリーニング 閾値キャリブレーション

Epic #305 / 要件定義書 §6.2 / §10 に基づく運用フロー。

## 初回キャリブレーション (200〜500 件)

1. `joryu-curate --screening` を 200〜500 件で実行
2. `screening.review.jsonl` を人手レビューキューに投入
3. レビュアは各レコードを **OK / NG 二択** で正解ラベル付け (CSV または JSONL)
4. `scripts/calibrate_thresholds.py` で推奨閾値を算出
5. `config.yaml` の `curate.screening.thresholds` を更新
6. 全件またはサブセットで再評価

## 正解ラベル形式 (JSONL)

```json
{"record_hash": "abc...", "label": "OK"}
{"record_hash": "def...", "label": "NG"}
```

## 閾値チューニング

```bash
uv run python scripts/calibrate_thresholds.py \
  --scores data/curated/<run>/scores.jsonl \
  --labels data/review_labels.jsonl
```

出力例:

```json
{
  "recommended_ok_min": 0.72,
  "recommended_review_min": 0.38,
  "precision_at_ok": 0.91,
  "recall_at_ok": 0.88
}
```

## max_review_rate

`curate.screening.max_review_rate` (既定 0.3) を超える REVIEW 件数は、
低スコアの REVIEW から自動的に NG に降格される。

レビューキャパに応じて 0.1〜0.5 で調整する。

## 再キャリブレーション

- Judge モデルを変更した場合は **閾値を必ず再キャリブレーション** (スコアスケールが変わる)
- ドメイン構成が大きく変わった場合も 200 件程度で再確認

## 50 件 smoke test

```bash
JORYU_CURATE_FAKE_JUDGE=1 uv run joryu-curate --screening --count 50 --no-resume ...
uv run python scripts/calibrate_thresholds.py --scores ... --labels ... --smoke
```
