"""Collect runtime dependency license material into a portable distribution."""

from __future__ import annotations

import argparse
import platform
import re
import shutil
import sys
from collections import deque
from collections.abc import Sequence
from importlib import metadata
from pathlib import Path, PurePath

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

_ROOT_DISTRIBUTIONS = (
    "alembic",
    "openpyxl",
    "ortools",
    "platformdirs",
    "PySide6",
    "PyYAML",
    "SQLAlchemy",
    "XlsxWriter",
)
_LICENSE_MARKERS = ("authors", "copying", "copyright", "licence", "license", "notice")


class LicenseCollectionError(RuntimeError):
    """Required dependency metadata or license material is unavailable."""


def runtime_distributions(
    roots: Sequence[str] = _ROOT_DISTRIBUTIONS,
) -> tuple[metadata.Distribution, ...]:
    """Resolve the installed runtime dependency closure without build/dev extras."""
    pending = deque(roots)
    resolved: dict[str, metadata.Distribution] = {}
    while pending:
        requested = pending.popleft()
        key = canonicalize_name(requested)
        if key in resolved:
            continue
        try:
            distribution = metadata.distribution(requested)
        except metadata.PackageNotFoundError as exc:
            raise LicenseCollectionError(f"依存パッケージが未導入です: {requested}") from exc
        resolved[key] = distribution
        for raw_requirement in distribution.requires or ():
            requirement = Requirement(raw_requirement)
            if requirement.marker is not None and not requirement.marker.evaluate({"extra": ""}):
                continue
            pending.append(requirement.name)
    return tuple(resolved[key] for key in sorted(resolved))


def collect_licenses(output_directory: Path) -> Path:
    """Copy available license files and write a deterministic dependency notice."""
    output_directory = output_directory.resolve()
    output_directory.mkdir(parents=True, exist_ok=True)
    notices: list[str] = [
        "THIRD-PARTY RUNTIME DEPENDENCIES",
        "================================",
        "",
        "This inventory is generated from the release-build Python environment.",
        "Review the copied license texts before public distribution.",
        "",
    ]

    copied_file_count = 0
    seen_names: set[str] = set()
    for distribution in runtime_distributions():
        name = distribution.metadata.get("Name") or "unknown"
        version = distribution.version
        key = canonicalize_name(name)
        seen_names.add(key)
        expression = distribution.metadata.get("License-Expression")
        license_metadata = distribution.metadata.get("License")
        license_name = expression or _first_non_empty_line(license_metadata) or "UNKNOWN"
        homepage = _project_url(distribution)
        notices.extend(
            [
                f"{name} {version}",
                f"  License: {license_name}",
                f"  Source: {homepage or 'not declared in package metadata'}",
            ]
        )

        destination = output_directory / f"{_safe_component(name)}-{_safe_component(version)}"
        package_copied = 0
        for packaged_path in sorted(distribution.files or (), key=str):
            if not _is_license_file(packaged_path):
                continue
            source = Path(str(distribution.locate_file(packaged_path)))
            if not source.is_file():
                continue
            relative = _license_relative_path(packaged_path)
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            package_copied += 1
            copied_file_count += 1
        notices.append(f"  Copied license files: {package_copied}")
        notices.append("")

    required = {
        canonicalize_name("PySide6_Essentials"),
        canonicalize_name("ortools"),
        canonicalize_name("SQLAlchemy"),
    }
    if not required.issubset(seen_names):
        missing = ", ".join(sorted(required - seen_names))
        raise LicenseCollectionError(f"必須依存ライセンスを解決できません: {missing}")

    qt_license_source = Path(__file__).resolve().parents[1] / "LICENSE"
    if not qt_license_source.is_file():
        raise LicenseCollectionError(f"Qt Community GPLv3本文がありません: {qt_license_source}")
    qt_license_destination = output_directory / "Qt-Community-GPL-3.0-only" / "LICENSE.txt"
    qt_license_destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(qt_license_source, qt_license_destination)
    copied_file_count += 1
    notices.extend(
        [
            "Qt / PySide6 / Shiboken6 Community Edition",
            "  Distribution license selected by this project: GPL-3.0-only",
            "  Source: https://code.qt.io/cgit/pyside/pyside-setup.git/",
            "  Copied license files: 1",
            "",
        ]
    )

    python_license = Path(sys.base_prefix) / "LICENSE.txt"
    if not python_license.is_file():
        raise LicenseCollectionError(f"CPython LICENSE.txt がありません: {python_license}")
    python_destination = output_directory / f"CPython-{platform.python_version()}" / "LICENSE.txt"
    python_destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(python_license, python_destination)
    copied_file_count += 1
    notices.extend(
        [
            f"CPython {platform.python_version()}",
            "  License: Python Software Foundation License",
            "  Source: https://www.python.org/",
            "  Copied license files: 1",
            "",
        ]
    )

    nuitka = _collect_nuitka_runtime_exception(output_directory)
    copied_file_count += nuitka[0]
    notices.extend(nuitka[1])

    if copied_file_count == 0:
        raise LicenseCollectionError("ライセンスファイルを1件も収集できませんでした")
    notice_path = output_directory / "THIRD_PARTY_NOTICES.txt"
    notice_path.write_text("\n".join(notices), encoding="utf-8", newline="\n")
    return notice_path


def _collect_nuitka_runtime_exception(output_directory: Path) -> tuple[int, list[str]]:
    """Ship the compiler license and its Target Code runtime exception, not Nuitka itself."""
    try:
        distribution = metadata.distribution("Nuitka")
    except metadata.PackageNotFoundError as exc:
        raise LicenseCollectionError("Nuitkaのライセンスを解決できません") from exc
    wanted = {"license-runtime.txt", "license.txt"}
    destination = output_directory / f"Nuitka-{_safe_component(distribution.version)}"
    copied = 0
    copied_names: set[str] = set()
    for packaged_path in sorted(distribution.files or (), key=str):
        if packaged_path.name.casefold() not in wanted:
            continue
        if ".dist-info" not in packaged_path.as_posix():
            continue
        source = Path(str(distribution.locate_file(packaged_path)))
        if not source.is_file():
            continue
        target = destination / packaged_path.name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        copied += 1
        copied_names.add(packaged_path.name.casefold())
    if copied_names != wanted:
        missing = ", ".join(sorted(wanted - copied_names))
        raise LicenseCollectionError(f"Nuitka runtime exceptionが不足しています: {missing}")
    return copied, [
        f"Nuitka {distribution.version} (build tool; compiler package is not distributed)",
        "  License: GNU Affero General Public License v3",
        "  Additional permission: Nuitka Runtime Library Exception v1.0",
        "  Source: https://nuitka.net/",
        f"  Copied license files: {copied}",
        "",
    ]


def _is_license_file(path: PurePath) -> bool:
    lowered = path.name.casefold()
    return any(marker in lowered for marker in _LICENSE_MARKERS)


def _license_relative_path(path: PurePath) -> Path:
    parts = list(path.parts)
    for index, part in enumerate(parts):
        if part.casefold() in {"license", "licenses"}:
            return Path(*parts[index:])
    return Path(path.name)


def _first_non_empty_line(value: str | None) -> str | None:
    if value is None:
        return None
    return next((line.strip() for line in value.splitlines() if line.strip()), None)


def _project_url(distribution: metadata.Distribution) -> str | None:
    for entry in distribution.metadata.get_all("Project-URL") or ():
        _, separator, url = str(entry).partition(",")
        if separator and url.strip():
            return url.strip()
    homepage = distribution.metadata.get("Home-page")
    return str(homepage) if homepage else None


def _safe_component(value: str) -> str:
    return re.sub(r"[^0-9A-Za-z._-]+", "_", value)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Collect license files for the current release environment."""
    arguments = _build_parser().parse_args(argv)
    try:
        path = collect_licenses(arguments.output)
    except (LicenseCollectionError, OSError) as exc:
        print(f"license collection failed: {exc}", file=sys.stderr)
        return 1
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
