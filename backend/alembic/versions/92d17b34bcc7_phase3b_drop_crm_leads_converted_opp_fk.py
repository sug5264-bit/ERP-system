"""phase3b: drop crm_leads.converted_opp FK

Revision ID: 92d17b34bcc7
Revises: 6f8b9bb7ad1c
Create Date: 2026-05-10 07:26:26.319754

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '92d17b34bcc7'
down_revision: Union[str, None] = '6f8b9bb7ad1c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # CRM 모듈 테이블은 모델 기반(autogenerate)만으로 운영되어 마이그레이션 체인에
    # create_table('crm_leads')가 없음. 신규 DB 부트 시 이 alter는 대상이 없으므로
    # 테이블 존재 시에만 실행 (idempotent).
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if 'crm_leads' not in insp.get_table_names():
        return
    with op.batch_alter_table('crm_leads', schema=None) as batch_op:
        try:
            batch_op.drop_constraint(
                batch_op.f('fk_crm_leads_converted_opportunity_id_crm_opportunities'),
                type_='foreignkey',
            )
        except Exception:
            # 제약이 없거나 이름이 다른 환경(이미 자동 생성된 스키마) — 무시
            pass


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if 'crm_leads' not in insp.get_table_names():
        return
    with op.batch_alter_table('crm_leads', schema=None) as batch_op:
        try:
            batch_op.create_foreign_key(
                batch_op.f('fk_crm_leads_converted_opportunity_id_crm_opportunities'),
                'crm_opportunities',
                ['converted_opportunity_id'],
                ['id'],
            )
        except Exception:
            pass
