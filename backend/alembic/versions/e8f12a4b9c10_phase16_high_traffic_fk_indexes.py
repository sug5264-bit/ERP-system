"""phase16: high-traffic FK indexes

Revision ID: e8f12a4b9c10
Revises: b17a28d69812
Create Date: 2026-05-13 00:00:00
"""
from alembic import op


revision = "e8f12a4b9c10"
down_revision = "b17a28d69812"
branch_labels = None
depends_on = None


# (table, column) pairs that join frequently and were missing indexes.
HIGH_TRAFFIC_INDEXES = [
    ("fin_journal_lines", "entry_id"),
    ("fin_journal_lines", "account_id"),
    ("approval_steps", "approver_id"),
    ("approval_steps", "escalate_to_id"),
    ("contracts", "customer_id"),
    ("contracts", "supplier_id"),
    ("contracts", "employee_id"),
    ("crm_opportunities", "customer_id"),
    ("hr_employees", "department_id"),
    ("ats_applications", "converted_employee_id"),
    ("ats_job_postings", "department_id"),
    ("fa_assets", "category_id"),
    ("audit_logs", "user_id"),
]


def upgrade() -> None:
    for tbl, col in HIGH_TRAFFIC_INDEXES:
        op.create_index(
            f"ix_{tbl}_{col}_perf", tbl, [col], unique=False,
        )


def downgrade() -> None:
    for tbl, col in HIGH_TRAFFIC_INDEXES:
        op.drop_index(f"ix_{tbl}_{col}_perf", table_name=tbl)
