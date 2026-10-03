"""create_users_shops_and_records

Revision ID: c96a7f33551c
Revises: 
Create Date: 2026-10-03 19:23:02.890875

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c96a7f33551c'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema for PostgreSQL."""
    # users
    op.create_table(
        'users',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('username', sa.String(length=80), nullable=False),
        sa.Column('fullname', sa.String(length=120), nullable=False),
        sa.Column('email', sa.String(length=120), nullable=False),
        sa.Column('password_hash', sa.String(length=255), nullable=False),
        sa.Column('role', sa.String(length=30), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)
    op.create_index(op.f('ix_users_id'), 'users', ['id'], unique=False)
    op.create_index(op.f('ix_users_username'), 'users', ['username'], unique=True)

    # shops
    op.create_table(
        'shops',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=150), nullable=False),
        sa.Column('owner_user_id', sa.Integer(), nullable=False),
        sa.Column('email', sa.String(length=120), nullable=True),
        sa.Column('phone', sa.String(length=50), nullable=True),
        sa.Column('address', sa.String(length=255), nullable=True),
        sa.Column('currency', sa.String(length=10), nullable=False),
        sa.Column('timezone', sa.String(length=50), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['owner_user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_shops_id'), 'shops', ['id'], unique=False)

    # daily_records
    op.create_table(
        'daily_records',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('shop_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('record_date', sa.Date(), nullable=False),
        sa.Column('total_customer_money', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('total_digital_money', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('total_cash_received', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('total_expenses', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('total_own_money', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('total_cash_box_expenses', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('in_hand_money', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('image_url', sa.String(length=500), nullable=True),
        sa.Column('image_hash', sa.String(length=64), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['shop_id'], ['shops.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_daily_records_id'), 'daily_records', ['id'], unique=False)
    op.create_index(op.f('ix_daily_records_image_hash'), 'daily_records', ['image_hash'], unique=False)
    op.create_index(op.f('ix_daily_records_record_date'), 'daily_records', ['record_date'], unique=False)
    op.create_index(op.f('ix_daily_records_shop_id'), 'daily_records', ['shop_id'], unique=False)
    op.create_index(op.f('ix_daily_records_user_id'), 'daily_records', ['user_id'], unique=False)

    # customer_receipts
    op.create_table(
        'customer_receipts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('daily_record_id', sa.Integer(), nullable=False),
        sa.Column('amount', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('payment_type', sa.String(length=20), nullable=True),
        sa.Column('description', sa.String(length=255), nullable=True),
        sa.Column('raw_text', sa.String(length=255), nullable=True),
        sa.Column('source_reference', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['daily_record_id'], ['daily_records.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_customer_receipts_id'), 'customer_receipts', ['id'], unique=False)
    op.create_index(op.f('ix_customer_receipts_daily_record_id'), 'customer_receipts', ['daily_record_id'], unique=False)

    # digital_entries
    op.create_table(
        'digital_entries',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('daily_record_id', sa.Integer(), nullable=False),
        sa.Column('amount', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('raw_text', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['daily_record_id'], ['daily_records.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_digital_entries_id'), 'digital_entries', ['id'], unique=False)
    op.create_index(op.f('ix_digital_entries_daily_record_id'), 'digital_entries', ['daily_record_id'], unique=False)

    # expenses
    op.create_table(
        'expenses',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('daily_record_id', sa.Integer(), nullable=False),
        sa.Column('description', sa.String(length=255), nullable=False),
        sa.Column('total_amount', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('own_amount', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('cash_box_amount', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('raw_text', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['daily_record_id'], ['daily_records.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_expenses_id'), 'expenses', ['id'], unique=False)
    op.create_index(op.f('ix_expenses_daily_record_id'), 'expenses', ['daily_record_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_expenses_daily_record_id'), table_name='expenses')
    op.drop_index(op.f('ix_expenses_id'), table_name='expenses')
    op.drop_table('expenses')
    op.drop_index(op.f('ix_digital_entries_daily_record_id'), table_name='digital_entries')
    op.drop_index(op.f('ix_digital_entries_id'), table_name='digital_entries')
    op.drop_table('digital_entries')
    op.drop_index(op.f('ix_customer_receipts_daily_record_id'), table_name='customer_receipts')
    op.drop_index(op.f('ix_customer_receipts_id'), table_name='customer_receipts')
    op.drop_table('customer_receipts')
    op.drop_index(op.f('ix_daily_records_user_id'), table_name='daily_records')
    op.drop_index(op.f('ix_daily_records_shop_id'), table_name='daily_records')
    op.drop_index(op.f('ix_daily_records_record_date'), table_name='daily_records')
    op.drop_index(op.f('ix_daily_records_image_hash'), table_name='daily_records')
    op.drop_index(op.f('ix_daily_records_id'), table_name='daily_records')
    op.drop_table('daily_records')
    op.drop_index(op.f('ix_shops_id'), table_name='shops')
    op.drop_table('shops')
    op.drop_index(op.f('ix_users_username'), table_name='users')
    op.drop_index(op.f('ix_users_id'), table_name='users')
    op.drop_index(op.f('ix_users_email'), table_name='users')
    op.drop_table('users')
