"""Fail closed when the Windows release build uses an unpinned Python environment."""

from __future__ import annotations

import argparse
import json
import re
import sys
import tomllib
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path

from packaging.version import InvalidVersion, Version

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REQUIREMENTS = REPOSITORY_ROOT / "packaging" / "requirements-release.txt"
DEFAULT_PYPROJECT = REPOSITORY_ROOT / "pyproject.toml"
EXACT_REQUIREMENT_PATTERN = re.compile(
    r"(?P<name>[A-Za-z0-9][A-Za-z0-9_.-]*)==(?P<version>[A-Za-z0-9][A-Za-z0-9_.+!-]*)"
)


class ReleaseEnvironmentError(RuntimeError):
    """Raised when the active interpreter is unsafe for a release build."""


@dataclass(frozen=True)
class ExactPin:
    """One exact distribution pin from the release requirements file."""

    name: str
    canonical_name: str
    version: str


@dataclass(frozen=True)
class InstalledDistribution:
    """Relevant installed-distribution metadata used by the verifier."""

    name: str
    version: str
    location: str
    editable: bool = False

    @property
    def canonical_name(self) -> str:
        """Return the PEP 503-normalized distribution name."""
        return canonicalize_name(self.name)


@dataclass(frozen=True)
class ReleaseEnvironment:
    """Successful release-environment verification summary."""

    pinned_distribution_count: int
    project_name: str
    project_version: str
    project_editable: bool


def canonicalize_name(name: str) -> str:
    """Normalize a distribution name as specified by PEP 503."""
    return re.sub(r"[-_.]+", "-", name).lower()


def read_exact_pins(path: Path) -> dict[str, ExactPin]:
    """Read an intentionally simple requirements file containing only exact pins."""
    pins: dict[str, ExactPin] = {}
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = EXACT_REQUIREMENT_PATTERN.fullmatch(line)
        if match is None:
            raise ReleaseEnvironmentError(
                f"{path}:{line_number}: exact 'name==version' pin required: {line!r}"
            )
        name = match.group("name")
        canonical_name = canonicalize_name(name)
        if canonical_name in pins:
            previous = pins[canonical_name]
            raise ReleaseEnvironmentError(
                f"{path}:{line_number}: duplicate pin for {name!r}; "
                f"already pinned as {previous.name!r}"
            )
        pins[canonical_name] = ExactPin(
            name=name,
            canonical_name=canonical_name,
            version=match.group("version"),
        )
    if not pins:
        raise ReleaseEnvironmentError(f"{path}: no release dependency pins found")
    return pins


def read_project_identity(path: Path) -> tuple[str, str]:
    """Read the project distribution name and version from pyproject.toml."""
    with path.open("rb") as stream:
        document = tomllib.load(stream)
    project = document.get("project")
    if not isinstance(project, dict):
        raise ReleaseEnvironmentError(f"{path}: [project] table is missing")
    name = project.get("name")
    version = project.get("version")
    if not isinstance(name, str) or not name:
        raise ReleaseEnvironmentError(f"{path}: project.name is missing")
    if not isinstance(version, str) or not version:
        raise ReleaseEnvironmentError(f"{path}: project.version is missing")
    return name, version


def discover_installed_distributions() -> tuple[InstalledDistribution, ...]:
    """Inspect distributions visible to the active Python interpreter."""
    installed: list[InstalledDistribution] = []
    for distribution in metadata.distributions():
        name = distribution.metadata.get("Name")
        if not name:
            raise ReleaseEnvironmentError(
                f"installed distribution has no Name metadata at {distribution.locate_file('')}"
            )
        installed.append(
            InstalledDistribution(
                name=name,
                version=distribution.version,
                location=str(distribution.locate_file("")),
                editable=_distribution_is_editable(distribution),
            )
        )
    return tuple(installed)


def verify_release_environment(
    requirements_path: Path = DEFAULT_REQUIREMENTS,
    pyproject_path: Path = DEFAULT_PYPROJECT,
    *,
    installed: Sequence[InstalledDistribution] | None = None,
) -> ReleaseEnvironment:
    """Verify exact pins and reject every distribution outside the release allow-list."""
    pins = read_exact_pins(requirements_path)
    project_name, project_version = read_project_identity(pyproject_path)
    project_canonical_name = canonicalize_name(project_name)
    if project_canonical_name in pins:
        raise ReleaseEnvironmentError(
            f"{requirements_path}: project {project_name!r} must not be a third-party pin"
        )

    discovered = tuple(installed) if installed is not None else discover_installed_distributions()
    by_name: dict[str, list[InstalledDistribution]] = defaultdict(list)
    for distribution in discovered:
        by_name[distribution.canonical_name].append(distribution)

    problems: list[str] = []
    for canonical_name, distributions in sorted(by_name.items()):
        if len(distributions) > 1:
            locations = ", ".join(
                f"{item.name}=={item.version} at {item.location}" for item in distributions
            )
            problems.append(f"duplicate installed distribution {canonical_name!r}: {locations}")

    for canonical_name, pin in sorted(pins.items()):
        distributions = by_name.get(canonical_name, [])
        if not distributions:
            problems.append(f"missing pinned distribution: {pin.name}=={pin.version}")
            continue
        installed_version = distributions[0].version
        if installed_version != pin.version:
            problems.append(
                f"version mismatch for {pin.name}: expected {pin.version}, "
                f"found {installed_version}"
            )

    project_distributions = by_name.get(project_canonical_name, [])
    if not project_distributions:
        problems.append(f"project distribution is not installed: {project_name}=={project_version}")
    elif not _versions_equivalent(project_distributions[0].version, project_version):
        problems.append(
            f"project version mismatch for {project_name}: expected {project_version}, "
            f"found {project_distributions[0].version}"
        )
    elif project_distributions[0].editable:
        problems.append(
            f"project distribution must be non-editable for release builds: {project_name}; "
            "editable .pth files are unsafe in the Windows deployment toolchain"
        )

    # pip is the only unpinned bootstrap tool allowed. setuptools and wheel must remain
    # explicit exact pins because their build hooks can change Nuitka's inputs.
    allowed_names = set(pins) | {"pip", project_canonical_name}
    for canonical_name in sorted(set(by_name) - allowed_names):
        descriptions = ", ".join(f"{item.name}=={item.version}" for item in by_name[canonical_name])
        problems.append(f"unexpected installed distribution: {descriptions}")

    if problems:
        details = "\n  - ".join(problems)
        raise ReleaseEnvironmentError(
            "release environment is not isolated and exactly pinned:\n"
            f"  - {details}\n"
            "Create a clean Python 3.12 x64 virtual environment, install "
            "packaging/requirements-release.txt, then install this project with "
            "'pip install --no-deps --no-build-isolation .'."
        )

    project_distribution = project_distributions[0]
    return ReleaseEnvironment(
        pinned_distribution_count=len(pins),
        project_name=project_name,
        project_version=project_version,
        project_editable=project_distribution.editable,
    )


def _distribution_is_editable(distribution: metadata.Distribution) -> bool:
    direct_url_text = distribution.read_text("direct_url.json")
    if direct_url_text is None:
        return False
    try:
        direct_url = json.loads(direct_url_text)
    except json.JSONDecodeError:
        return False
    if not isinstance(direct_url, dict):
        return False
    directory_info = direct_url.get("dir_info")
    return isinstance(directory_info, dict) and directory_info.get("editable") is True


def _versions_equivalent(installed_version: str, declared_version: str) -> bool:
    """Compare project versions after normal wheel-metadata PEP 440 normalization."""
    try:
        return Version(installed_version) == Version(declared_version)
    except InvalidVersion:
        return installed_version == declared_version


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify the active Python environment before a Nuitka release build."
    )
    parser.add_argument("--requirements", type=Path, default=DEFAULT_REQUIREMENTS)
    parser.add_argument("--pyproject", type=Path, default=DEFAULT_PYPROJECT)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the release environment verifier."""
    args = _parse_args(argv)
    try:
        result = verify_release_environment(args.requirements, args.pyproject)
    except (OSError, ReleaseEnvironmentError, tomllib.TOMLDecodeError) as exc:
        print(f"release environment validation failed: {exc}", file=sys.stderr)
        return 1
    print(
        "release environment validated: "
        f"{result.pinned_distribution_count} exact pins; "
        f"{result.project_name}=={result.project_version} (non-editable)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
