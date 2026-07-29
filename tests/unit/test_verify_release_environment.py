"""Release-build environment isolation tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from scripts.verify_release_environment import (
    InstalledDistribution,
    ReleaseEnvironmentError,
    canonicalize_name,
    read_exact_pins,
    verify_release_environment,
)


def _write_configuration(tmp_path: Path) -> tuple[Path, Path]:
    requirements = tmp_path / "requirements-release.txt"
    requirements.write_text(
        "# exact release lock\nPySide6_Addons==6.11.1\nsetuptools==83.0.0\nwheel==0.47.0\n",
        encoding="utf-8",
    )
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        '[project]\nname = "summer-course-scheduler"\nversion = "1.0.0-rc.1"\n',
        encoding="utf-8",
    )
    return requirements, pyproject


def _valid_installed(*, editable: bool) -> tuple[InstalledDistribution, ...]:
    return (
        InstalledDistribution("pip", "26.1", "site-packages"),
        InstalledDistribution("PySide6-Addons", "6.11.1", "site-packages"),
        InstalledDistribution("setuptools", "83.0.0", "site-packages"),
        InstalledDistribution("wheel", "0.47.0", "site-packages"),
        InstalledDistribution(
            "summer_course_scheduler",
            "1.0.0rc1",
            "site-packages",
            editable=editable,
        ),
    )


def test_canonicalize_name_handles_all_pep_503_separators() -> None:
    assert canonicalize_name("PySide6_Addons") == "pyside6-addons"
    assert canonicalize_name("Summer.Course__Scheduler") == "summer-course-scheduler"


def test_release_environment_accepts_only_exact_pins_pip_and_noneditable_project(
    tmp_path: Path,
) -> None:
    requirements, pyproject = _write_configuration(tmp_path)

    result = verify_release_environment(
        requirements,
        pyproject,
        installed=_valid_installed(editable=False),
    )

    assert result.pinned_distribution_count == 3
    assert result.project_editable is False


def test_release_environment_rejects_editable_project_install(tmp_path: Path) -> None:
    requirements, pyproject = _write_configuration(tmp_path)

    with pytest.raises(ReleaseEnvironmentError, match="must be non-editable"):
        verify_release_environment(
            requirements,
            pyproject,
            installed=_valid_installed(editable=True),
        )


def test_release_environment_reports_missing_mismatch_duplicate_and_unexpected(
    tmp_path: Path,
) -> None:
    requirements, pyproject = _write_configuration(tmp_path)
    installed = (
        InstalledDistribution("pip", "26.1", "site-packages"),
        InstalledDistribution("PySide6_Addons", "6.10.0", "first"),
        InstalledDistribution("PySide6-Addons", "6.11.1", "second"),
        InstalledDistribution("setuptools", "82.0.0", "site-packages"),
        InstalledDistribution("summer-course-scheduler", "1.0.0", "site-packages"),
        InstalledDistribution("pytest", "8.4.2", "site-packages"),
    )

    with pytest.raises(ReleaseEnvironmentError) as exc_info:
        verify_release_environment(
            requirements,
            pyproject,
            installed=installed,
        )

    message = str(exc_info.value)
    assert "duplicate installed distribution 'pyside6-addons'" in message
    assert "version mismatch for PySide6_Addons: expected 6.11.1, found 6.10.0" in message
    assert "version mismatch for setuptools: expected 83.0.0, found 82.0.0" in message
    assert "missing pinned distribution: wheel==0.47.0" in message
    assert "project version mismatch" in message
    assert "unexpected installed distribution: pytest==8.4.2" in message


@pytest.mark.parametrize(
    "contents, expected",
    (
        ("PySide6>=6.11\n", "exact 'name==version' pin required"),
        ("PySide6==6.11.1\npyside6==6.11.1\n", "duplicate pin"),
        ("# comments only\n", "no release dependency pins found"),
    ),
)
def test_release_requirements_fail_closed(
    tmp_path: Path,
    contents: str,
    expected: str,
) -> None:
    requirements = tmp_path / "requirements-release.txt"
    requirements.write_text(contents, encoding="utf-8")

    with pytest.raises(ReleaseEnvironmentError, match=expected):
        read_exact_pins(requirements)


def test_release_build_and_workflow_run_environment_guard() -> None:
    repository_root = Path(__file__).resolve().parents[2]
    build_script = (repository_root / "scripts" / "build_windows.ps1").read_text(encoding="utf-8")
    workflow = (repository_root / ".github" / "workflows" / "release-candidate.yml").read_text(
        encoding="utf-8"
    )

    assert build_script.index("verify_release_environment.py") < build_script.index(
        "pyside6-deploy"
    )
    assert "ASCII-only workspace path" in build_script
    assert build_script.index("ASCII-only workspace path") < build_script.index(
        "verify_release_environment.py"
    )
    assert "Copy or clone this repository to an ASCII-only" in build_script
    assert "py -3.12 -m venv .venv-release" in build_script
    assert "os.path.realpath" in build_script
    assert "subst, junctions, and symbolic links are not sufficient" in build_script
    assert build_script.index("os.path.realpath") < build_script.index(
        "verify_release_environment.py"
    )
    assert "python scripts/verify_release_environment.py" in workflow
    scrub = "python -m pip uninstall --yes argcomplete click colorama pipx userpath"
    assert scrub in workflow
    assert workflow.index(scrub) < workflow.index(
        "python -m pip install -r packaging/requirements-release.txt"
    )
