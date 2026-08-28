"""Windows release engineering contract tests."""

from __future__ import annotations

import re
import zipfile
from pathlib import Path

import pytest
from scripts.collect_licenses import collect_licenses
from scripts.package_release import (
    ReleasePackagingError,
    create_deterministic_archive,
    sha256_file,
    validate_distribution,
    validate_tag,
    validate_version,
    verify_checksums,
    version_from_pyproject,
    write_checksums,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def test_release_version_and_tag_match_project_metadata() -> None:
    version = version_from_pyproject(REPOSITORY_ROOT / "pyproject.toml")

    assert version == "1.4.0"
    validate_tag("v1.4.0", version)
    with pytest.raises(ReleasePackagingError, match="一致しません"):
        validate_tag("v1.0.0", version)
    with pytest.raises(ReleasePackagingError, match="Semantic Versioning"):
        validate_version("1.0")
    assert validate_version("1.0.0-123abc") == "1.0.0-123abc"
    with pytest.raises(ReleasePackagingError, match="Semantic Versioning"):
        validate_version("1.0.0-01")


def test_portable_archive_is_deterministic_and_checksums_round_trip(tmp_path: Path) -> None:
    source = _fake_standalone_tree(tmp_path)
    first = tmp_path / "first.zip"
    second = tmp_path / "second.zip"

    create_deterministic_archive(source, first)
    create_deterministic_archive(source, second)

    assert sha256_file(first) == sha256_file(second)
    with zipfile.ZipFile(first) as archive:
        names = archive.namelist()
        assert names == sorted(names)
        assert names[0].startswith("SummerCourseScheduler/")
        assert {item.date_time for item in archive.infolist()} == {(2026, 1, 1, 0, 0, 0)}

    checksums = write_checksums((second, first), tmp_path / "SHA256SUMS.txt")
    verify_checksums(checksums, tmp_path)
    lines = checksums.read_text(encoding="utf-8").splitlines()
    assert lines == sorted(lines, key=lambda line: line.split("  ", 1)[1].casefold())


def test_distribution_rejects_runtime_or_personal_data(tmp_path: Path) -> None:
    source = _fake_standalone_tree(tmp_path)
    personal_database = source / "data" / "実データ.db"
    personal_database.parent.mkdir()
    personal_database.write_bytes(b"not a real database")

    with pytest.raises(ReleasePackagingError, match="利用者データ用フォルダー"):
        validate_distribution(source)


def test_distribution_allows_dependency_component_named_input(tmp_path: Path) -> None:
    source = _fake_standalone_tree(tmp_path)
    plugin_metadata = source / "PySide6" / "qml" / "Qt3D" / "Input" / "plugins.qmltypes"
    plugin_metadata.parent.mkdir(parents=True)
    plugin_metadata.write_text("Module {}\n", encoding="utf-8")

    files = validate_distribution(source)

    assert plugin_metadata in files


@pytest.mark.parametrize(
    "relative",
    (
        "config.yaml",
        ".env",
        "nuitka-crash-report.xml",
        "project.jukuschedule-wal",
        "signing-key.pfx",
        "embedded-source-paths.pdb",
    ),
)
def test_distribution_rejects_local_configuration_and_secrets(
    tmp_path: Path,
    relative: str,
) -> None:
    source = _fake_standalone_tree(tmp_path)
    (source / relative).write_bytes(b"must not be distributed")

    with pytest.raises(ReleasePackagingError):
        validate_distribution(source)


def test_license_collection_includes_nuitka_runtime_exception_not_compiler(
    tmp_path: Path,
) -> None:
    output = tmp_path / "licenses"

    notice = collect_licenses(output)

    text = notice.read_text(encoding="utf-8")
    assert "Nuitka Runtime Library Exception v1.0" in text
    assert (output / "Nuitka-4.0" / "LICENSE-RUNTIME.txt").is_file()
    assert (output / "Nuitka-4.0" / "LICENSE.txt").is_file()
    assert not any(path.suffix == ".py" for path in output.rglob("*"))
    assert any(path.name == "LICENSE.txt" and "CPython-" in str(path) for path in output.rglob("*"))
    assert any(
        path.name == "LICENCE.rst" and path.parent.name.startswith("openpyxl-")
        for path in output.rglob("*")
    )
    assert any(
        path.name == "LICENSE.txt" and path.parent.name.startswith("xlsxwriter-")
        for path in output.rglob("*")
    )
    assert (output / "Qt-Community-GPL-3.0-only" / "LICENSE.txt").is_file()


def test_pyside_deploy_spec_is_relative_standalone_and_complete() -> None:
    text = (REPOSITORY_ROOT / "packaging" / "pysidedeploy.spec").read_text(encoding="utf-8")

    assert "mode = standalone" in text
    assert "packages = Nuitka==4.0" in text
    assert "--windows-console-mode=disable" in text
    assert "--include-package-data=ortools" in text
    assert "--include-package=summer_scheduler.infrastructure.db.alembic.versions" in text
    assert "--jobs=2" in text
    assert "--include-package=sqlalchemy.dialects.sqlite" in text
    assert "--nofollow-import-to=sqlalchemy.dialects.oracle.dictionary" in text
    for dialect in ("mssql", "mysql", "oracle", "postgresql"):
        assert f"--nofollow-import-to=sqlalchemy.dialects.{dialect} " not in text
    assert "--nofollow-import-to=sqlalchemy.dialects.sqlite" not in text
    assert "summer_scheduler/ui" in text
    assert "summer_scheduler/resources" in text
    assert "Qt.labs.assetdownloader" in text
    assert "QtWebEngine" in text
    assert re.search(r"(?m)^[A-Za-z]:[\\/]", text) is None


def test_installer_preserves_user_data_and_has_safe_shortcuts() -> None:
    text = (REPOSITORY_ROOT / "installer" / "SummerCourseScheduler.iss").read_text(encoding="utf-8")
    sections = {
        line.strip().casefold()
        for line in text.splitlines()
        if line.strip().startswith("[") and line.strip().endswith("]")
    }

    assert '#define MyAppId "{{69E193A4-8240-49BD-9933-0E175303A4EE}"' in text
    assert "AppId={#MyAppId}" in text
    assert "PrivilegesRequired=lowest" in text
    assert "ArchitecturesAllowed=x64compatible" in text
    assert 'Name: "desktopicon"' in text
    assert "Flags: unchecked" in text
    assert "[icons]" in sections
    assert "[uninstalldelete]" not in sections
    assert "ChangesAssociations=no" in text
    assert ".jukuschedule association is intentionally not registered" in text
    assert "VersionInfoVersion={#MyAppFileVersion}" in text
    assert "VersionInfoProductName=SummerCourseScheduler" in text
    assert "VersionInfoProductVersion={#MyAppFileVersion}" in text
    assert "VersionInfoProductTextVersion={#MyAppVersion}" in text
    assert "InfoBeforeFile={#SourceDirectory}\\PRIVACY.md" in text

    build_script = (REPOSITORY_ROOT / "scripts" / "build_installer.ps1").read_text(encoding="utf-8")
    assert '"/DMyAppFileVersion=$fileVersion"' in build_script
    assert "validate-distribution --source $sourceDirectory" in build_script


def test_release_workflow_is_tag_only_and_creates_only_a_draft_prerelease() -> None:
    text = (REPOSITORY_ROOT / ".github" / "workflows" / "release-candidate.yml").read_text(
        encoding="utf-8"
    )

    assert '      - "v*"' in text
    assert "workflow_dispatch:" not in text
    assert "ruff check ." in text
    assert "mypy src tests" in text
    assert "pytest" in text
    assert "build_windows.ps1" in text
    assert "build_installer.ps1" in text
    assert "verify_authenticode.ps1" in text
    assert "-RequireUnsigned" in text
    assert "verify-checksums" in text
    assert "Expand-Archive" in text
    assert "actions/download-artifact@v4" in text
    assert "build/release-artifact-download/SHA256SUMS.txt" in text
    assert text.count('-ArgumentList "--smoke-test" -Wait -PassThru') == 2
    assert "Standalone application log" in text
    assert "failed before local logging was initialized" in text
    assert "& $exe --smoke-test" not in text
    assert '& (Join-Path $installRoot "SummerCourseScheduler.exe") --smoke-test' not in text
    assert "--draft" in text
    assert "--prerelease" in text
    assert "## Unsigned internal distribution" in text
    assert "Intentionally unsigned" in text
    assert "SHA256SUMS.txt" in text
    assert "gh release create" in text
    assert "gh release upload" not in text


def test_unsigned_distribution_policy_has_no_active_signpath_setup() -> None:
    readme = (REPOSITORY_ROOT / "README.md").read_text(encoding="utf-8")
    policy = (REPOSITORY_ROOT / "docs" / "code_signing_policy.md").read_text(encoding="utf-8")
    application = (REPOSITORY_ROOT / "docs" / "signpath_application.md").read_text(encoding="utf-8")
    workflow = (REPOSITORY_ROOT / ".github" / "workflows" / "release-candidate.yml").read_text(
        encoding="utf-8"
    )

    assert "未署名" in readme
    assert "意図的に未署名" in policy
    assert "申請は不承認" in application
    assert "SIGNPATH_API_TOKEN" not in workflow
    assert "signpath/github-action" not in workflow.lower()
    assert "-RequireUnsigned" in workflow

    active_workflows = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (REPOSITORY_ROOT / ".github" / "workflows").glob("*.yml")
    )
    assert "SIGNPATH_API_TOKEN" not in active_workflows


def test_release_requirements_are_exactly_pinned() -> None:
    lines = (
        (REPOSITORY_ROOT / "packaging" / "requirements-release.txt")
        .read_text(encoding="utf-8")
        .splitlines()
    )
    requirements = [line for line in lines if line and not line.startswith("#")]

    assert requirements
    assert all(
        re.fullmatch(r"[A-Za-z0-9_.-]+==[A-Za-z0-9_.+-]+", requirement)
        for requirement in requirements
    )
    assert "Nuitka==4.0" in requirements
    assert "packaging==26.2" in requirements
    assert "PySide6==6.11.1" in requirements
    assert "ortools==9.14.6206" in requirements
    assert "setuptools==83.0.0" in requirements
    assert "wheel==0.47.0" in requirements


def test_release_build_prunes_unused_asset_downloader_intermediates() -> None:
    text = (REPOSITORY_ROOT / "scripts" / "build_windows.ps1").read_text(encoding="utf-8")

    assert "PySide6\\qml\\Qt\\labs\\assetdownloader" in text
    assert "Get-WorkspacePath" in text
    assert "Remove-Item -LiteralPath $assetDownloaderDirectory -Recurse -Force" in text


def test_release_build_copies_alembic_runtime_sources_for_frozen_discovery() -> None:
    text = (REPOSITORY_ROOT / "scripts" / "build_windows.ps1").read_text(encoding="utf-8")

    assert '@("env.py", "script.py.mako")' in text
    assert 'Get-ChildItem -LiteralPath $revisionSource -Filter "*.py" -File' in text
    assert 'Join-Path $migrationTarget "versions"' in text


def test_inno_setup_ci_install_is_portable_and_non_admin() -> None:
    text = (REPOSITORY_ROOT / "scripts" / "install_inno_setup_ci.ps1").read_text(encoding="utf-8")

    assert '"/PORTABLE=1"' in text
    assert '"/CURRENTUSER"' in text
    assert "Get-AuthenticodeSignature" in text
    assert "Pyrsys B\\.V\\." in text


def _fake_standalone_tree(tmp_path: Path) -> Path:
    source = tmp_path / "SummerCourseScheduler"
    files = {
        "SummerCourseScheduler.exe": b"exe",
        "README.txt": b"portable instructions",
        "Qt6Pdf.dll": b"pdf",
        "Qt6PdfQuick.dll": b"pdfquick",
        "Qt6Qml.dll": b"qml",
        "Qt6Quick.dll": b"quick",
        "plugins/platforms/qwindows.dll": b"windows platform",
        "qml/QtQuick/qtquick2plugin.dll": b"qt quick",
        "qml/QtQuick/Controls/qtquickcontrols2plugin.dll": b"controls",
        "qml/QtQuick/Layouts/qquicklayoutsplugin.dll": b"layouts",
        "qml/QtQuick/Pdf/pdfquickplugin.dll": b"pdf qml",
        "ortools.dll": b"ortools",
        "_sqlite3.pyd": b"sqlite extension",
        "sqlite3.dll": b"sqlite runtime",
        "ortools/sat/python/cp_model_helper.cp312-win_amd64.pyd": b"cp-sat",
        "summer_scheduler/ui/qml/Main.qml": b"import QtQuick\n",
        "summer_scheduler/resources/default_settings.yaml": b"application: {}\n",
        (
            "summer_scheduler/infrastructure/db/alembic/versions/"
            "20260729_0006_add_phase6_output_settings.py"
        ): b"revision = '20260729_0006'\n",
        "THIRD_PARTY_NOTICES.md": b"# notices\n",
        "PRIVACY.md": b"# privacy\n",
        "CODE_SIGNING_POLICY.md": b"# Code signing policy\n",
        "licenses/THIRD_PARTY_NOTICES.txt": b"generated inventory\n",
        "licenses/CPython-3.12.4/LICENSE.txt": b"PSF license\n",
        "licenses/Qt-Community-GPL-3.0-only/LICENSE.txt": b"GPL-3.0-only\n",
        "licenses/Nuitka-4.0/LICENSE.txt": b"AGPL-3.0\n",
        "licenses/Nuitka-4.0/LICENSE-RUNTIME.txt": b"runtime exception\n",
    }
    for relative, content in files.items():
        target = source / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    return source
