"""phase18: company_profiles 로고/직인 BLOB 저장

Revision ID: c7e5d1f4a902
Revises: a91c4d2e7f01
Create Date: 2026-06-19 14:00:00.000000

v26까지는 로고/직인을 디스크(/tmp 기본) 저장 → 컨테이너 재배포·재부팅 시
휘발. 영구화를 위해 DB BLOB로 옮김. 멀티인스턴스(K8s/Cloud Run)에서도
동기화 문제 없음.

기존 logo_path/stamp_path 컬럼은 유지 (deprecated, 호환용).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c7e5d1f4a902"
down_revision: Union[str, None] = "a91c4d2e7f01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("company_profiles", sa.Column("logo_bytes", sa.LargeBinary(), nullable=True))
    op.add_column("company_profiles", sa.Column("logo_mimetype", sa.String(50), nullable=True))
    op.add_column("company_profiles", sa.Column("stamp_bytes", sa.LargeBinary(), nullable=True))
    op.add_column("company_profiles", sa.Column("stamp_mimetype", sa.String(50), nullable=True))


def downgrade() -> None:
    op.drop_column("company_profiles", "stamp_mimetype")
    op.drop_column("company_profiles", "stamp_bytes")
    op.drop_column("company_profiles", "logo_mimetype")
    op.drop_column("company_profiles", "logo_bytes")
