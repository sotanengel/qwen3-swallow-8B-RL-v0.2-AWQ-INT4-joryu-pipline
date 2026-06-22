"""MinHash + LSH によるグローバル重複判定 + 永続化 (R-24)。

設計:
- 1 ラン目: 入力レコード全てを MinHash 化し、LSH インデックスに insert。
  終了時に `data/curated/<run_id>/minhash.index` (pickle) として保存。
- 2 ラン目: 既存インデックスをロード → 新規レコードのみ `query → insert`。
  既存レコード × 新規レコードのペアは新規側だけ評価し、重複なら新規を棄却。

datasketch を optional dependency として扱い、未インストール時は SHA1 完全一致に
フォールバックする (CI が小さいうちは依存膨張を避けるため)。
"""

from __future__ import annotations

import hashlib
import logging
import pickle
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

try:
    from datasketch import MinHash, MinHashLSH

    _DATASKETCH_AVAILABLE = True
except ImportError:  # pragma: no cover - optional dep
    MinHash = None  # type: ignore[assignment,misc]
    MinHashLSH = None  # type: ignore[assignment,misc]
    _DATASKETCH_AVAILABLE = False

DEFAULT_NUM_PERM = 128
DEFAULT_JACCARD_THRESHOLD = 0.9
DEFAULT_INDEX_FILENAME = "minhash.index"
MAX_INDEX_BYTES_DEFAULT = 1024 * 1024 * 1024  # 1GB


_TOKEN_PATTERN = re.compile(r"\w+", re.UNICODE)


def _shingles(text: str, k: int = 5) -> set[str]:
    """k-shingle (文字 5-gram) を返す。半角空白の連続は 1 つに圧縮。"""
    if not text:
        return set()
    normalized = re.sub(r"\s+", " ", text.strip())
    if len(normalized) < k:
        return {normalized}
    return {normalized[i : i + k] for i in range(len(normalized) - k + 1)}


@dataclass
class GlobalDuplicateIndex:
    """ラン跨ぎで永続化可能な重複インデックスの共通 API。

    `query_and_insert(record_hash, text)` で新規レコードを評価し、

    - 重複なら `(True, dup_record_hash)` を返して **insert はしない**
      (重複と判定されたレコードは棄却されるため index に入れない)
    - 非重複なら `(False, None)` を返して index に登録する
    """

    num_perm: int = DEFAULT_NUM_PERM
    threshold: float = DEFAULT_JACCARD_THRESHOLD
    _exact_hashes: set[str] = field(default_factory=set, init=False)
    _lsh: Any = field(default=None, init=False)
    _stored_minhashes: dict[str, Any] = field(default_factory=dict, init=False)
    backend: str = field(default="", init=False)

    def __post_init__(self) -> None:
        if _DATASKETCH_AVAILABLE:
            self._lsh = MinHashLSH(threshold=self.threshold, num_perm=self.num_perm)
            self.backend = "minhash"
        else:
            self._lsh = None
            self.backend = "sha1"

    def __len__(self) -> int:
        return len(self._exact_hashes)

    def query_and_insert(self, record_hash: str, text: str) -> tuple[bool, str | None]:
        """重複判定 + 非重複なら index へ追加。

        Returns:
            (is_duplicate, dup_with_record_hash)
        """
        if not text:
            return False, None
        exact_h = hashlib.sha1(text.encode("utf-8"), usedforsecurity=False).hexdigest()
        if exact_h in self._exact_hashes:
            return True, exact_h  # 完全一致

        if self.backend == "minhash" and self._lsh is not None:
            m = MinHash(num_perm=self.num_perm)
            for sh in _shingles(text):
                m.update(sh.encode("utf-8"))
            matches = self._lsh.query(m)
            if matches:
                return True, str(matches[0])
            self._lsh.insert(record_hash, m)
            self._stored_minhashes[record_hash] = m

        self._exact_hashes.add(exact_h)
        return False, None

    def to_bytes(self) -> bytes:
        """pickle 化して保存可能な bytes に。"""
        payload = {
            "version": 1,
            "backend": self.backend,
            "num_perm": self.num_perm,
            "threshold": self.threshold,
            "exact_hashes": list(self._exact_hashes),
            "minhashes": self._stored_minhashes if self.backend == "minhash" else None,
        }
        return pickle.dumps(payload, protocol=pickle.HIGHEST_PROTOCOL)

    @classmethod
    def from_bytes(cls, data: bytes) -> GlobalDuplicateIndex:
        """`to_bytes()` で書き出した state からロード。

        スキーマ違反 / backend 不一致は警告ログを出して空インデックスを返す。
        """
        try:
            payload = pickle.loads(data)  # noqa: S301 - 信頼できる自己生成データ
        except (pickle.UnpicklingError, EOFError, ValueError) as exc:
            logger.warning("[curate.minhash_index] failed to load: %s", exc)
            return cls()
        if not isinstance(payload, dict) or payload.get("version") != 1:
            logger.warning("[curate.minhash_index] unsupported index payload")
            return cls()

        idx = cls(
            num_perm=int(payload.get("num_perm", DEFAULT_NUM_PERM)),
            threshold=float(payload.get("threshold", DEFAULT_JACCARD_THRESHOLD)),
        )
        idx._exact_hashes = set(payload.get("exact_hashes") or [])
        if (
            idx.backend == "minhash"
            and payload.get("backend") == "minhash"
            and isinstance(payload.get("minhashes"), dict)
        ):
            for rh, m in payload["minhashes"].items():
                idx._lsh.insert(rh, m)
                idx._stored_minhashes[rh] = m
        return idx

    def save(self, path: str | Path) -> Path:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        data = self.to_bytes()
        if len(data) > MAX_INDEX_BYTES_DEFAULT:
            logger.warning(
                "[curate.minhash_index] index size %d bytes exceeds soft limit %d",
                len(data),
                MAX_INDEX_BYTES_DEFAULT,
            )
        p.write_bytes(data)
        return p

    @classmethod
    def load(
        cls,
        path: str | Path,
        *,
        num_perm: int = DEFAULT_NUM_PERM,
        threshold: float = DEFAULT_JACCARD_THRESHOLD,
    ) -> GlobalDuplicateIndex:
        p = Path(path)
        if not p.exists():
            return cls(num_perm=num_perm, threshold=threshold)
        try:
            data = p.read_bytes()
        except OSError as exc:
            logger.warning("[curate.minhash_index] read failed %s: %s", p, exc)
            return cls(num_perm=num_perm, threshold=threshold)
        return cls.from_bytes(data)


__all__ = [
    "DEFAULT_INDEX_FILENAME",
    "DEFAULT_JACCARD_THRESHOLD",
    "DEFAULT_NUM_PERM",
    "MAX_INDEX_BYTES_DEFAULT",
    "GlobalDuplicateIndex",
]
