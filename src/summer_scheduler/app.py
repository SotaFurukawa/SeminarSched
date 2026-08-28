"""PySide6/QMLデスクトップアプリの起動エントリーポイント。"""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Sequence
from pathlib import Path

from PySide6.QtCore import QTimer, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine

from summer_scheduler import __release_channel__, __version__
from summer_scheduler.application.availability_import_service import (
    AvailabilityImportService,
)
from summer_scheduler.application.group_lesson_service import GroupLessonService
from summer_scheduler.application.master_data_service import MasterDataService
from summer_scheduler.application.optimization_run_service import OptimizationRunService
from summer_scheduler.application.output_service import OutputService
from summer_scheduler.application.project_validation_service import (
    ProjectValidationService,
)
from summer_scheduler.application.questionnaire_script_service import (
    QuestionnaireScriptService,
)
from summer_scheduler.application.sample_project_service import SampleProjectService
from summer_scheduler.application.schedule_edit_service import ScheduleEditService
from summer_scheduler.bootstrap import BootstrapError, bootstrap
from summer_scheduler.infrastructure.db import get_head_revision
from summer_scheduler.shared.settings import SettingsError
from summer_scheduler.ui.viewmodels.app_view_model import AppViewModel
from summer_scheduler.ui.viewmodels.optimization_view_model import OptimizationViewModel
from summer_scheduler.ui.viewmodels.output_view_model import OutputViewModel
from summer_scheduler.ui.viewmodels.phase3_view_model import Phase3ViewModel
from summer_scheduler.ui.viewmodels.schedule_editor_view_model import (
    ScheduleEditorViewModel,
)
from summer_scheduler.ui.viewmodels.workspace_view_model import WorkspaceViewModel

logger = logging.getLogger(__name__)


class ApplicationStartError(RuntimeError):
    """QML画面を生成できなかった場合の例外。"""


def run(argv: Sequence[str] | None = None) -> int:
    """ローカル実行環境とQMLを初期化してイベントループを開始する。"""
    raw_arguments = list(argv) if argv is not None else list(sys.argv)
    arguments, qt_arguments = _parse_arguments(raw_arguments)

    runtime = bootstrap(arguments.config)
    try:
        application = QGuiApplication(qt_arguments)
        application.setApplicationName("summer-scheduler")
        application.setApplicationDisplayName(runtime.settings.application_name)
        application.setOrganizationName(runtime.settings.organization_name)
        application.setApplicationVersion(__version__)

        engine = QQmlApplicationEngine()
        schema_version = get_head_revision()
        view_model = AppViewModel(
            __version__,
            schema_version,
            release_channel=__release_channel__,
            database_ready=True,
        )
        logger.info(
            "アプリケーションを起動します（app_version=%s, release_channel=%s, db_schema=%s）",
            __version__,
            __release_channel__,
            schema_version,
        )
        workspace_view_model = WorkspaceViewModel(
            runtime.projects,
            MasterDataService(runtime.projects),
        )
        automatic_backup_timer = QTimer(application)
        automatic_backup_timer.setInterval(
            runtime.settings.backup.automatic_interval_minutes * 60 * 1000
        )
        automatic_backup_timer.timeout.connect(workspace_view_model.createAutomaticBackup)
        automatic_backup_timer.start()
        optimization_view_model = OptimizationViewModel(
            OptimizationRunService(
                runtime.projects,
                runtime.settings.optimization,
            ),
            runtime.projects,
            runtime.log_path,
        )
        schedule_editor_view_model = ScheduleEditorViewModel(
            ScheduleEditService(
                runtime.projects,
                runtime.settings.optimization,
            ),
            runtime.projects,
        )
        output_view_model = OutputViewModel(
            OutputService(
                runtime.projects,
                runtime.settings.optimization,
                output_defaults=runtime.settings.output,
            ),
            runtime.projects,
        )

        def ensure_project_switch_allowed() -> None:
            optimization_view_model.ensure_project_switch_allowed()
            output_view_model.ensure_project_switch_allowed()

        workspace_view_model.set_project_change_guard(ensure_project_switch_allowed)
        phase3_view_model = Phase3ViewModel(
            runtime.projects,
            AvailabilityImportService(runtime.projects),
            GroupLessonService(runtime.projects),
            ProjectValidationService(runtime.projects),
            SampleProjectService(runtime.projects),
            QuestionnaireScriptService(runtime.projects),
            before_project_change=workspace_view_model.ensure_project_switch_allowed,
        )
        workspace_view_model.projectStateChanged.connect(phase3_view_model.refreshPhase3)
        workspace_view_model.projectStateChanged.connect(
            optimization_view_model.refreshProjectState
        )
        workspace_view_model.projectStateChanged.connect(
            schedule_editor_view_model.refreshProjectState
        )
        workspace_view_model.projectStateChanged.connect(output_view_model.refreshProjectState)
        phase3_view_model.projectChanged.connect(workspace_view_model.refreshProjectState)
        optimization_view_model.optimizationSaved.connect(workspace_view_model.refreshProjectState)
        schedule_editor_view_model.scheduleSaved.connect(workspace_view_model.refreshProjectState)
        application.aboutToQuit.connect(optimization_view_model.shutdown)
        application.aboutToQuit.connect(output_view_model.shutdown)
        engine.rootContext().setContextProperty("appViewModel", view_model)
        engine.rootContext().setContextProperty(
            "workspaceViewModel",
            workspace_view_model,
        )
        engine.rootContext().setContextProperty(
            "phase3ViewModel",
            phase3_view_model,
        )
        engine.rootContext().setContextProperty(
            "optimizationViewModel",
            optimization_view_model,
        )
        engine.rootContext().setContextProperty(
            "scheduleEditorViewModel",
            schedule_editor_view_model,
        )
        engine.rootContext().setContextProperty(
            "outputViewModel",
            output_view_model,
        )
        engine.load(QUrl.fromLocalFile(str(_qml_entrypoint())))

        if not engine.rootObjects():
            raise ApplicationStartError(
                "メイン画面を読み込めませんでした。ログを確認してください。"
            )

        logger.info("メインウィンドウを表示しました")
        if arguments.smoke_test:
            QTimer.singleShot(100, application.quit)

        return application.exec()
    except Exception:
        logger.exception("画面の初期化または実行中にエラーが発生しました")
        raise
    finally:
        runtime.close()


def main() -> int:
    """CLI向けに既知の起動失敗を日本語で報告する。"""
    try:
        return run()
    except (ApplicationStartError, BootstrapError, SettingsError, OSError) as exc:
        print(f"アプリケーションを起動できませんでした: {exc}", file=sys.stderr)
        return 1
    except Exception:
        logger.exception("予期しない起動エラーが発生しました")
        print(
            "予期しないエラーで起動できませんでした。ローカルログを確認してください。",
            file=sys.stderr,
        )
        return 1


def _parse_arguments(
    argv: list[str],
) -> tuple[argparse.Namespace, list[str]]:
    parser = argparse.ArgumentParser(
        prog=argv[0] if argv else "summer-scheduler",
        description="夏期講習時間割作成ローカルデスクトップアプリ",
    )
    parser.add_argument(
        "--config",
        type=Path,
        help="読み込むYAML設定ファイル",
    )
    parser.add_argument(
        "--smoke-test",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    arguments, qt_options = parser.parse_known_args(argv[1:])
    executable = argv[0] if argv else "summer-scheduler"
    return arguments, [executable, *qt_options]


def _qml_entrypoint() -> Path:
    path = Path(__file__).resolve().parent / "ui" / "qml" / "Main.qml"
    if not path.is_file():
        raise ApplicationStartError(f"QMLファイルが見つかりません: {path.name}")
    return path
