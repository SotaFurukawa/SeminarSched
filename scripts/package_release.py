"""Create deterministic portable archives and release checksums."""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
import tomllib
import zipfile
from collections.abc import Iterable, Sequence
from pathlib import Path

_SEMVER = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-((?:(?:0|[1-9]\d*)|[0-9A-Za-z-]*[A-Za-z-][0-9A-Za-z-]*)"
    r"(?:\.(?:(?:0|[1-9]\d*)|[0-9A-Za-z-]*[A-Za-z-][0-9A-Za-z-]*))*))?"
    r"(?:\+([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?$"
)
_FORBIDDEN_SUFFIXES = {
    ".bak",
    ".backup",
    ".cer",
    ".crt",
    ".csv",
    ".db",
    ".db-journal",
    ".db-shm",
    ".db-wal",
    ".dwp",
    ".exp",
    ".ilk",
    ".key",
    ".jukuschedule",
    ".jukuschedule-journal",
    ".jukuschedule-shm",
    ".jukuschedule-wal",
    ".lib",
    ".log",
    ".map",
    ".obj",
    ".p12",
    ".pdb",
    ".pdf",
    ".pem",
    ".pfx",
    ".sqlite",
    ".sqlite-journal",
    ".sqlite-shm",
    ".sqlite-wal",
    ".sqlite3",
    ".sqlite3-journal",
    ".sqlite3-shm",
    ".sqlite3-wal",
    ".tmp",
    ".xlsx",
}
_FORBIDDEN_FILENAMES = {
    ".env",
    "config.yaml",
    "config.yml",
    "nuitka-crash-report.xml",
}
_FORBIDDEN_TOP_LEVEL_DIRECTORY_NAMES = {
    "backup",
    "backups",
    "data",
    "input",
    "inputs",
    "logs",
    "output",
    "outputs",
    "runtime",
}
_FIXED_ZIP_TIMESTAMP = (2026, 1, 1, 0, 0, 0)


class ReleasePackagingError(RuntimeError):
    """Release input or artifact validation failed."""


def validate_version(version: str) -> str:
    """Return a valid Semantic Version, rejecting ambiguous artifact names."""
    if _SEMVER.fullmatch(version) is None:
        raise ReleasePackagingError(f"Semantic Versioning形式ではありません: {version}")
    return version


def version_from_pyproject(pyproject_path: Path) -> str:
    """Read and validate the project version without importing the application."""
    with pyproject_path.open("rb") as stream:
        data = tomllib.load(stream)
    try:
        version = data["project"]["version"]
    except (KeyError, TypeError) as exc:
        raise ReleasePackagingError("pyproject.toml に project.version がありません") from exc
    if not isinstance(version, str):
        raise ReleasePackagingError("pyproject.toml の project.version が文字列ではありません")
    return validate_version(version)


def validate_tag(tag: str, version: str) -> None:
    """Require an exact v-prefixed tag/version match."""
    expected = f"v{validate_version(version)}"
    if tag != expected:
        raise ReleasePackagingError(f"タグ {tag!r} はアプリ版 {expected!r} と一致しません")


def validate_distribution(source: Path) -> tuple[Path, ...]:
    """Reject personal/runtime data and require all frozen runtime components."""
    source = source.resolve()
    if not source.is_dir():
        raise ReleasePackagingError(f"配布元フォルダーがありません: {source}")

    entries = tuple(source.rglob("*"))
    for path in entries:
        is_junction = getattr(path, "is_junction", lambda: False)
        if path.is_symlink() or is_junction():
            raise ReleasePackagingError(
                f"配布元にリンクを含められません: {path.relative_to(source)}"
            )
        if not path.resolve().is_relative_to(source):
            raise ReleasePackagingError(
                f"配布元外を参照する項目があります: {path.relative_to(source)}"
            )

    files = tuple(sorted((path for path in entries if path.is_file()), key=str))
    if not files:
        raise ReleasePackagingError("配布元フォルダーが空です")

    for path in files:
        relative = path.relative_to(source)
        top_level = relative.parts[0].casefold()
        if top_level in _FORBIDDEN_TOP_LEVEL_DIRECTORY_NAMES:
            raise ReleasePackagingError(f"利用者データ用フォルダーを含められません: {relative}")
        if path.name.casefold() in _FORBIDDEN_FILENAMES:
            raise ReleasePackagingError(f"秘密情報・ローカル設定になり得るファイルです: {relative}")
        if path.suffix.casefold() in _FORBIDDEN_SUFFIXES:
            raise ReleasePackagingError(f"実データになり得るファイルを含められません: {relative}")

    required_exact = (
        source / "SummerCourseScheduler.exe",
        source / "README.txt",
        source / "summer_scheduler" / "ui" / "qml" / "Main.qml",
        source / "summer_scheduler" / "resources" / "default_settings.yaml",
        source / "THIRD_PARTY_NOTICES.md",
        source / "PRIVACY.md",
        source / "CODE_SIGNING_POLICY.md",
        source / "licenses" / "THIRD_PARTY_NOTICES.txt",
        source / "licenses" / "Qt-Community-GPL-3.0-only" / "LICENSE.txt",
        source / "licenses" / "Nuitka-4.0" / "LICENSE.txt",
        source / "licenses" / "Nuitka-4.0" / "LICENSE-RUNTIME.txt",
    )
    for required in required_exact:
        if not required.is_file():
            raise ReleasePackagingError(f"必須ランタイム資産がありません: {required.name}")

    _require_name(files, "Qt6Pdf.dll")
    _require_name(files, "Qt6PdfQuick.dll")
    _require_name(files, "Qt6Qml.dll")
    _require_name(files, "Qt6Quick.dll")
    _require_name(files, "pdfquickplugin.dll")
    _require_name(files, "qquicklayoutsplugin.dll")
    _require_name(files, "qtquick2plugin.dll")
    _require_name(files, "qtquickcontrols2plugin.dll")
    _require_name(files, "qwindows.dll")
    _require_name(files, "ortools.dll")
    _require_name(files, "_sqlite3.pyd")
    _require_name(files, "sqlite3.dll")
    if not any(
        path.name.casefold() == "license.txt" and path.parent.name.casefold().startswith("cpython-")
        for path in files
    ):
        raise ReleasePackagingError("CPython LICENSE.txt がありません")
    if not any(
        path.name.casefold().startswith("cp_model_helper") and path.suffix.casefold() == ".pyd"
        for path in files
    ):
        raise ReleasePackagingError("OR-Tools CP-SAT拡張 cp_model_helper がありません")
    if not any(
        path.name.endswith(".py") and "alembic" in path.parts and "versions" in path.parts
        for path in files
    ):
        raise ReleasePackagingError("Alembicマイグレーションがありません")
    return files


def create_deterministic_archive(source: Path, output: Path) -> Path:
    """Archive a validated standalone tree with stable order and metadata."""
    source = source.resolve()
    files = validate_distribution(source)
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        output.unlink()

    with zipfile.ZipFile(
        output,
        "w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
        strict_timestamps=True,
    ) as archive:
        for path in files:
            relative = Path(source.name) / path.relative_to(source)
            info = zipfile.ZipInfo(relative.as_posix(), _FIXED_ZIP_TIMESTAMP)
            info.create_system = 3
            mode = 0o755 if path.suffix.casefold() in {".dll", ".exe", ".pyd"} else 0o644
            info.external_attr = mode << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, path.read_bytes(), compresslevel=9)

    if not output.is_file() or output.stat().st_size == 0:
        raise ReleasePackagingError("ポータブルZIPを作成できませんでした")
    return output


def sha256_file(path: Path) -> str:
    """Return a lowercase SHA-256 digest."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_checksums(artifacts: Iterable[Path], output: Path) -> Path:
    """Write sorted GNU-style SHA-256 entries and reject missing artifacts."""
    resolved = sorted((path.resolve() for path in artifacts), key=lambda item: item.name.casefold())
    if not resolved:
        raise ReleasePackagingError("チェックサム対象がありません")
    for artifact in resolved:
        if not artifact.is_file():
            raise ReleasePackagingError(f"成果物がありません: {artifact}")
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"{sha256_file(path)}  {path.name}" for path in resolved]
    output.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return output


def verify_checksums(checksum_path: Path, directory: Path) -> None:
    """Verify every checksum entry and disallow unsafe relative paths."""
    lines = checksum_path.read_text(encoding="utf-8").splitlines()
    if not lines:
        raise ReleasePackagingError("SHA256SUMS.txt が空です")
    directory = directory.resolve()
    for line in lines:
        match = re.fullmatch(r"([0-9a-f]{64})  ([^/\\]+)", line)
        if match is None:
            raise ReleasePackagingError(f"チェックサム行が不正です: {line!r}")
        expected, filename = match.groups()
        artifact = directory / filename
        if not artifact.is_file():
            raise ReleasePackagingError(f"チェックサム対象がありません: {filename}")
        actual = sha256_file(artifact)
        if actual != expected:
            raise ReleasePackagingError(f"SHA-256が一致しません: {filename}")


def _require_name(files: Sequence[Path], filename: str) -> None:
    if not any(path.name.casefold() == filename.casefold() for path in files):
        raise ReleasePackagingError(f"必須ランタイムがありません: {filename}")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    version_parser = subparsers.add_parser("validate-version")
    version_parser.add_argument("--pyproject", type=Path, required=True)
    version_parser.add_argument("--expected", required=True)

    tag_parser = subparsers.add_parser("validate-tag")
    tag_parser.add_argument("--pyproject", type=Path, required=True)
    tag_parser.add_argument("--tag", required=True)

    distribution_parser = subparsers.add_parser("validate-distribution")
    distribution_parser.add_argument("--source", type=Path, required=True)

    archive_parser = subparsers.add_parser("archive")
    archive_parser.add_argument("--source", type=Path, required=True)
    archive_parser.add_argument("--output", type=Path, required=True)

    checksum_parser = subparsers.add_parser("checksums")
    checksum_parser.add_argument("--output", type=Path, required=True)
    checksum_parser.add_argument("artifacts", nargs="+", type=Path)

    verify_parser = subparsers.add_parser("verify-checksums")
    verify_parser.add_argument("--checksums", type=Path, required=True)
    verify_parser.add_argument("--directory", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run a release packaging command with concise failure output."""
    parser = _build_parser()
    arguments = parser.parse_args(argv)
    try:
        if arguments.command == "validate-version":
            actual = version_from_pyproject(arguments.pyproject)
            expected = validate_version(arguments.expected)
            if actual != expected:
                raise ReleasePackagingError(
                    f"pyproject.toml の版 {actual!r} は指定版 {expected!r} と一致しません"
                )
        elif arguments.command == "validate-tag":
            validate_tag(arguments.tag, version_from_pyproject(arguments.pyproject))
        elif arguments.command == "validate-distribution":
            validate_distribution(arguments.source)
        elif arguments.command == "archive":
            create_deterministic_archive(arguments.source, arguments.output)
        elif arguments.command == "checksums":
            write_checksums(arguments.artifacts, arguments.output)
        elif arguments.command == "verify-checksums":
            verify_checksums(arguments.checksums, arguments.directory)
        else:  # pragma: no cover - argparse constrains this
            parser.error("unknown command")
    except (OSError, ReleasePackagingError, tomllib.TOMLDecodeError, zipfile.BadZipFile) as exc:
        print(f"release packaging failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
