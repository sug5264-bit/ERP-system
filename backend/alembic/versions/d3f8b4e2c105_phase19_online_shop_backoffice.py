"""phase19: online shop backoffice support

Revision ID: d3f8b4e2c105
Revises: c7e5d1f4a902
Create Date: 2026-06-19 16:00:00.000000

외부 쇼핑몰(카페24/네이버 스마트스토어/쿠팡 등) 백오피스 운영 지원:
- Customer.customer_type (business/individual) — 세금계산서 발행 대상 구분
- Customer.external_id / external_source — 쇼핑몰 회원 ID 매칭
- Item.external_sku — 쇼핑몰 상품코드 ↔ 내부 SKU 매핑

기존 데이터는 모두 'business' (default) 로 시작 — 운영자가 점진적으로 분류.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d3f8b4e2c105"
down_revision: Union[str, None] = "c7e5d1f4a902"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Customer
    op.add_column(
        "sales_customers",
        sa.Column(
            "customer_type",
            sa.String(20),
            nullable=False,
            server_default="business",
        ),
    )
    op.add_column(
        "sales_customers", sa.Column("external_id", sa.String(100), nullable=True)
    )
    op.add_column(
        "sales_customers", sa.Column("external_source", sa.String(50), nullable=True)
    )
    op.create_index(
        "ix_sales_customers_external_id", "sales_customers", ["external_id"]
    )
    op.create_index(
        "ix_sales_customers_customer_type", "sales_customers", ["customer_type"]
    )

    # Item
    op.add_column(
        "inv_items", sa.Column("external_sku", sa.String(100), nullable=True)
    )
    op.create_index("ix_inv_items_external_sku", "inv_items", ["external_sku"])


def downgrade() -> None:
    op.drop_index("ix_inv_items_external_sku", table_name="inv_items")
    op.drop_column("inv_items", "external_sku")

    op.drop_index("ix_sales_customers_customer_type", table_name="sales_customers")
    op.drop_index("ix_sales_customers_external_id", table_name="sales_customers")
    op.drop_column("sales_customers", "external_source")
    op.drop_column("sales_customers", "external_id")
    op.drop_column("sales_customers", "customer_type")
