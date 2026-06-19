"""phase17: company_profile + customer/supplier KR document fields

Revision ID: a91c4d2e7f01
Revises: d7e7f9b2d668
Create Date: 2026-06-19 11:00:00.000000

한국형 ERP 표준 양식(거래명세표, 인수증, 세금계산서, 발주서, 견적서)
출력에 필요한 회사/거래처 정보를 보강.

추가:
- company_profiles 신설 (사업자등록증 + 입금계좌)
- sales_customers: 사업자번호, 대표자, 주소, 업태/종목, 팩스, 담당자, 은행
- suppliers: 위와 동일 항목

기존 데이터 보존(전부 nullable). 다운그레이드 가능.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "a91c4d2e7f01"
down_revision: Union[str, None] = "d7e7f9b2d668"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ─── company_profiles ────────────────────────────────────────────
    op.create_table(
        "company_profiles",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column(
            "tenant_id",
            sa.Integer,
            sa.ForeignKey("tenants.id"),
            nullable=True,
            index=True,
        ),
        sa.Column("business_no", sa.String(20), nullable=False),
        sa.Column("corporate_no", sa.String(20)),
        sa.Column("company_name", sa.String(200), nullable=False),
        sa.Column("representative", sa.String(100), nullable=False),
        sa.Column("address", sa.String(500), nullable=False),
        sa.Column("business_type", sa.String(100)),
        sa.Column("business_item", sa.String(200)),
        sa.Column("phone", sa.String(50)),
        sa.Column("fax", sa.String(50)),
        sa.Column("email", sa.String(255)),
        sa.Column("website", sa.String(255)),
        sa.Column("bank_name", sa.String(100)),
        sa.Column("bank_account", sa.String(100)),
        sa.Column("bank_holder", sa.String(100)),
        sa.Column("logo_path", sa.String(500)),
        sa.Column("stamp_path", sa.String(500)),
        sa.UniqueConstraint("tenant_id", name="uq_company_profile_tenant"),
    )

    # ─── sales_customers 확장 ────────────────────────────────────────
    new_customer_cols = [
        ("business_no", sa.String(20)),
        ("representative", sa.String(100)),
        ("address", sa.String(500)),
        ("business_type", sa.String(100)),
        ("business_item", sa.String(200)),
        ("fax", sa.String(50)),
        ("contact_person", sa.String(100)),
        ("bank_name", sa.String(100)),
        ("bank_account", sa.String(100)),
    ]
    for name, col_type in new_customer_cols:
        op.add_column("sales_customers", sa.Column(name, col_type, nullable=True))
    op.create_index(
        "ix_sales_customers_business_no", "sales_customers", ["business_no"]
    )

    # ─── suppliers 확장 ─────────────────────────────────────────────
    new_supplier_cols = [
        ("representative", sa.String(100)),
        ("address", sa.String(500)),
        ("business_type", sa.String(100)),
        ("business_item", sa.String(200)),
        ("fax", sa.String(50)),
        ("contact_person", sa.String(100)),
        ("bank_name", sa.String(100)),
        ("bank_account", sa.String(100)),
    ]
    for name, col_type in new_supplier_cols:
        op.add_column("suppliers", sa.Column(name, col_type, nullable=True))


def downgrade() -> None:
    for name in (
        "bank_account",
        "bank_name",
        "contact_person",
        "fax",
        "business_item",
        "business_type",
        "address",
        "representative",
    ):
        op.drop_column("suppliers", name)

    op.drop_index("ix_sales_customers_business_no", table_name="sales_customers")
    for name in (
        "bank_account",
        "bank_name",
        "contact_person",
        "fax",
        "business_item",
        "business_type",
        "address",
        "representative",
        "business_no",
    ):
        op.drop_column("sales_customers", name)

    op.drop_table("company_profiles")
