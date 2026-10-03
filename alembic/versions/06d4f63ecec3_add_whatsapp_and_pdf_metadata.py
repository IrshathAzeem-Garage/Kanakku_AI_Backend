"""add_whatsapp_and_pdf_metadata

Revision ID: 06d4f63ecec3
Revises: c96a7f33551c
Create Date: 2026-10-03 23:58:09.122883

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '06d4f63ecec3'
down_revision: Union[str, Sequence[str], None] = 'c96a7f33551c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('whatsapp_number', sa.String(length=50), nullable=True))
    op.add_column('daily_records', sa.Column('pdf_generated_at', sa.DateTime(), nullable=True))
    op.add_column('daily_records', sa.Column('pdf_file_name', sa.String(length=255), nullable=True))
    op.add_column('daily_records', sa.Column('whatsapp_status', sa.String(length=50), server_default='not_sent', nullable=True))
    op.add_column('daily_records', sa.Column('whatsapp_message_id', sa.String(length=255), nullable=True))
    op.add_column('daily_records', sa.Column('whatsapp_sent_at', sa.DateTime(), nullable=True))
    op.add_column('daily_records', sa.Column('whatsapp_error', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('daily_records', 'whatsapp_error')
    op.drop_column('daily_records', 'whatsapp_sent_at')
    op.drop_column('daily_records', 'whatsapp_message_id')
    op.drop_column('daily_records', 'whatsapp_status')
    op.drop_column('daily_records', 'pdf_file_name')
    op.drop_column('daily_records', 'pdf_generated_at')
    op.drop_column('users', 'whatsapp_number')

