"""Stage1/2 dedup tests."""

import hashlib

import pytest

from joryu.prompt_dedup import ExactDedup, normalize_prompt_exact
from joryu.seed_gen.dedup import EmbeddingBackend, EmbeddingIndex, cosine_similarity


class _StubBackend:
    """テスト用の決定論的 embedding backend。"""

    def embed(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for text in texts:
            digest = hashlib.sha256(text.encode("utf-8")).digest()
            out.append([float(b) / 255.0 for b in digest[:16]])
        return out


def _stub_backend() -> EmbeddingBackend:
    return _StubBackend()


class TestExactDedup:
    def test_nfkc_and_punctuation(self) -> None:
        assert normalize_prompt_exact("Pythonでhello") == normalize_prompt_exact(
            "Ｐｙｔｈｏｎでｈｅｌｌｏ"
        )
        assert normalize_prompt_exact("a b c") == normalize_prompt_exact("a  b\nc")
        assert normalize_prompt_exact("はい、わかった。") == normalize_prompt_exact("はいわかった")

    def test_seed_and_reject(self) -> None:
        d = ExactDedup()
        d.seed_from_existing(["Python", "JavaScript"])
        assert d.is_duplicate("Python")
        assert not d.is_duplicate("Rust")
        d.add("Rust")
        assert d.is_duplicate("Rust")


def test_embedding_index_rejects_similar() -> None:
    idx = EmbeddingIndex(_stub_backend(), threshold=0.99)
    idx.add("同じテーマの質問A")
    assert idx.is_similar("同じテーマの質問A")
    assert not idx.is_similar("全く別の長いプロンプト文字列XYZ")


def test_cosine_identical() -> None:
    v = [1.0, 0.0, 0.5]
    assert cosine_similarity(v, v) == pytest.approx(1.0)
