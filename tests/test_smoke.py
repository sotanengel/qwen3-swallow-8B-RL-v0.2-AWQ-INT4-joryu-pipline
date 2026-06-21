"""PR-1 スモーク: パッケージが import でき、バージョンが取れること。"""

import joryu


def test_version_is_string() -> None:
    assert isinstance(joryu.__version__, str)
    assert joryu.__version__


def test_package_importable() -> None:
    # 後続 PR で増える CLI モジュールが既に登録される前の最小確認。
    assert joryu.__name__ == "joryu"
