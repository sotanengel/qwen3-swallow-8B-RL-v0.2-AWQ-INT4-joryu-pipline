"""BM25 検索インデックス (rank-bm25)。"""

from __future__ import annotations

import json
import logging
import pickle
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from joryu.search.record_key import record_id
from joryu.search.snippets import extract_snippet, pick_snippet_field
from joryu.search.tokenizer import tokenize

logger = logging.getLogger(__name__)

IndexStatus = Literal["ready", "building", "empty", "unavailable"]
TOKENIZER_VERSION = 1


@dataclass
class SearchHit:
    record_key: str
    score: float
    snippet: str
    snippet_field: str
    record: dict[str, Any]


@dataclass
class SearchResult:
    total: int
    index_status: IndexStatus
    hits: list[SearchHit]


@dataclass
class IndexStatusInfo:
    index_status: IndexStatus
    record_count: int
    built_at: str | None
    stale: bool


def build_search_text(record: dict[str, Any]) -> str:
    parts = [
        record.get("prompt"),
        record.get("answer"),
        record.get("thinking_trace"),
        record.get("category"),
        record.get("style_id"),
        record.get("model"),
    ]
    return "\n".join(str(p) for p in parts if p)


def _load_jsonl_records(jsonl_path: Path) -> list[dict[str, Any]]:
    if not jsonl_path.is_file():
        return []
    records: list[dict[str, Any]] = []
    for line in jsonl_path.read_text(encoding="utf-8").splitlines():
        trimmed = line.strip()
        if not trimmed:
            continue
        try:
            obj = json.loads(trimmed)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and isinstance(obj.get("prompt"), str):
            records.append(obj)
    return records


def _jsonl_fingerprint(jsonl_path: Path) -> tuple[float, int]:
    if not jsonl_path.is_file():
        return (0.0, 0)
    stat = jsonl_path.stat()
    text = jsonl_path.read_text(encoding="utf-8")
    line_count = sum(1 for line in text.splitlines() if line.strip())
    return (stat.st_mtime, line_count)


class SearchIndex:
    """BM25 インデックス。ディスクに永続化する。"""

    def __init__(self, index_dir: Path, *, snippet_chars: int = 200) -> None:
        self._index_dir = index_dir
        self._snippet_chars = snippet_chars
        self._bm25: Any | None = None
        self._tokenized_corpus: list[list[str]] = []
        self._records: list[dict[str, Any]] = []
        self._manifest: dict[str, Any] = {}
        self._load_from_disk()

    @property
    def manifest_path(self) -> Path:
        return self._index_dir / "manifest.json"

    @property
    def index_path(self) -> Path:
        return self._index_dir / "bm25.pkl"

    def _load_from_disk(self) -> None:
        if not self.manifest_path.is_file() or not self.index_path.is_file():
            return
        try:
            self._manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
            with self.index_path.open("rb") as f:
                payload = pickle.load(f)
            self._bm25 = payload["bm25"]
            self._tokenized_corpus = payload["tokenized_corpus"]
            self._records = payload["records"]
        except (OSError, json.JSONDecodeError, pickle.PickleError, KeyError) as exc:
            logger.warning("[search] failed to load index from %s: %s", self._index_dir, exc)
            self._bm25 = None
            self._tokenized_corpus = []
            self._records = []
            self._manifest = {}

    def _is_stale(self, jsonl_path: Path) -> bool:
        if not self._manifest:
            return True
        mtime, line_count = _jsonl_fingerprint(jsonl_path)
        return (
            self._manifest.get("jsonl_mtime") != mtime
            or self._manifest.get("jsonl_line_count") != line_count
            or self._manifest.get("tokenizer_version") != TOKENIZER_VERSION
        )

    def build(self, jsonl_path: Path) -> None:
        records = _load_jsonl_records(jsonl_path)
        self._records = records
        if not records:
            self._bm25 = None
            self._tokenized_corpus = []
            self._manifest = {
                "jsonl_mtime": 0.0,
                "jsonl_line_count": 0,
                "tokenizer_version": TOKENIZER_VERSION,
                "record_count": 0,
                "built_at": datetime.now(UTC).isoformat(),
                "index_status": "empty",
            }
            self._persist()
            return

        try:
            from rank_bm25 import BM25Okapi
        except ImportError as exc:
            raise ImportError(
                "rank-bm25 is required for search; install with `uv sync --extra api`"
            ) from exc

        corpus = [build_search_text(r) for r in records]
        self._tokenized_corpus = [tokenize(text) for text in corpus]
        self._bm25 = BM25Okapi(self._tokenized_corpus)
        mtime, line_count = _jsonl_fingerprint(jsonl_path)
        self._manifest = {
            "jsonl_mtime": mtime,
            "jsonl_line_count": line_count,
            "tokenizer_version": TOKENIZER_VERSION,
            "record_count": len(records),
            "built_at": datetime.now(UTC).isoformat(),
            "index_status": "ready",
        }
        self._persist()

    def _persist(self) -> None:
        self._index_dir.mkdir(parents=True, exist_ok=True)
        self.manifest_path.write_text(
            json.dumps(self._manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        if self._bm25 is not None:
            with self.index_path.open("wb") as f:
                pickle.dump(
                    {
                        "bm25": self._bm25,
                        "tokenized_corpus": self._tokenized_corpus,
                        "records": self._records,
                    },
                    f,
                )
        elif self.index_path.is_file():
            self.index_path.unlink()

    def ensure_fresh(self, jsonl_path: Path) -> None:
        if self._is_stale(jsonl_path):
            self.build(jsonl_path)

    def status(self) -> IndexStatusInfo:
        status: IndexStatus
        if self._manifest.get("index_status") == "empty" or (
            self._manifest.get("record_count", 0) == 0 and not self._records
        ):
            status = "empty"
        elif self._bm25 is None:
            status = "unavailable"
        else:
            status = "ready"
        return IndexStatusInfo(
            index_status=status,
            record_count=int(self._manifest.get("record_count", len(self._records))),
            built_at=self._manifest.get("built_at"),
            stale=False,
        )

    def status_for(self, jsonl_path: Path) -> IndexStatusInfo:
        info = self.status()
        info.stale = self._is_stale(jsonl_path)
        return info

    def search(
        self,
        query: str,
        *,
        mode: str = "all",
        category: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> SearchResult:
        if not self._records:
            return SearchResult(total=0, index_status="empty", hits=[])

        q = query.strip()
        filtered: list[tuple[int, float]] = []

        if not q:
            filtered = [
                (i, 0.0)
                for i in range(len(self._records))
                if self._passes_filters(i, mode, category)
            ]
        elif self._bm25 is not None:
            query_tokens = tokenize(q)
            if query_tokens:
                scores = self._bm25.get_scores(query_tokens)
                for i, score in enumerate(scores):
                    if not self._passes_filters(i, mode, category):
                        continue
                    filtered.append((i, float(score)))
                filtered.sort(key=lambda pair: pair[1], reverse=True)

        total = len(filtered)
        page = filtered[offset : offset + limit]
        hits: list[SearchHit] = []
        for i, score in page:
            rec = self._records[i]
            field = pick_snippet_field(rec, q)
            snippet = extract_snippet(str(rec.get(field) or ""), q, max_chars=self._snippet_chars)
            hits.append(
                SearchHit(
                    record_key=record_id(rec),
                    score=round(score, 4),
                    snippet=snippet,
                    snippet_field=field,
                    record=rec,
                )
            )

        status = self.status().index_status
        return SearchResult(total=total, index_status=status, hits=hits)

    def _passes_filters(self, i: int, mode: str, category: str | None) -> bool:
        rec = self._records[i]
        if mode and mode != "all" and rec.get("mode") != mode:
            return False
        if category and rec.get("category") != category:
            return False
        return True
