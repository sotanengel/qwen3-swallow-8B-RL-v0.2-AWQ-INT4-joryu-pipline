"""scripts/migrate_csv_to_jsonl.py の機能 (csv -> jsonl prompt bank)."""

from pathlib import Path

from joryu.migrate import csv_to_jsonl


def _read_jsonl(path: Path) -> list[str]:
    return [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]


def test_csv_to_jsonl_basic(tmp_path: Path) -> None:
    csv_path = tmp_path / "in.csv"
    csv_path.write_text(
        "分野,プロンプト\n国語,桜の特徴は？\n数学,1+1は？\n",
        encoding="utf-8",
    )
    out_path = tmp_path / "out.jsonl"
    n = csv_to_jsonl(csv_path, out_path)
    assert n == 2
    lines = _read_jsonl(out_path)
    assert len(lines) == 2
    import json

    rows = [json.loads(ln) for ln in lines]
    assert rows[0]["prompt"] == "桜の特徴は？"
    assert rows[0]["category"] == "国語"
    assert rows[1]["category"] == "数学"


def test_csv_to_jsonl_skips_empty_rows(tmp_path: Path) -> None:
    csv_path = tmp_path / "in.csv"
    csv_path.write_text(
        "分野,プロンプト\n国語,桜\n,\n数学,2+2\n",
        encoding="utf-8",
    )
    out_path = tmp_path / "out.jsonl"
    n = csv_to_jsonl(csv_path, out_path)
    assert n == 2


def test_csv_to_jsonl_creates_parent_dir(tmp_path: Path) -> None:
    csv_path = tmp_path / "in.csv"
    csv_path.write_text("分野,プロンプト\n国語,桜\n", encoding="utf-8")
    out_path = tmp_path / "nested" / "deep" / "out.jsonl"
    n = csv_to_jsonl(csv_path, out_path)
    assert n == 1
    assert out_path.exists()


def test_csv_to_jsonl_handles_bom(tmp_path: Path) -> None:
    csv_path = tmp_path / "in.csv"
    # UTF-8 BOM つきCSV (元データと同じ条件)
    csv_path.write_bytes(
        b"\xef\xbb\xbf\xe5\x88\x86\xe9\x87\x8e,\xe3\x83\x97\xe3\x83\xad\xe3\x83\xb3\xe3\x83\x97\xe3\x83\x88\n\xe5\x9b\xbd\xe8\xaa\x9e,\xe6\xa1\x9c\n"
    )
    out_path = tmp_path / "out.jsonl"
    n = csv_to_jsonl(csv_path, out_path)
    assert n == 1
    import json

    row = json.loads(_read_jsonl(out_path)[0])
    assert row["category"] == "国語"
    assert row["prompt"] == "桜"
