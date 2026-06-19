"""phase19b: order_no global unique → (tenant_id, order_no) composite

Revision ID: e4a91c3d7f08
Revises: d3f8b4e2c105
Create Date: 2026-06-19 17:30:00.000000

외부 쇼핑몰 백오피스 도입 후 카페24/네이버/쿠팡이 동일한 단순 번호
(예: '100001')를 사용해도 import가 IntegrityError 없이 통과하도록.

운영자가 import 시 shop prefix를 붙이지 않더라도, 멀티테넌트 환경이라면
테넌트별로 격리되어 충돌 없음. 단일 테넌트(tenant_id=NULL) 운영자는
import 엔드포인트가 자동으로 'CAFE24-100001'과 같이 shop prefix를 붙여
충돌을 방지.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "e4a91c3d7f08"
down_revision: Union[str, None] = "d3f8b4e2c105"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        # SQLite는 unique constraint drop이 까다로움 → batch_alter_table
        with op.batch_alter_table("sales_orders", schema=None) as batch_op:
            batch_op.create_unique_constraint(
                "uq_sales_orders_tenant_order_no", ["tenant_id", "order_no"]
            )
        # 기존의 단일 unique index/constraint는 batch 작업으로 재생성되며
        # SQLAlchemy가 모델 정의 기준으로 처리. 명시적 drop은 생략 (sqlite_autoindex_*).
        return

    # Postgres / MySQL — 기존 unique 제약/인덱스 안전 제거 후 composite 생성
    insp = op.get_context().opts["target_metadata"].bind  # noqa: F841 (보존)
    # 기존 unique constraint 이름이 명시되지 않았으므로 Postgres에서는
    # 자동 생성된 sales_orders_order_no_key 또는 ix_sales_orders_order_no 일 수 있음.
    op.execute(
        "ALTER TABLE sales_orders DROP CONSTRAINT IF EXISTS sales_orders_order_no_key"
    )
    op.execute(
        "DROP INDEX IF EXISTS ix_sales_orders_order_no"
    )
    op.create_index("ix_sales_orders_order_no", "sales_orders", ["order_no"])
    op.create_unique_constraint(
        "uq_sales_orders_tenant_order_no",
        "sales_orders",
        ["tenant_id", "order_no"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("sales_orders", schema=None) as batch_op:
            batch_op.drop_constraint(
                "uq_sales_orders_tenant_order_no", type_="unique"
            )
        return
    op.drop_constraint(
        "uq_sales_orders_tenant_order_no", "sales_orders", type_="unique"
    )
    op.execute("DROP INDEX IF EXISTS ix_sales_orders_order_no")
    op.create_index(
        "ix_sales_orders_order_no", "sales_orders", ["order_no"], unique=True
    )
