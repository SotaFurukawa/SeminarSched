[app]

# This file is copied to build/pysidedeploy.spec before use. Paths are
# intentionally relative to that generated file or to the repository root.
title = SummerCourseScheduler
project_dir = ..
input_file = src/summer_scheduler/__main__.py
exec_directory = build/deploy
project_file =
icon =

[python]

python_path =
packages = Nuitka==4.0

[qt]

qml_files = src/summer_scheduler/ui/qml/AvailabilityImportPage.qml,src/summer_scheduler/ui/qml/DashboardCard.qml,src/summer_scheduler/ui/qml/DashboardPage.qml,src/summer_scheduler/ui/qml/ExcelSettingsTab.qml,src/summer_scheduler/ui/qml/GroupLessonPage.qml,src/summer_scheduler/ui/qml/Main.qml,src/summer_scheduler/ui/qml/OpenDateSettingsTab.qml,src/summer_scheduler/ui/qml/OptimizationPage.qml,src/summer_scheduler/ui/qml/OutputPage.qml,src/summer_scheduler/ui/qml/Phase3DiffList.qml,src/summer_scheduler/ui/qml/Phase3IssueList.qml,src/summer_scheduler/ui/qml/PlaceholderPage.qml,src/summer_scheduler/ui/qml/ProjectHomePage.qml,src/summer_scheduler/ui/qml/ProjectSettingsTab.qml,src/summer_scheduler/ui/qml/ScheduleEditorPage.qml,src/summer_scheduler/ui/qml/SettingsPage.qml,src/summer_scheduler/ui/qml/Sidebar.qml,src/summer_scheduler/ui/qml/StatusBanner.qml,src/summer_scheduler/ui/qml/StudentPage.qml,src/summer_scheduler/ui/qml/SubjectSettingsTab.qml,src/summer_scheduler/ui/qml/TeacherPage.qml,src/summer_scheduler/ui/qml/TimeSlotSettingsTab.qml,src/summer_scheduler/ui/qml/ValidationIssuesPage.qml
excluded_qml_plugins = Qt.labs.assetdownloader,QtCharts,QtQuick3D,QtSensors,QtTest,QtWebEngine
modules = Core,Gui,Pdf,Qml,Quick,QuickControls2
plugins =

[android]

wheel_pyside =
wheel_shiboken =
plugins =

[nuitka]

macos.permissions =
mode = standalone
# pyside6-deploy already enables the PySide6 plugin. Explicit data targets
# preserve package-relative paths used by __file__ and importlib.resources.
extra_args = --quiet --assume-yes-for-downloads --windows-console-mode=disable --msvc=latest --jobs=2 --include-package=summer_scheduler.infrastructure.db.alembic.versions --include-package=sqlalchemy.dialects.sqlite --nofollow-import-to=sqlalchemy.dialects.oracle.dictionary --include-package-data=ortools --include-data-dir=src/summer_scheduler/ui=summer_scheduler/ui --include-data-dir=src/summer_scheduler/resources=summer_scheduler/resources --include-data-dir=src/summer_scheduler/infrastructure/db/alembic=summer_scheduler/infrastructure/db/alembic --windows-company-name=SummerScheduler --windows-product-name=SummerCourseScheduler --windows-file-version=@FILE_VERSION@ --windows-product-version=@FILE_VERSION@

[buildozer]

mode = debug
recipe_dir =
jars_dir =
ndk_path =
sdk_path =
local_libs =
arch =
