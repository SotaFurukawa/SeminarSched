"""YAMLと環境変数からアプリ設定を読み込む。"""

from __future__ import annotations

import math
import os
from collections.abc import Mapping
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path
from typing import Any, Final, cast

import yaml
from platformdirs import user_data_path

from summer_scheduler.reporting.settings import (
    OutputSettingsDefaults,
    OutputSettingsValidationError,
    PageOrientation,
    PaperSize,
    StudentPageMode,
    StyleRule,
)

_APP_DIRECTORY_NAME: Final = "SummerScheduler"
_CONFIG_ENV: Final = "SUMMER_SCHEDULER_CONFIG"
_DATA_DIR_ENV: Final = "SUMMER_SCHEDULER_DATA_DIR"
_DATABASE_PATH_ENV: Final = "SUMMER_SCHEDULER_DATABASE_PATH"
_LOG_DIR_ENV: Final = "SUMMER_SCHEDULER_LOG_DIR"


class SettingsError(ValueError):
    """設定ファイルが不正な場合に送出する例外。"""


@dataclass(frozen=True, slots=True)
class LoggingSettings:
    """ローカルログの設定。"""

    directory: Path
    filename: str
    level: str
    max_bytes: int
    backup_count: int

    @property
    def file_path(self) -> Path:
        """ログファイルの絶対パスを返す。"""
        return self.directory / self.filename


@dataclass(frozen=True, slots=True)
class BackupSettings:
    """自動バックアップのローカル世代管理設定。"""

    automatic_generations: int
    automatic_interval_minutes: int


@dataclass(frozen=True, slots=True)
class OptimizationAppSettings:
    """設定ファイルから読み込む最適化presetと段階内スコア。"""

    default_preset: str
    fast_time_limit_seconds: float
    standard_time_limit_seconds: float
    high_quality_time_limit_seconds: float
    random_seed: int
    num_search_workers: int
    regular_teacher_priority_weights: tuple[int, int, int, int]
    preferred_teacher_rank_weights: tuple[int, int, int]
    student_preferred_time_weight: int
    teacher_preferred_time_weight: int
    preserve_existing_assignment_weight: int
    optional_balance_weight: int

    def time_limit_for(self, preset: str) -> float:
        """UIのpreset名を検証し、対応する全体秒数を返す。"""
        limits = {
            "fast": self.fast_time_limit_seconds,
            "standard": self.standard_time_limit_seconds,
            "high_quality": self.high_quality_time_limit_seconds,
        }
        try:
            return limits[preset]
        except KeyError as exc:
            raise SettingsError(
                "最適化presetはfast/standard/high_qualityから選んでください"
            ) from exc


@dataclass(frozen=True, slots=True)
class AppSettings:
    """起動時に確定したアプリ設定。"""

    application_name: str
    organization_name: str
    data_directory: Path
    database_path: Path
    logging: LoggingSettings
    backup: BackupSettings
    optimization: OptimizationAppSettings
    output: OutputSettingsDefaults
    config_path: Path


def load_settings(config_path: Path | None = None) -> AppSettings:
    """既定値、任意YAML、環境変数の順で設定を上書きして返す。

    明示指定または ``SUMMER_SCHEDULER_CONFIG`` で指定されたファイルが
    存在しない場合は、入力ミスを黙って無視せず ``SettingsError`` にする。
    """

    default_data = _load_yaml_resource()
    selected_path, is_explicit = _select_config_path(config_path)
    merged = default_data

    if selected_path.is_file():
        merged = _deep_merge(default_data, _load_yaml_file(selected_path))
    elif is_explicit:
        raise SettingsError(f"設定ファイルが見つかりません: {selected_path}")

    application = _mapping(merged, "application")
    storage = _mapping(merged, "storage")
    logging_data = _mapping(merged, "logging")
    backup_data = _mapping(merged, "backup")
    optimization_data = _mapping(merged, "optimization")
    output_data = _mapping(merged, "output")

    application_name = _non_empty_string(application, "name")
    organization_name = _non_empty_string(application, "organization_name")

    app_root = user_data_path(_APP_DIRECTORY_NAME, appauthor=False)
    configured_data_dir = os.getenv(_DATA_DIR_ENV) or storage.get("data_directory")
    data_directory = _resolve_path(
        configured_data_dir,
        default=app_root / "data",
        relative_to=selected_path.parent,
        field_name="storage.data_directory",
    )

    configured_database_path = os.getenv(_DATABASE_PATH_ENV)
    if configured_database_path:
        database_path = _resolve_path(
            configured_database_path,
            default=data_directory / "summer_scheduler.db",
            relative_to=selected_path.parent,
            field_name=_DATABASE_PATH_ENV,
        )
    else:
        database_filename = _safe_filename(storage, "database_filename")
        database_path = data_directory / database_filename

    configured_log_dir = os.getenv(_LOG_DIR_ENV) or logging_data.get("directory")
    log_directory = _resolve_path(
        configured_log_dir,
        default=app_root / "logs",
        relative_to=selected_path.parent,
        field_name="logging.directory",
    )

    return AppSettings(
        application_name=application_name,
        organization_name=organization_name,
        data_directory=data_directory,
        database_path=database_path,
        logging=LoggingSettings(
            directory=log_directory,
            filename=_safe_filename(logging_data, "filename"),
            level=_log_level(logging_data),
            max_bytes=_positive_int(logging_data, "max_bytes"),
            backup_count=_non_negative_int(logging_data, "backup_count"),
        ),
        backup=BackupSettings(
            automatic_generations=_positive_int(
                backup_data,
                "automatic_generations",
            ),
            automatic_interval_minutes=_positive_int(
                backup_data,
                "automatic_interval_minutes",
            ),
        ),
        optimization=OptimizationAppSettings(
            default_preset=_choice(
                optimization_data,
                "default_preset",
                {"fast", "standard", "high_quality"},
            ),
            fast_time_limit_seconds=_positive_float(
                optimization_data,
                "fast_time_limit_seconds",
            ),
            standard_time_limit_seconds=_positive_float(
                optimization_data,
                "standard_time_limit_seconds",
            ),
            high_quality_time_limit_seconds=_positive_float(
                optimization_data,
                "high_quality_time_limit_seconds",
            ),
            random_seed=_non_negative_int(optimization_data, "random_seed"),
            num_search_workers=_positive_int(optimization_data, "num_search_workers"),
            regular_teacher_priority_weights=cast(
                tuple[int, int, int, int],
                _integer_tuple(
                    optimization_data,
                    "regular_teacher_priority_weights",
                    length=4,
                ),
            ),
            preferred_teacher_rank_weights=cast(
                tuple[int, int, int],
                _integer_tuple(
                    optimization_data,
                    "preferred_teacher_rank_weights",
                    length=3,
                ),
            ),
            student_preferred_time_weight=_non_negative_int(
                optimization_data,
                "student_preferred_time_weight",
            ),
            teacher_preferred_time_weight=_non_negative_int(
                optimization_data,
                "teacher_preferred_time_weight",
            ),
            preserve_existing_assignment_weight=_non_negative_int(
                optimization_data,
                "preserve_existing_assignment_weight",
            ),
            optional_balance_weight=_non_negative_int(
                optimization_data,
                "optional_balance_weight",
            ),
        ),
        output=_output_settings_defaults(
            output_data,
            relative_to=selected_path.parent,
        ),
        config_path=selected_path,
    )


def ensure_runtime_directories(settings: AppSettings) -> None:
    """DBとログの保存ディレクトリを必要な場合だけ作成する。"""
    settings.database_path.parent.mkdir(parents=True, exist_ok=True)
    settings.logging.directory.mkdir(parents=True, exist_ok=True)


def _load_yaml_resource() -> dict[str, Any]:
    resource = files("summer_scheduler.resources").joinpath("default_settings.yaml")
    with resource.open("r", encoding="utf-8") as stream:
        return _yaml_mapping(yaml.safe_load(stream), "組込み既定設定")


def _load_yaml_file(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as stream:
            return _yaml_mapping(yaml.safe_load(stream), str(path))
    except OSError as exc:
        raise SettingsError(f"設定ファイルを読み込めません: {path}") from exc
    except yaml.YAMLError as exc:
        raise SettingsError(f"設定ファイルのYAML形式が不正です: {path}") from exc


def _select_config_path(config_path: Path | None) -> tuple[Path, bool]:
    if config_path is not None:
        return config_path.expanduser().resolve(), True

    environment_path = os.getenv(_CONFIG_ENV)
    if environment_path:
        return Path(environment_path).expanduser().resolve(), True

    default_path = user_data_path(_APP_DIRECTORY_NAME, appauthor=False) / "config.yaml"
    return default_path, False


def _deep_merge(base: Mapping[str, Any], override: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(base)
    for key, value in override.items():
        current = result.get(key)
        if isinstance(current, Mapping) and isinstance(value, Mapping):
            result[key] = _deep_merge(current, value)
        else:
            result[key] = value
    return result


def _yaml_mapping(value: object, source: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise SettingsError(f"{source}のルートはマッピングである必要があります")
    return {str(key): item for key, item in value.items()}


def _mapping(data: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = data.get(key)
    if not isinstance(value, Mapping):
        raise SettingsError(f"設定「{key}」はマッピングである必要があります")
    return value


def _non_empty_string(data: Mapping[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise SettingsError(f"設定「{key}」には空でない文字列を指定してください")
    return value.strip()


def _safe_filename(data: Mapping[str, Any], key: str) -> str:
    value = _non_empty_string(data, key)
    path = Path(value)
    if path.name != value or value in {".", ".."}:
        raise SettingsError(f"設定「{key}」にはファイル名だけを指定してください")
    return value


def _positive_int(data: Mapping[str, Any], key: str) -> int:
    value = data.get(key)
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise SettingsError(f"設定「{key}」には正の整数を指定してください")
    return value


def _non_negative_int(data: Mapping[str, Any], key: str) -> int:
    value = data.get(key)
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise SettingsError(f"設定「{key}」には0以上の整数を指定してください")
    return value


def _positive_float(data: Mapping[str, Any], key: str) -> float:
    value = data.get(key)
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(float(value))
        or not float(value) > 0.0
    ):
        raise SettingsError(f"設定「{key}」には正の数を指定してください")
    return float(value)


def _integer_tuple(
    data: Mapping[str, Any],
    key: str,
    *,
    length: int,
) -> tuple[int, ...]:
    value = data.get(key)
    if (
        not isinstance(value, list)
        or len(value) != length
        or any(not isinstance(item, int) or isinstance(item, bool) or item < 0 for item in value)
    ):
        raise SettingsError(f"設定「{key}」には{length}個の0以上の整数を指定してください")
    return tuple(value)


def _output_settings_defaults(
    data: Mapping[str, Any],
    *,
    relative_to: Path,
) -> OutputSettingsDefaults:
    style_data = _mapping(data, "style_rules")
    style_rules: list[StyleRule] = []
    for raw_code in style_data:
        if not isinstance(raw_code, str) or not raw_code.strip():
            raise SettingsError("設定「output.style_rules」のコードが不正です")
        code = raw_code.strip()
        rule = _mapping(style_data, raw_code)
        style_rules.append(
            StyleRule(
                code=code,
                label=_non_empty_string(rule, "label"),
                marker=_non_empty_string(rule, "marker"),
                fill_color=_non_empty_string(rule, "fill_color"),
                text_color=_non_empty_string(rule, "text_color"),
            )
        )
    defaults = OutputSettingsDefaults(
        paper_size=cast(
            PaperSize,
            _choice(data, "paper_size", {"A3", "A4"}),
        ),
        orientation=cast(
            PageOrientation,
            _choice(data, "orientation", {"landscape", "portrait"}),
        ),
        visible_fields=_string_tuple(data, "visible_fields"),
        days_per_page=_plain_int(data, "days_per_page"),
        teacher_columns_per_page=_plain_int(
            data,
            "teacher_columns_per_page",
        ),
        font_size=_finite_number(data, "font_size"),
        margin_mm=_finite_number(data, "margin_mm"),
        file_name_pattern=_non_empty_string(data, "file_name_pattern"),
        default_output_directory_optional=_optional_path_string(
            data.get("default_output_directory"),
            relative_to=relative_to,
            field_name="output.default_output_directory",
        ),
        student_page_mode=cast(
            StudentPageMode,
            _choice(
                data,
                "student_page_mode",
                {"one_per_page", "combined"},
            ),
        ),
        csv_with_bom=_boolean(data, "csv_with_bom"),
        style_rules=tuple(style_rules),
    )
    try:
        defaults.for_project(1)
    except OutputSettingsValidationError as exc:
        raise SettingsError(f"設定「output」が不正です: {exc}") from exc
    return defaults


def _plain_int(data: Mapping[str, Any], key: str) -> int:
    value = data.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        raise SettingsError(f"設定「{key}」には整数を指定してください")
    return value


def _finite_number(data: Mapping[str, Any], key: str) -> float:
    value = data.get(key)
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(float(value))
    ):
        raise SettingsError(f"設定「{key}」には有限の数値を指定してください")
    return float(value)


def _boolean(data: Mapping[str, Any], key: str) -> bool:
    value = data.get(key)
    if not isinstance(value, bool):
        raise SettingsError(f"設定「{key}」にはtrueまたはfalseを指定してください")
    return value


def _string_tuple(data: Mapping[str, Any], key: str) -> tuple[str, ...]:
    value = data.get(key)
    if (
        not isinstance(value, list)
        or not value
        or any(not isinstance(item, str) or not item.strip() for item in value)
    ):
        raise SettingsError(f"設定「{key}」には空でない文字列の一覧を指定してください")
    return tuple(item.strip() for item in value)


def _optional_path_string(
    value: object,
    *,
    relative_to: Path,
    field_name: str,
) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise SettingsError(f"設定「{field_name}」にはパス文字列またはnullを指定してください")
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = relative_to / path
    return str(path.resolve())


def _choice(data: Mapping[str, Any], key: str, allowed: set[str]) -> str:
    value = _non_empty_string(data, key)
    if value not in allowed:
        options = "/".join(sorted(allowed))
        raise SettingsError(f"設定「{key}」は{options}から選んでください")
    return value


def _log_level(data: Mapping[str, Any]) -> str:
    value = _non_empty_string(data, "level").upper()
    allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
    if value not in allowed:
        raise SettingsError(
            "設定「logging.level」はDEBUG/INFO/WARNING/ERROR/CRITICALから選んでください"
        )
    return value


def _resolve_path(
    value: object,
    *,
    default: Path,
    relative_to: Path,
    field_name: str,
) -> Path:
    if value is None:
        path = default
    elif isinstance(value, str) and value.strip():
        path = Path(value).expanduser()
        if not path.is_absolute():
            path = relative_to / path
    else:
        raise SettingsError(f"設定「{field_name}」にはパス文字列を指定してください")
    return path.resolve()
