"""``python -m summer_scheduler`` 用のエントリーポイント。"""

from __future__ import annotations

from summer_scheduler.app import main as _main


def main() -> int:
    """デスクトップアプリを起動する。"""
    return _main()


if __name__ == "__main__":
    raise SystemExit(main())
