"""実パッケージのオフスクリーン起動テスト。"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def test_module_entrypoint_loads_qml_and_initializes_runtime(tmp_path: Path) -> None:
    data_directory = tmp_path / "アプリデータ"
    log_directory = tmp_path / "アプリログ"
    environment = os.environ.copy()
    environment.pop("SUMMER_SCHEDULER_CONFIG", None)
    environment.update(
        {
            "PYTHONUTF8": "1",
            "QT_QPA_PLATFORM": "offscreen",
            "QT_QUICK_BACKEND": "software",
            "QSG_RHI_BACKEND": "software",
            "SUMMER_SCHEDULER_DATA_DIR": str(data_directory),
            "SUMMER_SCHEDULER_LOG_DIR": str(log_directory),
        }
    )

    result = subprocess.run(
        [sys.executable, "-m", "summer_scheduler", "--smoke-test"],
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert (data_directory / "summer_scheduler.db").is_file()
    assert (log_directory / "summer_scheduler.log").is_file()
