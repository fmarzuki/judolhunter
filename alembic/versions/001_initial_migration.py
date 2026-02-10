"""Initial database schema.

Revision ID: 001
Revises:
Create Date: 2026-02-09
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic
revision: str = '001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create users table
    op.create_table(
        'users',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('hashed_password', sa.String(length=255), nullable=False),
        sa.Column('full_name', sa.String(length=255), nullable=True),
        sa.Column('plan_type', sa.Enum('free', 'lite', 'pro', 'corporate', name='plantype'), nullable=False),
        sa.Column('plan_expires_at', sa.DateTime(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('is_verified', sa.Boolean(), nullable=False),
        sa.Column('role', sa.Enum('admin', 'user', name='userrole'), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('last_login_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_users_id'), 'users', ['id'])
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)
    op.create_index(op.f('ix_users_plan_type'), 'users', ['plan_type'])

    # Create plans table
    op.create_table(
        'plans',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('name', sa.String(length=50), nullable=False),
        sa.Column('slug', sa.Enum('free', 'lite', 'pro', 'corporate', name='plantype'), nullable=False),
        sa.Column('max_urls_per_scan', sa.Integer(), nullable=False),
        sa.Column('max_domains_per_week', sa.Integer(), nullable=False),
        sa.Column('price_monthly', sa.Integer(), nullable=True),
        sa.Column('features', sa.Text(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('display_order', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('slug')
    )

    # Create scans table
    op.create_table(
        'scans',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('session_id', sa.String(length=255), nullable=True),
        sa.Column('url', sa.String(length=2048), nullable=False),
        sa.Column('domain', sa.String(length=255), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('risk_level', sa.String(length=20), nullable=False),
        sa.Column('findings', sa.JSON(), nullable=True),
        sa.Column('fetch_info', sa.JSON(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('started_at', sa.DateTime(), nullable=False),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_scans_id'), 'scans', ['id'])
    op.create_index(op.f('ix_scans_user_id'), 'scans', ['user_id'])
    op.create_index(op.f('ix_scans_session_id'), 'scans', ['session_id'])
    op.create_index(op.f('ix_scans_domain'), 'scans', ['domain'])
    op.create_index(op.f('ix_scans_status'), 'scans', ['status'])

    # Create usage_trackers table
    op.create_table(
        'usage_trackers',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('session_id', sa.String(length=255), nullable=True),
        sa.Column('domain', sa.String(length=255), nullable=False),
        sa.Column('week_start', sa.Date(), nullable=False),
        sa.Column('scan_count', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_usage_trackers_id'), 'usage_trackers', ['id'])
    op.create_index(op.f('ix_usage_trackers_user_id'), 'usage_trackers', ['user_id'])
    op.create_index(op.f('ix_usage_trackers_session_id'), 'usage_trackers', ['session_id'])
    op.create_index(op.f('ix_usage_trackers_domain'), 'usage_trackers', ['domain'])
    op.create_index(op.f('ix_usage_trackers_week_start'), 'usage_trackers', ['week_start'])


def downgrade() -> None:
    op.drop_index(op.f('ix_usage_trackers_week_start'), table_name='usage_trackers')
    op.drop_index(op.f('ix_usage_trackers_domain'), table_name='usage_trackers')
    op.drop_index(op.f('ix_usage_trackers_session_id'), table_name='usage_trackers')
    op.drop_index(op.f('ix_usage_trackers_user_id'), table_name='usage_trackers')
    op.drop_index(op.f('ix_usage_trackers_id'), table_name='usage_trackers')
    op.drop_table('usage_trackers')

    op.drop_index(op.f('ix_scans_status'), table_name='scans')
    op.drop_index(op.f('ix_scans_domain'), table_name='scans')
    op.drop_index(op.f('ix_scans_session_id'), table_name='scans')
    op.drop_index(op.f('ix_scans_user_id'), table_name='scans')
    op.drop_index(op.f('ix_scans_id'), table_name='scans')
    op.drop_table('scans')

    op.drop_table('plans')

    op.drop_index(op.f('ix_users_plan_type'), table_name='users')
    op.drop_index(op.f('ix_users_email'), table_name='users')
    op.drop_index(op.f('ix_users_id'), table_name='users')
    op.drop_table('users')
