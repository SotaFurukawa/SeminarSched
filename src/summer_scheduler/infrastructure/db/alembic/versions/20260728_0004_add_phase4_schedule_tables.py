"""Phase 4の時間割結果と最適化実行履歴を追加する。

Revision ID: 20260728_0004
Revises: 20260728_0003
Create Date: 2026-07-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260728_0004"
down_revision: str | None = "20260728_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamp_columns() -> tuple[sa.Column[sa.DateTime], sa.Column[sa.DateTime]]:
    return (
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
    )


def upgrade() -> None:
    op.create_index(
        "ix_lesson_requests_project_id_id_unique",
        "lesson_requests",
        ["project_id", "id"],
        unique=True,
    )

    op.create_table(
        "optimization_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column(
            "solver_status",
            sa.String(length=30),
            server_default=sa.text("'UNKNOWN'"),
            nullable=False,
        ),
        sa.Column("time_limit_seconds", sa.Integer(), nullable=False),
        sa.Column(
            "objective_summary_json",
            sa.Text(),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column(
            "unassigned_count",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "warning_count",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("log_path_optional", sa.Text(), nullable=True),
        sa.Column(
            "input_snapshot_json",
            sa.Text(),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column(
            "result_snapshot_json",
            sa.Text(),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column(
            "random_seed",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("elapsed_seconds", sa.Float(), nullable=True),
        sa.CheckConstraint(
            "status IN ('running', 'completed', 'cancelled', 'failed')",
            name=op.f("ck_optimization_runs_status_value"),
        ),
        sa.CheckConstraint(
            "solver_status IN ('OPTIMAL', 'FEASIBLE', 'INFEASIBLE', 'UNKNOWN', 'MODEL_INVALID')",
            name=op.f("ck_optimization_runs_solver_status_value"),
        ),
        sa.CheckConstraint(
            "time_limit_seconds > 0",
            name=op.f("ck_optimization_runs_time_limit_positive"),
        ),
        sa.CheckConstraint(
            "unassigned_count >= 0 AND warning_count >= 0",
            name=op.f("ck_optimization_runs_counts_nonnegative"),
        ),
        sa.CheckConstraint(
            "elapsed_seconds IS NULL OR elapsed_seconds >= 0",
            name=op.f("ck_optimization_runs_elapsed_nonnegative"),
        ),
        sa.CheckConstraint(
            "finished_at IS NULL OR finished_at >= started_at",
            name=op.f("ck_optimization_runs_finished_after_started"),
        ),
        sa.CheckConstraint(
            "length(trim(objective_summary_json)) > 0",
            name=op.f("ck_optimization_runs_objective_summary_not_blank"),
        ),
        sa.CheckConstraint(
            "length(trim(input_snapshot_json)) > 0",
            name=op.f("ck_optimization_runs_input_snapshot_not_blank"),
        ),
        sa.CheckConstraint(
            "length(trim(result_snapshot_json)) > 0",
            name=op.f("ck_optimization_runs_result_snapshot_not_blank"),
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["course_projects.id"],
            name=op.f("fk_optimization_runs_project_id_course_projects"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_optimization_runs")),
    )
    op.create_index(
        "ix_optimization_runs_project_started",
        "optimization_runs",
        ["project_id", "started_at"],
        unique=False,
    )
    op.create_index(
        "ix_optimization_runs_project_status",
        "optimization_runs",
        ["project_id", "status"],
        unique=False,
    )

    op.create_table(
        "assignments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("lesson_request_id", sa.Integer(), nullable=False),
        sa.Column("session_index", sa.Integer(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("time_slot_id", sa.Integer(), nullable=False),
        sa.Column("teacher_id", sa.Integer(), nullable=False),
        sa.Column("optimization_run_id_optional", sa.Integer(), nullable=True),
        sa.Column(
            "is_locked",
            sa.Boolean(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "is_manual",
            sa.Boolean(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("created_by", sa.String(length=100), nullable=False),
        *_timestamp_columns(),
        sa.CheckConstraint(
            "session_index >= 1",
            name=op.f("ck_assignments_session_index_positive"),
        ),
        sa.CheckConstraint(
            "length(trim(created_by)) > 0",
            name=op.f("ck_assignments_created_by_not_blank"),
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["course_projects.id"],
            name=op.f("fk_assignments_project_id_course_projects"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "lesson_request_id"],
            ["lesson_requests.project_id", "lesson_requests.id"],
            name="fk_assignments_project_request_lesson_requests",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "time_slot_id"],
            ["time_slots.project_id", "time_slots.id"],
            name="fk_assignments_project_slot_time_slots",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["teacher_id"],
            ["teachers.id"],
            name=op.f("fk_assignments_teacher_id_teachers"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["optimization_run_id_optional"],
            ["optimization_runs.id"],
            name=op.f("fk_assignments_optimization_run_id_optional_optimization_runs"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_assignments")),
        sa.UniqueConstraint(
            "project_id",
            "lesson_request_id",
            "session_index",
            name=op.f("uq_assignments_project_request_session"),
        ),
    )
    op.create_index(
        "ix_assignments_project_date_slot",
        "assignments",
        ["project_id", "date", "time_slot_id"],
        unique=False,
    )
    op.create_index(
        "ix_assignments_project_teacher_date_slot",
        "assignments",
        ["project_id", "teacher_id", "date", "time_slot_id"],
        unique=False,
    )
    op.create_index(
        "ix_assignments_project_locked",
        "assignments",
        ["project_id", "is_locked"],
        unique=False,
    )
    op.create_index(
        "ix_assignments_optimization_run_id",
        "assignments",
        ["optimization_run_id_optional"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_table("assignments")
    op.drop_table("optimization_runs")
    op.drop_index(
        "ix_lesson_requests_project_id_id_unique",
        table_name="lesson_requests",
    )
