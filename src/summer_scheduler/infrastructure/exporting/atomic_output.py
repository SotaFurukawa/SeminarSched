"""同一ディレクトリの一時ファイルを使う原子的な出力保存。"""

from __future__ import annotations

import logging
import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from tempfile import NamedTemporaryFile

from summer_scheduler.infrastructure.exporting.errors import (
    OutputDestinationExistsError,
    OutputPermissionError,
    OutputWriteError,
)

logger = logging.getLogger(__name__)


@contextmanager
def atomic_output_path(
    destination: Path,
    *,
    overwrite: bool,
) -> Iterator[Path]:
    """一時パスを渡し、正常終了時だけ最終ファイルへ置換する。

    一時ファイルを最終ファイルと同じディレクトリへ作ることで、成功時の
    ``os.replace`` が同一ファイルシステム内の置換になるようにする。生成中や
    置換中に失敗しても既存の最終ファイルを先に削除しない。
    """

    target = destination.expanduser().resolve()
    temporary: Path | None = None
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and not overwrite:
            raise OutputDestinationExistsError(f"同名の出力ファイルが既にあります: {target.name}")

        with NamedTemporaryFile(
            mode="wb",
            prefix=f".{target.name}.",
            suffix=".tmp",
            dir=target.parent,
            delete=False,
        ) as stream:
            temporary = Path(stream.name)

        yield temporary

        if not temporary.is_file():
            raise OutputWriteError("出力用の一時ファイルが作成されませんでした")
        if target.exists() and not overwrite:
            raise OutputDestinationExistsError(
                f"出力中に同名ファイルが作成されたため保存を中止しました: {target.name}"
            )
        os.replace(temporary, target)
        temporary = None
    except OutputDestinationExistsError:
        raise
    except PermissionError as exc:
        raise OutputPermissionError(
            "出力先へ書き込めません。保存先の権限を確認し、"
            f"「{target.name}」をExcel等で開いている場合は閉じてください。"
        ) from exc
    except OSError as exc:
        raise OutputWriteError(f"出力ファイル「{target.name}」を保存できませんでした。") from exc
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError as cleanup_exc:
                # 元の例外を隠さず、個人情報を含み得る一時ファイルの残留を記録する。
                logger.warning(
                    "出力用一時ファイルを削除できませんでした（ファイル名は記録しません）",
                    exc_info=(
                        type(cleanup_exc),
                        OSError("例外の詳細値は安全のため省略しました"),
                        cleanup_exc.__traceback__,
                    ),
                )


__all__ = ["atomic_output_path"]
