"""Phase 6のファイル出力境界で利用する利用者向け例外。"""

from __future__ import annotations


class OutputExportError(RuntimeError):
    """出力処理を安全に完了できなかった場合の基底例外。"""


class OutputDestinationExistsError(OutputExportError):
    """確認されていない既存ファイル上書きを拒否した。"""


class OutputPermissionError(OutputExportError):
    """保存先の権限または外部アプリのファイルロックで保存できない。"""


class OutputWriteError(OutputExportError):
    """保存先への書込みまたは原子的な置換を完了できない。"""


class OutputRenderError(OutputExportError):
    """中間レイアウトや出力データをファイルへ変換できない。"""


class OutputDataError(OutputRenderError):
    """参照欠落等により、情報を失わず出力できない。"""


__all__ = [
    "OutputDataError",
    "OutputDestinationExistsError",
    "OutputExportError",
    "OutputPermissionError",
    "OutputRenderError",
    "OutputWriteError",
]
